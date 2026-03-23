import json
import logging
import os
from typing import Dict

from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models.classification import ClassificationResult, KeyFields
from models.case import ClassificationCategory

logger = logging.getLogger(__name__)

BASE_SYSTEM_PROMPT = """You are an expert insurance document classification AI. 
You are analyzing a Conversation Thread between multiple parties (Brokers, Underwriters, Insureds). 
The content may contain multiple emails and attachments, separated by [Source: ...]. 
Your goal is to synthesize the entire thread to identify the final intent, latest names, dates, and terms. 

THOUGHT PROCESS:
Before providing the final JSON, you must follow these steps:
1. Identify the core intent of the most recent communication in the thread.
2. List all participants and resolve their roles (Underwriter, Broker, Insured, etc.).
3. **Extraction Audit**: For every field in the extraction schema, locate the value and note which Source (Email # or Attachment Name) it came from.
4. **Conflict Resolution**: If a field has conflicting values across sources, determine the most authoritative one (e.g., a formal PDF Policy usually beats an informal email mention).
5. Compare your findings against the Classification Rules below.
6. **Hallucination Check**: Ensure no values were "guessed" or "invented" just to fill the schema. 

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

Extraction Rules:
- **Accuracy First**: Only extract values that are explicitly present or can be strongly inferred. 
- **Multi-Source Synthesis**: You are provided with multiple email threads and document contents. If a field (like Policy Number) appears in both an email and a PDF, prefer the most formal one or the latest one if they conflict.
- **Nested Objects**: For "agent" and "insured", fill in all sub-fields (email, phone, etc.) by looking across all available text parts.
- **Agent Identification & Mandatory Information**: The "agent" (also called Broker or Producer) is the professional intermediary sending the submission. You MUST extract their **Agent Email** and **Agent Phone**. 
- **Signature Scanning**: These contact details are almost always found in the **email signature block** (at the very bottom of the individual emails) of the sender. Scan the entire document/email thread to find these signatures. Do not return "NA" for `agent_email` or `agent_phone` if a signature block exists anywhere in the thread.

Confidence Scoring Rules:
- **Be Critical**: Provide a confidence score (0.0 to 1.0) for every field extracted in `key_fields`.
- **Lower Confidence on Doubt**: If a value is inferred, blurry in a document, or comes from a conflicting source, you MUST lower the score below 0.7.
- **Ambiguity**: If you are making an "educated guess" (e.g., date format is unclear), use 0.4 - 0.6.
- **Null Fields**: If a field is not found (`null`), set its confidence in `field_confidence` to **0.0** or omit it entirely.
- **High Certainty**: Only use 0.95+ for values that are explicitly and clearly present in the source text.

Extraction Instructions:
{extraction_instructions}
{pii_masking_notice}

Respond ONLY with valid JSON in this exact format:
{{
  "reasoning": "<Detailed step-by-step chain of thought: 1. Core intent. 2. Participant roles. 3. Classification justification. 4. Extraction Walk-through: explain where you found key data points and how you resolved any conflicting values between emails and documents.>",
  "classification_category": "<category name>",
  "confidence_score": <0.0 to 1.0>,
  "summary": "<2-3 sentence summary>",
  "key_fields": {{
{key_fields_json}
  }},
  "field_confidence": {{
    "<field_key>": <0.0 to 1.0>,
    ...
  }},
  "requires_human_review": <true if confidence < 0.75 or any critical field confidence < 0.6, else false>
}}"""


