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

SYSTEM_PROMPT = """You are an expert insurance document classification AI. 
You are analyzing a Conversation Thread between multiple parties (Brokers, Underwriters, Insureds). 
The content may contain multiple emails and attachments, separated by [Source: ...]. 
Your goal is to synthesize the entire thread to identify the final intent, latest names, dates, and terms. 

Categories:
1. New - New policy applications or first-time insurance requests
2. Renewal - Policy renewal requests or related documents
3. Query/General - General questions or information requests
4. Follow-up - Follow-up on previously submitted items
5. Complaint/Escalation - Formal complaints or escalated issues
6. Regulatory/Legal - FCA, legal, compliance communications
7. Documentation/Evidence - Supporting documents for existing cases
8. Spam/Irrelevant - Unsolicited or non-insurance emails
9. BOR - Broker of Record change requests

Classification Rules:
- If a thread shows a change in the designated broker, classify it as BOR.
- If a thread contains both a Complaint and a General Query, ALWAYS classify it as Complaint/Escalation.
- If an email is following up on a New application, use Follow-up, NOT New.
- If the latest reply just says "Thank you" or "Received", distinguish it from the core request but don't ignore the context of the conversion.

Extraction Instructions:
- name: The Insured Business Name.
- insured: { "name": "...", "address": "..." }
- agent: { "agencyName": "...", "name": "...", "email": "...", "phone": "..." }
- description: A brief summary of the insurance submission.
- coverages: An array of objects: { "coverage": "...", "description": "...", "limit": "...", "deductible": "..." }
- exposures: An array of objects: { "exposureType": "...", "description": "...", "value": "..." }
- documents: An array of objects indicating the attached documents found in the text.

NOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders. If a value is masked, return the placeholder.

Respond ONLY with valid JSON in this exact format:
{
  "reasoning": "<Explain step-by-step why you chose this category.>",
  "classification_category": "<category name>",
  "confidence_score": <0.0 to 1.0>,
  "summary": "<2-3 sentence summary>",
  "key_fields": {
    "name": "<Insured Business Name>",
    "insured": { "name": "<val>", "address": "<val>" },
    "agent": { "agencyName": "<val>", "name": "<val>", "email": "<val>", "phone": "<val>" },
    "description": "<summary>",
    "coverages": [ { "coverage": "<val>", "description": "<val>", "limit": "<val>", "deductible": "<val>" } ],
    "exposures": [ { "exposureType": "<val>", "description": "<val>", "value": "<val>" } ],
    "documents": [ { "fileName": "<val>", "fileType": "<val>", "description": "<val>" } ],
    "document_type": "<legacy type>",
    "urgency": "<low|medium|high>",
    "policy_reference": "<val>"
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
