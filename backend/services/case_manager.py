"""
Case manager service (Step 13).
Handles case creation and email chain detection.
Chain detection priority:
  1. In-Reply-To header match against known Message-IDs
  2. References header match
  3. Subject line fallback (RE:/FW: stripped)
  4. No match → create new case
"""

import logging
import re
from datetime import datetime, timezone

from models.case import CaseDocument, CaseStatus
from services.cosmos_db import CosmosDBService

logger = logging.getLogger(__name__)

# Strip RE: / FW: / Fwd: prefixes for subject matching
_SUBJECT_STRIP_RE = re.compile(r"^(RE|FW|FWD|AW|SV|Re|Fw|Fwd)\s*:\s*", re.IGNORECASE)

# Case ID format: IAT-YYYY-XXXXXX
_CASE_ID_FORMAT = "IAT-{year}-{seq:06d}"


def _strip_reply_prefix(subject: str) -> str:
    """Remove RE:/FW: prefixes from a subject line for comparison."""
    while True:
        stripped = _SUBJECT_STRIP_RE.sub("", subject).strip()
        if stripped == subject:
            break
        subject = stripped
    return subject


class CaseManager:
    """Manages case creation and email chain detection."""

    def __init__(self, cosmos: CosmosDBService):
        self._cosmos = cosmos

    async def resolve_case(self, email_data: dict) -> str:
        """
        Determine the case ID for an incoming email.
        Creates a new case if none is matched.

        Args:
            email_data: Full Graph API email message object.

        Returns:
            Case ID string (existing or newly created).
        """
        internet_headers = {
            h["name"].lower(): h["value"]
            for h in email_data.get("internetMessageHeaders", [])
        }

        in_reply_to = internet_headers.get("in-reply-to", "").strip("<>")
        references_raw = internet_headers.get("references", "")
        message_id = internet_headers.get("message-id", "").strip("<>")
        subject = email_data.get("subject", "")
        
        # Handle sender extracting for both raw Graph API dict and simplified Blob string
        raw_sender = email_data.get("from", "")
        if isinstance(raw_sender, dict):
            sender = raw_sender.get("emailAddress", {}).get("address", "")
        else:
            sender = str(raw_sender)

        # ── 1. In-Reply-To match ──────────────────────────────────────────────
        if in_reply_to:
            existing = await self._cosmos.find_email_by_message_id(in_reply_to)
            if existing:
                case_id = existing["case_id"]
                logger.info(f"[CaseManager] Chained via In-Reply-To → case {case_id}")
                await self._increment_email_count(case_id)
                return case_id

        # ── 2. References header match ────────────────────────────────────────
        references = [r.strip().strip("<>") for r in references_raw.split() if r.strip()]
        for ref in references:
            existing = await self._cosmos.find_email_by_message_id(ref)
            if existing:
                case_id = existing["case_id"]
                logger.info(f"[CaseManager] Chained via References → case {case_id}")
                await self._increment_email_count(case_id)
                return case_id

        # ── 3. Subject line fallback ───────────────────────────────────────────
        clean_subject = _strip_reply_prefix(subject)
        if clean_subject and (subject != clean_subject):
            # Only use this fallback if there WAS a RE:/FW: prefix
            existing_case_id = await self._cosmos.find_case_by_subject(clean_subject)
            if existing_case_id:
                logger.info(f"[CaseManager] Chained via subject fallback → case {existing_case_id}")
                await self._increment_email_count(existing_case_id)
                return existing_case_id

        # ── 4. No match → create a new case ───────────────────────────────────
        case_id = await self._create_new_case(subject=clean_subject or subject, sender=sender)
        return case_id

    async def _create_new_case(self, subject: str, sender: str) -> str:
        """
        Create a new Case in Cosmos DB with auto-incrementing ID.

        Args:
            subject: Email subject (cleaned, no RE:/FW:).
            sender: Sender email address.

        Returns:
            New case ID string.
        """
        year = datetime.now(timezone.utc).year
        seq = await self._cosmos.get_next_case_sequence()
        case_id = _CASE_ID_FORMAT.format(year=year, seq=seq)

        case = CaseDocument(
            case_id=case_id,
            status=CaseStatus.RECEIVED,
            subject=subject,
            sender=sender,
            email_count=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await self._cosmos.create_case(case)
        logger.info(f"[CaseManager] Created new case: {case_id}")
        return case_id

    async def _increment_email_count(self, case_id: str) -> None:
        """Increment the email_count on an existing case."""
        case = await self._cosmos.get_case(case_id)
        if case:
            new_count = case.get("email_count", 1) + 1
            status = CaseStatus(case.get("status", CaseStatus.RECEIVED.value))
            await self._cosmos.update_case_status(
                case_id, 
                status, 
                email_count=new_count
            )
