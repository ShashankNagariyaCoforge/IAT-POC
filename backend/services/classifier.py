"""
AI classifier service (Step 11).
Sends PII-masked text to Azure OpenAI GPT-4o-mini for classification.
Returns structured JSON with category, confidence, summary, and routing.
"""

import json
import logging
from typing import Dict

from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models.classification import ClassificationResult, KeyFields
from models.case import ClassificationCategory

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert insurance document classification AI. Analyze the following email content
and classify it into exactly one category. 

Categories:
1. New - New policy applications or first-time insurance requests
2. Renewal - Policy renewal requests or related documents
3. Query/General - General questions or information requests
4. Follow-up - Follow-up on previously submitted items
5. Complaint/Escalation - Formal complaints or escalated issues
6. Regulatory/Legal - FCA, legal, compliance communications
7. Documentation/Evidence - Supporting documents for existing cases
8. Spam/Irrelevant - Unsolicited or non-insurance emails

Classification Rules:
- If an email contains both a Complaint and a General Query, ALWAYS classify it as Complaint/Escalation.
- If an email is following up on a New application, use Follow-up, NOT New.
- If an email just says "Thank you" or "Received", classify it as Spam/Irrelevant.

NOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders.

Respond ONLY with valid JSON in this exact format. You MUST provide your step-by-step reasoning FIRST before outputting the final category.
{
  "reasoning": "<Explain step-by-step why you chose this category and team over the alternatives before generating the final score>",
  "classification_category": "<category name>",
  "confidence_score": <0.0 to 1.0>,
  "summary": "<2-3 sentence plain English summary>",
  "key_fields": {
    "document_type": "<type>",
    "urgency": "<low|medium|high>",
    "policy_reference": "<masked value or null>",
    "claim_type": "<type or null>"
  },
  "requires_human_review": <true if confidence < 0.75, else false>
}"""


class Classifier:
    """Azure OpenAI GPT-4o-mini classifier for insurance email triage."""

    def __init__(self):
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            # Uses DefaultAzureCredential for token-based auth if api_key is None
        )
        self._deployment = settings.azure_openai_deployment
        self._confidence_threshold = settings.classification_confidence_threshold

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def classify(self, masked_text: str) -> Dict:
        """
        Classify a PII-masked email/document using GPT-4o-mini.

        Args:
            masked_text: PII-masked text content of the email and its documents.

        Returns:
            Parsed classification result dictionary.

        Raises:
            ValueError: If GPT returns invalid JSON.
            Exception: If API call fails after retries.
        """
        logger.info(f"Sending {len(masked_text)} chars to GPT-4o-mini for classification.")
        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Email content:\n\n{masked_text[:8000]}"},
                ],
                temperature=0.1,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            raw_json = response.choices[0].message.content
            result = json.loads(raw_json)
            self._validate_result(result)
            logger.info(
                f"Classification result: {result.get('classification_category')} "
                f"(confidence: {result.get('confidence_score')})"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(f"GPT returned invalid JSON: {e}")
            raise ValueError(f"GPT classification returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Classification API call failed: {e}", exc_info=True)
            raise

    def _validate_result(self, result: dict) -> None:
        """
        Validate that GPT classification result contains required fields.

        Args:
            result: Parsed JSON from GPT response.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        required = ["reasoning", "classification_category", "confidence_score", "summary"]
        for field in required:
            if field not in result:
                raise ValueError(f"Classification result missing required field: {field}")

        # Ensure confidence score is in valid range
        score = float(result["confidence_score"])
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Invalid confidence_score: {score}")

        # Enforce requires_human_review based on threshold
        result["requires_human_review"] = score < self._confidence_threshold
