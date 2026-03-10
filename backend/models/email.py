"""Pydantic v2 models for Email data."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class EmailDocument(BaseModel):
    """Cosmos DB document for the 'emails' container."""
    email_id: str = Field(..., description="Unique email identifier (Graph message ID)")
    case_id: str
    message_id: str  # RFC 5322 Message-ID header
    in_reply_to: Optional[str] = None  # In-Reply-To header value
    references: List[str] = Field(default_factory=list)  # References header values
    sender: str
    recipients: List[str] = Field(default_factory=list)
    subject: str
    received_at: datetime
    blob_path: str  # Path in raw-emails blob container
    has_attachments: bool = False
    attachment_count: int = 0
    body_preview: Optional[str] = None  # First 500 chars of body (PII masked)
    body: Optional[str] = None  # Full body text (PII unmasked, cleaned)


class EmailResponse(BaseModel):
    """API response for a single email."""
    email_id: str
    case_id: str
    sender: str
    recipients: List[str]
    subject: str
    received_at: datetime
    has_attachments: bool
    attachment_count: int
    body_preview: Optional[str] = None
    body: Optional[str] = None
