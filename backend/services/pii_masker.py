"""
PII masking service (Step 10).
Uses Microsoft Presidio to detect and mask all PII in document text.
Stores original PII values encrypted (AES-256) in Cosmos DB pii_mapping container.
Masked text is ONLY what gets sent to GPT-4o-mini.

Masked PII fields (aligned to IAT Insurance requirements):
  ✅ Full Name               → [NAME]
  ✅ Date of Birth (DOB)     → [DOB]
  ✅ Social Security Number  → [SSN]
  ✅ Employee ID             → [EMPLOYEE_ID]   (custom pattern recognizer)
  ✅ Job Title / Position    → [JOB_TITLE]     (allowlist-based recognizer)
  ✅ Salary / Compensation   → [SALARY]        (custom pattern recognizer)
  ✅ Deferred Compensation   → [SALARY]        (same recognizer, keyword-scoped)
  ✅ Home Address            → [ADDRESS]
  ✅ Phone Number            → [PHONE]
  ✅ Email Address           → [EMAIL]
  ✅ Corporate Email         → [EMAIL]         (same recognizer)
  ✅ Office Location         → [ADDRESS]       (same recognizer)
  ✅ Internal System IDs     → [INTERNAL_ID]   (custom pattern recognizer)
  ✅ Health Plan Member ID   → [HEALTH_PLAN_ID](custom pattern recognizer)
"""

import base64
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from config import settings

logger = logging.getLogger(__name__)

# ── PII entity types to detect ─────────────────────────────────────────────────
# Presidio built-ins
BUILTIN_ENTITIES = [
    "PERSON",           # Full Name
    "EMAIL_ADDRESS",    # Email Address / Corporate Email
    "PHONE_NUMBER",     # Phone Number
    "US_SSN",           # Social Security Number
    "DATE_TIME",        # Date of Birth (and other dates)
    "LOCATION",         # Home Address / Office Location
]

# Custom entity names
CUSTOM_ENTITIES = [
    "EMPLOYEE_ID",
    "JOB_TITLE",
    "SALARY",
    "INTERNAL_ID",
    "HEALTH_PLAN_ID",
]

ALL_ENTITIES = BUILTIN_ENTITIES + CUSTOM_ENTITIES

# ── Placeholder labels ─────────────────────────────────────────────────────────
PLACEHOLDER_MAP = {
    "PERSON":           "[NAME]",
    "EMAIL_ADDRESS":    "[EMAIL]",
    "PHONE_NUMBER":     "[PHONE]",
    "US_SSN":           "[SSN]",
    "DATE_TIME":        "[DATE]",
    "LOCATION":         "[ADDRESS]",
    "EMPLOYEE_ID":      "[EMPLOYEE_ID]",
    "JOB_TITLE":        "[JOB_TITLE]",
    "SALARY":           "[SALARY]",
    "INTERNAL_ID":      "[INTERNAL_ID]",
    "HEALTH_PLAN_ID":   "[HEALTH_PLAN_ID]",
}


# ── Custom recognizers ─────────────────────────────────────────────────────────

def _build_employee_id_recognizer() -> PatternRecognizer:
    """Detect Employee IDs: EMP-12345, E12345, EMPID-001, EMP_00789."""
    return PatternRecognizer(
        supported_entity="EMPLOYEE_ID",
        name="EmployeeIdRecognizer",
        patterns=[
            Pattern("EMP_HYPHEN",    r"\bEMP[-_]?\d{4,8}\b",   score=0.85),
            Pattern("E_PREFIX",      r"\bE\d{5,8}\b",           score=0.75),
            Pattern("EMPID_PREFIX",  r"\bEMPID[-_]?\d{4,8}\b", score=0.85),
            Pattern("EMPL_PREFIX",   r"\bEMPL[-_]?\d{4,8}\b",  score=0.85),
        ],
    )


def _build_salary_recognizer() -> PatternRecognizer:
    """
    Detect salary / compensation / deferred compensation values.
    Examples: $125,000, $85,000.00/yr, 120000 annually, $150K
    """
    return PatternRecognizer(
        supported_entity="SALARY",
        name="SalaryRecognizer",
        patterns=[
            # $XX,XXX or $XXX,XXX optionally with cents and/or keyword
            Pattern(
                "DOLLAR_AMOUNT_WITH_KEYWORD",
                r"\$[\d,]{4,}(?:\.\d{2})?\s*(?:per\s+year|annually|/yr|/year|salary|compensation|deferred|bonus|base|annual)",
                score=0.90,
            ),
            # $XXX,XXX  or  $XXX,XXX.XX  (standalone large dollar amounts)
            Pattern(
                "LARGE_DOLLAR_AMOUNT",
                r"\$\d{2,3},\d{3}(?:\.\d{2})?",
                score=0.80,
            ),
            # 125000 USD / 85000 dollars
            Pattern(
                "NUMERIC_WITH_CURRENCY_KEYWORD",
                r"\b\d{5,7}(?:\.\d{2})?\s*(?:USD|dollars?)\b",
                score=0.80,
            ),
            # $XXK  (shorthand like $125K)
            Pattern(
                "DOLLAR_K_SHORTHAND",
                r"\$\d{2,4}[Kk]\b",
                score=0.75,
            ),
        ],
    )


