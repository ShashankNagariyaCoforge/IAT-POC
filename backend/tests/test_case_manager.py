"""
Unit tests for the case manager service (chain detection).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.case_manager import CaseManager, _strip_reply_prefix


def test_strip_reply_prefix():
    assert _strip_reply_prefix("RE: Hello") == "Hello"
    assert _strip_reply_prefix("FW: Hello") == "Hello"
    assert _strip_reply_prefix("RE: FW: Hello") == "Hello"
    assert _strip_reply_prefix("Hello") == "Hello"


@pytest.mark.asyncio
async def test_chain_via_in_reply_to():
    """Chain detection: In-Reply-To match returns existing case_id."""
    mock_cosmos = AsyncMock()
    mock_cosmos.find_email_by_message_id.return_value = {
        "email_id": "e1",
        "case_id": "IAT-2026-000001",
        "message_id": "existing-msg-id@test.com",
    }
    mock_cosmos.get_case.return_value = {
        "case_id": "IAT-2026-000001",
        "email_count": 1,
    }
    mock_cosmos._get_container = AsyncMock()
    container_mock = AsyncMock()
    mock_cosmos._get_container.return_value = container_mock

    mgr = CaseManager(mock_cosmos)
    email_data = {
        "internetMessageId": "new-msg@test.com",
        "internetMessageHeaders": [
            {"name": "In-Reply-To", "value": "<existing-msg-id@test.com>"},
            {"name": "References", "value": ""},
        ],
        "subject": "RE: Policy Query",
        "from": {"emailAddress": {"address": "user@example.com"}},
    }
    result = await mgr.resolve_case(email_data)
    assert result == "IAT-2026-000001"


@pytest.mark.asyncio
async def test_new_case_created_when_no_chain():
    """A new case is created when no chain match is found."""
    mock_cosmos = AsyncMock()
    mock_cosmos.find_email_by_message_id.return_value = None
    mock_cosmos.find_case_by_subject.return_value = None
    mock_cosmos.get_next_case_sequence.return_value = 1
    mock_cosmos.create_case = AsyncMock()

    mgr = CaseManager(mock_cosmos)
    email_data = {
        "internetMessageId": "fresh@test.com",
        "internetMessageHeaders": [],
        "subject": "New Policy Application",
        "from": {"emailAddress": {"address": "newuser@example.com"}},
    }
    result = await mgr.resolve_case(email_data)
    assert result.startswith("IAT-")
    assert "000001" in result
    mock_cosmos.create_case.assert_called_once()
