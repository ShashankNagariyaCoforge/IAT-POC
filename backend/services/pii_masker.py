"""
PII masking service (Step 10).
Uses Microsoft Presidio to detect and mask all PII in document text.
Stores original PII values encrypted (AES-256) in Cosmos DB pii_mapping container.
Masked text is ONLY what gets sent to GPT-4o-mini.
"""

import base64
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from config import settings

logger = logging.getLogger(__name__)

# PII entity types to detect
PII_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "DATE_TIME",
    "LOCATION",
    "URL",
    "IP_ADDRESS",
    "IBAN_CODE",
    "CREDIT_CARD",
    "MEDICAL_LICENSE",
    "UK_NHS",
    "NRP",  # National Registration Patterns
]

# Placeholder labels for each entity type
_PLACEHOLDER_MAP = {
    "PERSON": "[NAME]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "PHONE_NUMBER": "[PHONE]",
    "US_SSN": "[SSN]",
    "DATE_TIME": "[DOB]",
    "LOCATION": "[ADDRESS]",
    "URL": "[URL]",
    "IP_ADDRESS": "[IP]",
    "IBAN_CODE": "[IBAN]",
    "CREDIT_CARD": "[CARD]",
    "MEDICAL_LICENSE": "[POLICY_NUMBER]",
    "UK_NHS": "[POLICY_NUMBER]",
    "NRP": "[POLICY_NUMBER]",
}


class PIIMasker:
    """Detects and masks PII using Microsoft Presidio. Stores mapping encrypted in Cosmos."""

    def __init__(self):
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()
        # Load AES-256 key from settings (base64-encoded 32 bytes)
        key_bytes = base64.b64decode(settings.pii_encryption_key)
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

        Args:
            text: Original text containing potential PII.
            case_id: Associated case ID (stored with mapping).
            document_id: Associated document ID.

        Returns:
            Tuple of (masked_text, list_of_pii_mapping_dicts).
        """
        if not text.strip():
            return text, []

        logger.info(f"Running PII analysis on {len(text)} characters for document {document_id}")

        # Analyze text for PII
        results = self._analyzer.analyze(
            text=text,
            entities=PII_ENTITIES,
            language="en",
        )

        if not results:
            logger.info("No PII detected in document text.")
            return text, []

        logger.info(f"Detected {len(results)} PII entities.")

        pii_mappings = []
        # Build operator config to replace each entity with typed placeholder
        operators = {}
        for result in results:
            placeholder = _PLACEHOLDER_MAP.get(result.entity_type, "[REDACTED]")
            operators[result.entity_type] = OperatorConfig("replace", {"new_value": placeholder})

        # Anonymize
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )
        masked_text = anonymized.text

        # Build PII mapping records (original values encrypted)
        for result in results:
            original_value = text[result.start:result.end]
            encrypted_value = self._encrypt(original_value)
            mapping = {
                "mapping_id": str(uuid.uuid4()),
                "case_id": case_id,
                "document_id": document_id,
                "pii_type": result.entity_type,
                "masked_value": _PLACEHOLDER_MAP.get(result.entity_type, "[REDACTED]"),
                "original_value_encrypted": encrypted_value,
                "created_at": datetime.utcnow().isoformat(),
            }
            pii_mappings.append(mapping)

        logger.info(f"PII masking complete. {len(pii_mappings)} values encrypted and stored.")
        return masked_text, pii_mappings

    def _encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string using AES-256-GCM.

        Args:
            plaintext: The original PII value to encrypt.

        Returns:
            Base64-encoded ciphertext (nonce + ciphertext).
        """
        aesgcm = AESGCM(self._aes_key)
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    def _decrypt(self, encrypted: str) -> str:
        """
        Decrypt an AES-256-GCM encrypted value (for internal use only, never in API).

        Args:
            encrypted: Base64-encoded nonce + ciphertext.

        Returns:
            Original plaintext string.
        """
        data = base64.b64decode(encrypted)
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(self._aes_key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