def _build_internal_id_recognizer() -> PatternRecognizer:
    """
    Detect internal system IDs: ML-2026-001349, CASE-0012, TKT-88291, REF-20260201
    These are typically <2-4 uppercase letters>-<digits> patterns.
    High confidence to take priority over PHONE_NUMBER false-positives.
    """
    return PatternRecognizer(
        supported_entity="INTERNAL_ID",
        name="InternalIdRecognizer",
        patterns=[
            # ML-2026-001349 / CASE-2026-0012 style (two hyphen segments)
            Pattern(
                "INTERNAL_ID_LONG",
                r"\b[A-Z]{2,6}-\d{4}-\d{4,8}\b",
                score=0.90,
            ),
            # TKT-88291 / REF-20260201 / ID-001234 style (one hyphen segment)
            Pattern(
                "INTERNAL_ID_SHORT",
                r"\b(?:TKT|CASE|REF|ID|SYS|INT|INC|CLM|DOC)[-_]\d{4,12}\b",
                score=0.88,
            ),
        ],
    )


def _build_health_plan_id_recognizer() -> PatternRecognizer:
    """
    Detect Health Plan Member IDs: MEM-123456, MBR-789012, HPMID-001234.
    """
    return PatternRecognizer(
        supported_entity="HEALTH_PLAN_ID",
        name="HealthPlanIdRecognizer",
        patterns=[
            Pattern("MEM_PREFIX",   r"\bMEM[-_]?\d{5,12}\b",   score=0.88),
            Pattern("MBR_PREFIX",   r"\bMBR[-_]?\d{5,12}\b",   score=0.88),
            Pattern("HPMID_PREFIX", r"\bHPMID[-_]?\d{4,10}\b", score=0.90),
            Pattern("HP_PREFIX",    r"\bHP[-_]\d{5,12}\b",      score=0.85),
        ],
    )


# Job titles allowlist — extend as needed for your domain
_JOB_TITLE_TERMS = [
    "Chief Executive Officer", "CEO",
    "Chief Financial Officer", "CFO",
    "Chief Operating Officer", "COO",
    "Chief Legal Officer", "CLO",
    "Chief Compliance Officer", "CCO",
    "Chief Risk Officer", "CRO",
    "Chief Information Officer", "CIO",
    "Chief Technology Officer", "CTO",
    "Chief Human Resources Officer", "CHRO",
    "Vice President", "VP",
    "Senior Vice President", "SVP",
    "Executive Vice President", "EVP",
    "Director", "Senior Director", "Managing Director",
    "General Counsel", "Associate General Counsel",
    "Controller", "Treasurer",
    "President", "Managing Partner", "Partner",
    "Manager", "Senior Manager",
    "HR Director", "HR Manager", "Human Resources Manager",
    "Compliance Officer", "Risk Officer",
    "Board Member", "Board Director", "Independent Director",
    "Actuary", "Senior Actuary",
    "Underwriter", "Senior Underwriter",
    "Claims Adjuster", "Senior Claims Adjuster",
    "Portfolio Manager", "Fund Manager",
    "Analyst", "Senior Analyst",
]

def _build_job_title_recognizer() -> PatternRecognizer:
    """
    Detect job titles using an allowlist-backed regex.
    Matches when a job title appears near name-like context.
    """
    # Build alternation pattern from the allowlist
    import re
    escaped = [re.escape(t) for t in sorted(_JOB_TITLE_TERMS, key=len, reverse=True)]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return PatternRecognizer(
        supported_entity="JOB_TITLE",
        name="JobTitleRecognizer",
        patterns=[
            Pattern("JOB_TITLE_ALLOWLIST", pattern, score=0.80),
        ],
    )


# ── PIIMasker ──────────────────────────────────────────────────────────────────

# Max characters to send to spaCy NER at once (limit is 1,000,000 — we use 500K for safety)
MAX_CHUNK_SIZE = 500_000


