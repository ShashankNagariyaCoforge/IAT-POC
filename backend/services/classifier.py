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

# ── Prompt 1: Classification only ─────────────────────────────────────────────

CLASSIFICATION_SYSTEM_PROMPT = """You are an expert insurance email triage AI.
You are analyzing a conversation thread between multiple parties (Brokers, Underwriters, Insureds).
The content may contain multiple emails and attachments, separated by [Source: ...].
Your ONLY job in this step is to classify the thread — do NOT extract field values.

THOUGHT PROCESS:
1. Identify the core intent of the most recent communication in the thread.
2. List all participants and resolve their roles (Underwriter, Broker, Insured, etc.).
3. Compare your findings against the Classification Rules below.
4. Determine the single best-fit category.

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
- If the latest reply just says "Thank you" or "Received", distinguish it from the core request but don't ignore the context of the thread.

{pii_masking_notice}

Respond ONLY with valid JSON in this exact format:
{{
  "reasoning": "<Detailed step-by-step chain of thought: 1. Core intent. 2. Participant roles. 3. Classification justification.>",
  "classification_category": "<category name>",
  "confidence_score": <0.0 to 1.0>,
  "summary": "<2-3 sentence summary of the thread>",
  "requires_human_review": <true if confidence < 0.75 or category is Spam/Irrelevant, Complaint/Escalation, or Regulatory/Legal, else false>
}}"""

# ── Prompt 2: Extraction only ──────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are an expert insurance data extraction AI.
You are analyzing a conversation thread between multiple parties (Brokers, Underwriters, Insureds).
The content contains sections labeled [Source: ...] — each label identifies where the following text came from.
Labels look like: [Source: Email from broker@abc.com] or [Source: Attachment claim_form.pdf]

The thread has already been classified as: {classification_category}

Your ONLY job is to extract the specific field values listed below.
Do NOT re-classify. Do NOT add fields that are not in the schema.

EXTRACTION RULES:
- **Accuracy First**: Only extract values that are explicitly present or can be strongly inferred. Never guess.
- **Multi-Source Synthesis**: If a field appears in both an email and a PDF, prefer the most formal or latest source.
- **Nested Objects**: For "agent" and "insured", fill in all sub-fields by looking across all text parts.
- **Agent Identification**: The agent (also called Broker or Producer) is the professional intermediary sending the submission.
  Extract their Agent Email and Agent Phone from the email signature block at the bottom of emails.
  Do NOT return "NA" for agent_email or agent_phone if a signature block exists anywhere in the thread.
- **Signature Scanning**: Scan the entire document/email thread carefully for signature blocks containing contact details.
- **Hallucination Check**: Ensure no values were guessed or invented just to fill the schema. If not found, use null.

TRACEABILITY RULES (critical — follow exactly):
- For every field you extract, you MUST also return:
  - raw_text: the EXACT verbatim phrase from the source (10-25 surrounding words of context).
    Copy word-for-word. Never paraphrase. Include the field label/heading if visible.
  - source_document: the filename from the [Source: Attachment <filename>] label where you found it,
    OR the string "email" if you found it in a [Source: Email from ...] section.
- If a field is null (not found), omit it from field_traceability entirely.

FOR ARRAY FIELDS (coverages, exposures) — use dot notation per element per sub-field:
  "coverages.0.coverage": {{ "raw_text": "...", "source_document": "..." }},
  "coverages.0.limit":    {{ "raw_text": "...", "source_document": "..." }},
  "coverages.0.deductible": {{ "raw_text": "...", "source_document": "..." }},
  "coverages.0.coverageDescription": {{ "raw_text": "...", "source_document": "..." }},
  "coverages.1.coverage": {{ "raw_text": "...", "source_document": "..." }},
  ... (one entry per extracted sub-field per array element, 0-indexed)

  "exposures.0.exposureType":        {{ "raw_text": "...", "source_document": "..." }},
  "exposures.0.value":               {{ "raw_text": "...", "source_document": "..." }},
  "exposures.0.exposureDescription": {{ "raw_text": "...", "source_document": "..." }},
  ... (same pattern for each exposure element)

  Only include entries for sub-fields that actually have an extracted value.

CONFIDENCE SCORING:
- 0.95+ : Value is explicitly and clearly present in the source text
- 0.75-0.94: Value is clearly present but from a less formal source
- 0.50-0.74: Value is inferred or from a conflicting/ambiguous source
- < 0.50: Educated guess — should be null instead unless strongly implied
- 0.0 or omit: Field not found

{extraction_instructions}

{pii_masking_notice}

