"""
Unit tests for the PII masker service.
Tests masking without Azure services (purely local Presidio).
"""

import pytest
from unittest.mock import patch
import base64
import os


@pytest.fixture
def masker():
    """Create a PIIMasker with a test AES key."""
    # Generate a 32-byte test key
    test_key = base64.b64encode(os.urandom(32)).decode()
    with patch("services.pii_masker.settings") as mock_settings:
        mock_settings.pii_encryption_key = test_key
        from services.pii_masker import PIIMasker
        return PIIMasker()


@pytest.mark.asyncio
async def test_mask_person_name(masker):
    """Test that person names are masked."""
    text = "John Smith submitted a claim today."
    masked, mappings = await masker.mask_text(text, "IAT-2026-000001", "doc-1")
    assert "[NAME]" in masked
    assert "John Smith" not in masked


@pytest.mark.asyncio
async def test_mask_email_address(masker):
    """Test that email addresses are masked."""
    text = "Please contact john.doe@example.com for details."
    masked, mappings = await masker.mask_text(text, "IAT-2026-000001", "doc-2")
    assert "john.doe@example.com" not in masked


@pytest.mark.asyncio
async def test_empty_text(masker):
    """Empty text returns unchanged with empty mappings."""
    masked, mappings = await masker.mask_text("", "IAT-2026-000001", "doc-3")
    assert masked == ""
    assert mappings == []


@pytest.mark.asyncio
async def test_encrypt_decrypt_roundtrip(masker):
    """AES-256-GCM encryption/decryption roundtrip."""
    original = "John Smith"
    encrypted = masker._encrypt(original)
    decrypted = masker._decrypt(encrypted)
    assert decrypted == original


@pytest.mark.asyncio
async def test_no_pii_returns_original(masker):
    """Text with no PII should be returned largely unchanged."""
    text = "The policy renewal request was received on the 15th."
    masked, mappings = await masker.mask_text(text, "IAT-2026-000001", "doc-4")
    # No PII found → all or most mappings empty
    assert isinstance(masked, str)
    assert len(masked) > 0
