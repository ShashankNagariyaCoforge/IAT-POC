"""
Unit tests for the classifier service (GPT-4o-mini).
Mocks OpenAI API calls — no real Azure calls.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def classifier():
    with patch("services.classifier.settings") as mock_settings:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_api_version = "2024-08-01-preview"
        mock_settings.azure_openai_deployment = "gpt-4o-mini"
        mock_settings.classification_confidence_threshold = 0.75
        with patch("services.classifier.AsyncAzureOpenAI"):
            from services.classifier import Classifier
            c = Classifier()
            return c


@pytest.mark.asyncio
async def test_classify_returns_structured_result(classifier):
    """Test that a valid GPT response is parsed correctly."""
    mock_response = {
        "classification_category": "New",
        "confidence_score": 0.92,
        "summary": "A new policy application was submitted.",
        "key_fields": {
            "document_type": "application_form",
            "urgency": "medium",
            "policy_reference": "[POLICY_NUMBER]",
            "claim_type": None,
        },
        "requires_human_review": False,
    }
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(mock_response)
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    classifier._client.chat.completions.create = AsyncMock(return_value=mock_completion)

    result = await classifier.classify("Test masked email content here.")
    assert result["classification_category"] == "New"
    assert result["confidence_score"] == 0.92
    assert result["requires_human_review"] is False


@pytest.mark.asyncio
async def test_classify_low_confidence_flags_review(classifier):
    """Low confidence score should set requires_human_review=True."""
    mock_response = {
        "classification_category": "Query/General",
        "confidence_score": 0.65,
        "summary": "Uncertain classification.",
        "key_fields": {"document_type": "unknown", "urgency": "low", "policy_reference": None, "claim_type": None},
        "requires_human_review": False,  # GPT says false, but we override based on threshold
    }
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(mock_response)
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    classifier._client.chat.completions.create = AsyncMock(return_value=mock_completion)

    result = await classifier.classify("Unclear content.")
    # Classifier enforces requires_human_review for confidence < 0.75
    assert result["requires_human_review"] is True