Respond ONLY with valid JSON in this exact format:
{{
  "key_fields": {{
{key_fields_json}
  }},
  "field_confidence": {{
    "<field_key>": <0.0 to 1.0>,
    ...
  }},
  "field_traceability": {{
    "<field_key>": {{
      "raw_text": "<exact verbatim phrase 10-25 words>",
      "source_document": "<filename.pdf or email>"
    }},
    ...
  }}
}}"""


class Classifier:
    """Azure OpenAI GPT-4o classifier for insurance email triage.

    Uses two separate LLM calls:
    1. classify()  — determines category, confidence, summary (no field extraction)
    2. extract()   — extracts key_fields given the classification context
    """

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

    def _build_extraction_prompt(self, classification_category: str, pii_masking_notice: str = "") -> str:
        """Build the extraction system prompt with field instructions and JSON schema."""
        instructions = []
        kf_lines = []

        # Fixed complex fields
        instructions.append('- insured: { "name": "...", "address": "..." }')
        instructions.append('- agent: { "agencyName": "...", "name": "...", "email": "...", "phone": "..." }')
        instructions.append('- coverages: An array of objects: { "coverage": "...", "coverageDescription": "...", "limit": "...", "deductible": "..." }')
        instructions.append('- exposures: An array of objects: { "exposureType": "...", "exposureDescription": "...", "value": "..." }')
        instructions.append('- documents: An array of objects indicating the attached documents found in the text.')

        kf_lines.append('    "name": "<Insured Business Name>",')
        kf_lines.append('    "insured": { "name": "<val>", "address": "<val>" },')
        kf_lines.append('    "agent": { "agencyName": "<val>", "name": "<val>" },')
        kf_lines.append('    "agent_email": "<MANDATORY: extract from sender signature>",')
        kf_lines.append('    "agent_phone": "<MANDATORY: extract from sender signature>",')
        kf_lines.append('    "submission_description": "<summary>",')
        kf_lines.append('    "coverages": [ { "coverage": "<val>", "coverageDescription": "<val>", "limit": "<val>", "deductible": "<val>" } ],')
        kf_lines.append('    "exposures": [ { "exposureType": "<val>", "exposureDescription": "<val>", "value": "<val>" } ],')
        kf_lines.append('    "documents": [ { "fileName": "<val>", "fileType": "<val>", "documentDescription": "<val>" } ],')

        # Dynamic fields from schema
        simple_fields = []
        for f in self._schema.get("fields", []):
            if f["key"] in ["insured", "agent", "coverages", "exposures", "documents", "name"]:
                continue
            simple_fields.append(f["key"])
            kf_lines.append(f'    "{f["key"]}": "<val>",')
            desc = f.get("description", "Standard extraction")
            aliases = ", ".join(f.get("aliases", []))
            alias_text = f" (aliases: {aliases})" if aliases else ""
            instructions.append(f"- {f['key']}: {desc}{alias_text}")

        if simple_fields:
            instructions.append(f"- {', '.join(simple_fields)}: Standard string extraction as defined in the schema.")

        # Legacy fields
        kf_lines.append('    "document_type": "<legacy type>",')
        kf_lines.append('    "urgency": "<low|medium|high>",')
        kf_lines.append('    "policy_reference": "<val>"')

        return EXTRACTION_SYSTEM_PROMPT.format(
            classification_category=classification_category,
            extraction_instructions="\n".join(instructions),
            pii_masking_notice=pii_masking_notice,
            key_fields_json="\n".join(kf_lines),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def classify(self, text: str, is_masked: bool = True) -> Dict:
        """
        Step 1: Classify the email thread (category, confidence, summary).
        Does NOT extract key field values — that is done separately in extract().

        Returns a dict with: reasoning, classification_category, confidence_score,
        summary, requires_human_review.
        """
        logger.info(f"[Classifier] Step 1 — Classification. Input: {len(text)} chars.")

        pii_masking_notice = ""
        if is_masked:
            pii_masking_notice = "\nNOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders."

        system_prompt = CLASSIFICATION_SYSTEM_PROMPT.format(pii_masking_notice=pii_masking_notice)

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Email thread:\n\n{text[:32000]}"},
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            self._validate_classification(result)
            logger.info(
                f"[Classifier] Step 1 done — category={result.get('classification_category')} "
                f"confidence={result.get('confidence_score')}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[Classifier] Step 1 returned invalid JSON: {e}")
            raise ValueError(f"Classification returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"[Classifier] Step 1 API call failed: {e}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def extract(self, text: str, classification_category: str, is_masked: bool = True) -> Dict:
        """
        Step 2: Extract key fields from the email thread.
        Receives the classification_category from Step 1 as context.

        Returns a dict with: key_fields, field_confidence.
        """
        logger.info(f"[Classifier] Step 2 — Extraction for category='{classification_category}'. Input: {len(text)} chars.")

        pii_masking_notice = ""
        if is_masked:
            pii_masking_notice = "\nNOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders. If a value is masked, return the placeholder as-is."

        system_prompt = self._build_extraction_prompt(classification_category, pii_masking_notice)

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Email thread:\n\n{text[:32000]}"},
                ],
                temperature=0.1,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            logger.info(f"[Classifier] Step 2 done — extracted {len(result.get('key_fields', {}))} fields.")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[Classifier] Step 2 returned invalid JSON: {e}")
            raise ValueError(f"Extraction returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"[Classifier] Step 2 API call failed: {e}", exc_info=True)
            raise

    def _validate_classification(self, result: dict) -> None:
        """Validate that the classification result has required fields."""
        required = ["reasoning", "classification_category", "confidence_score", "summary"]
        for field in required:
            if field not in result:
                raise ValueError(f"Classification result missing required field: {field}")

        score = float(result["confidence_score"])
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Invalid confidence_score: {score}")

        # Enforce requires_human_review
        is_low_confidence = score < self._confidence_threshold
        category = result.get("classification_category", "")
        is_sensitive_category = category in [
            "Spam/Irrelevant",
            "Complaint/Escalation",
            "Regulatory/Legal",
        ]
        result["requires_human_review"] = is_low_confidence or is_sensitive_category