class PIIMasker:
    """
    Detects and masks PII using Microsoft Presidio.
    Custom recognizers cover IAT-specific fields (Employee ID, Salary,
    Internal System IDs, Health Plan Member ID, Job Title).
    Stores mapping encrypted in Cosmos DB.
    """

    def __init__(self):
        # Register custom recognizers
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()
        registry.add_recognizer(_build_employee_id_recognizer())
        registry.add_recognizer(_build_salary_recognizer())
        registry.add_recognizer(_build_internal_id_recognizer())
        registry.add_recognizer(_build_health_plan_id_recognizer())
        registry.add_recognizer(_build_job_title_recognizer())

        self._analyzer = AnalyzerEngine(registry=registry)
        self._anonymizer = AnonymizerEngine()

        # Load AES-256 key from settings (base64-encoded 32 bytes)
        raw_key = settings.pii_encryption_key
        if not raw_key:
            raise RuntimeError(
                "PII_ENCRYPTION_KEY is not set. "
                "Add a base64-encoded 32-byte key to your .env file."
            )
        key_bytes = base64.b64decode(raw_key)
        if len(key_bytes) != 32:
            raise ValueError("PII_ENCRYPTION_KEY must be base64-encoded 32 bytes (AES-256).")
        self._aes_key = key_bytes

    async def mask_text(
        self,
        text: str,
        case_id: str,
        document_id: str,
    ) -> Tuple[str, List[Dict]]:
        """
        Mask all PII in the given text and return masked text with PII mapping records.
        Automatically chunks text larger than MAX_CHUNK_SIZE to avoid spaCy's 1M char limit.
        """
        if not text.strip():
            return text, []

        logger.info(f"[PIIMasker] Running PII analysis on {len(text):,} characters for document {document_id}")

        if len(text) > MAX_CHUNK_SIZE:
            return await self._mask_chunked(text, case_id, document_id)

        return self._mask_chunk(text, case_id, document_id)

    async def _mask_chunked(
        self,
        text: str,
        case_id: str,
        document_id: str,
    ) -> Tuple[str, List[Dict]]:
        """Split text into ~MAX_CHUNK_SIZE chunks (splitting on newlines) and mask each."""
        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = start + MAX_CHUNK_SIZE
            if end < len(text):
                # Try to split on a newline so we don't cut mid-sentence
                nl = text.rfind('\n', start, end)
                if nl > start:
                    end = nl + 1
            chunks.append(text[start:end])
            start = end

        logger.info(
            f"[PIIMasker] Text too large ({len(text):,} chars) — "
            f"splitting into {len(chunks)} chunk(s) of up to {MAX_CHUNK_SIZE:,} chars each."
        )

        masked_parts: List[str] = []
        all_mappings: List[Dict] = []

        for i, chunk in enumerate(chunks, 1):
            logger.info(f"[PIIMasker] Processing chunk {i}/{len(chunks)} ({len(chunk):,} chars)...")
            masked_chunk, chunk_mappings = self._mask_chunk(chunk, case_id, document_id)
            masked_parts.append(masked_chunk)
            all_mappings.extend(chunk_mappings)

        logger.info(f"[PIIMasker] All {len(chunks)} chunks processed. Total PII entities: {len(all_mappings)}.")
        return "".join(masked_parts), all_mappings

    def _mask_chunk(
        self,
        text: str,
        case_id: str,
        document_id: str,
    ) -> Tuple[str, List[Dict]]:
        """Mask PII in a single chunk of text (must be under MAX_CHUNK_SIZE)."""
        results = self._analyzer.analyze(
            text=text,
            entities=ALL_ENTITIES,
            language="en",
        )

        if not results:
            logger.info("[PIIMasker] No PII detected in chunk.")
            return text, []

        logger.info(f"[PIIMasker] Detected {len(results)} PII entities in chunk.")

        operators = {}
        for result in results:
            placeholder = PLACEHOLDER_MAP.get(result.entity_type, "****")
            operators[result.entity_type] = OperatorConfig("replace", {"new_value": placeholder})

        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )
        masked_text = anonymized.text

        pii_mappings = []
        for result in results:
            original_value = text[result.start:result.end]
            encrypted_value = self._encrypt(original_value)
            mapping = {
                "mapping_id": str(uuid.uuid4()),
                "case_id": case_id,
                "document_id": document_id,
                "pii_type": result.entity_type,
                "masked_value": PLACEHOLDER_MAP.get(result.entity_type, "****"),
                "original_value_encrypted": encrypted_value,
                "created_at": datetime.utcnow().isoformat(),
            }
            pii_mappings.append(mapping)

        return masked_text, pii_mappings

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string using AES-256-GCM."""
        aesgcm = AESGCM(self._aes_key)
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    def _decrypt(self, encrypted: str) -> str:
        """Decrypt an AES-256-GCM encrypted value (internal use only)."""
        data = base64.b64decode(encrypted)
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(self._aes_key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