class Classifier:
    """Azure OpenAI GPT-4o-mini classifier for insurance email triage."""

    def __init__(self):
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_deployment
        self._confidence_threshold = settings.classification_confidence_threshold
        self._load_schema()

    def _load_schema(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "config", "extraction_schema.json")
        try:
            with open(schema_path, "r") as f:
                self._schema = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load extraction schema from {schema_path}: {e}")
            self._schema = {"fields": []}

    def _generate_prompt(self, pii_masking_notice: str = "") -> str:
        instructions = []
        kf_lines = []

        # Default complex fields
        instructions.append("- insured: { \"name\": \"...\", \"address\": \"...\" }")
        instructions.append("- agent: { \"agencyName\": \"...\", \"name\": \"...\", \"email\": \"...\", \"phone\": \"...\" }")
        instructions.append("- coverages: An array of objects: { \"coverage\": \"...\", \"coverageDescription\": \"...\", \"limit\": \"...\", \"deductible\": \"...\" }")
        instructions.append("- exposures: An array of objects: { \"exposureType\": \"...\", \"exposureDescription\": \"...\", \"value\": \"...\" }")
        instructions.append("- documents: An array of objects indicating the attached documents found in the text.")

        kf_lines.append('    "name": "<Insured Business Name>",')
        kf_lines.append('    "insured": { "name": "<val>", "address": "<val>" },')
        kf_lines.append('    "agent": { "agencyName": "<val>", "name": "<val>" },')
        kf_lines.append('    "agent_email": "<MANDATORY: extract from sender signature>",')
        kf_lines.append('    "agent_phone": "<MANDATORY: extract from sender signature>",')
        kf_lines.append('    "submission_description": "<summary>",')
        kf_lines.append('    "coverages": [ { "coverage": "<val>", "coverageDescription": "<val>", "limit": "<val>", "deductible": "<val>" } ],')
        kf_lines.append('    "exposures": [ { "exposureType": "<val>", "exposureDescription": "<val>", "value": "<val>" } ],')
        kf_lines.append('    "documents": [ { "fileName": "<val>", "fileType": "<val>", "documentDescription": "<val>" } ],')

        # Dynamically add rest of fields from schema
        simple_fields = []
        for f in self._schema.get("fields", []):
            if f["key"] in ["insured", "agent", "coverages", "exposures", "documents", "name"]:
                continue
            
            # Key/Value description for AI
            simple_fields.append(f["key"])
            kf_lines.append(f'    "{f["key"]}": "<val>",')
            
            # Add enriched context for each field (additive)
            desc = f.get("description", "Standard extraction")
            aliases = ", ".join(f.get("aliases", []))
            alias_text = f" (aliases: {aliases})" if aliases else ""
            instructions.append(f"- {f['key']}: {desc}{alias_text}")
        
        if simple_fields:
            instructions.append(f"- {', '.join(simple_fields)}: Standard string extraction as defined in the schema.")

        # Add legacy/standard fields
        kf_lines.append('    "document_type": "<legacy type>",')
        kf_lines.append('    "urgency": "<low|medium|high>",')
        kf_lines.append('    "policy_reference": "<val>"')

        return BASE_SYSTEM_PROMPT.format(
            extraction_instructions="\n".join(instructions),
            pii_masking_notice=pii_masking_notice,
            key_fields_json="\n".join(kf_lines)
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def classify(self, masked_text: str, is_masked: bool = True) -> Dict:
        """
        Classify an email/document using GPT-4o-mini.

        Args:
            masked_text: Text content of the email and its documents (optionally masked).
            is_masked: Whether PII has been masked in the input text.

        Returns:
            Parsed classification result dictionary.

        Raises:
            ValueError: If GPT returns invalid JSON.
            Exception: If API call fails after retries.
        """
        logger.info(f"Sending {len(masked_text)} chars to GPT-4o-mini for classification.")
        try:
            # Generate the dynamic prompt from the current schema
            pii_masking_notice = ""
            if is_masked:
                pii_masking_notice = "\nNOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders. If a value is masked, return the placeholder."
            
            system_prompt = self._generate_prompt(pii_masking_notice)
            
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Email content:\n\n{masked_text[:32000]}"},
                ],
                temperature=0.1,
                max_tokens=16384,
                response_format={"type": "json_object"},
            )
            raw_json = response.choices[0].message.content
            result = json.loads(raw_json)
            self._validate_result(result)
            logger.info(
                f"Classification result: {result.get('classification_category')} "
                f"(confidence: {result.get('confidence_score')})"
            )
            # Map field_confidence to key_fields object for Pydantic
            if "field_confidence" in result and "key_fields" in result:
                result["key_fields"]["field_confidence"] = result["field_confidence"]
            
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

        # Enforce requires_human_review based on threshold or sensitive categories
        is_low_confidence = score < self._confidence_threshold
        category = result.get("classification_category", "")
        
        # These categories ALWAYS require human eyes for safety/business reasons
        is_sensitive_category = category in [
            "Spam/Irrelevant",
            "Complaint/Escalation",
            "Regulatory/Legal"
        ]
        
        result["requires_human_review"] = is_low_confidence or is_sensitive_category
