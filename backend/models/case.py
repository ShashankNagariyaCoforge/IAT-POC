"""Pydantic v2 models for Case data."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    """Case lifecycle statuses as defined in PRD section 9.3."""
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    CLASSIFIED = "CLASSIFIED"
    PENDING_REVIEW = "PENDING_REVIEW"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    BLOCKED_SAFETY = "BLOCKED_SAFETY"
    NEEDS_REVIEW_SAFETY = "NEEDS_REVIEW_SAFETY"
    UPDATED = "UPDATED"


class ContentSafetyResult(BaseModel):
    hate_severity: int = 0
    self_harm_severity: int = 0
    sexual_severity: int = 0
    violence_severity: int = 0



class ClassificationCategory(str, Enum):
    """8 classification categories as defined in PRD section 8.1."""
    NEW = "New"
    RENEWAL = "Renewal"
    QUERY_GENERAL = "Query/General"
    FOLLOW_UP = "Follow-up"
    COMPLAINT_ESCALATION = "Complaint/Escalation"
    REGULATORY_LEGAL = "Regulatory/Legal"
    DOCUMENTATION_EVIDENCE = "Documentation/Evidence"
    SPAM_IRRELEVANT = "Spam/Irrelevant"
    BOR = "BOR"


class CaseDocument(BaseModel):
    """Cosmos DB document for the 'cases' container."""
    case_id: str = Field(..., description="Case ID e.g. IAT-2026-000001")
    status: CaseStatus = CaseStatus.RECEIVED
    classification_category: Optional[ClassificationCategory] = None
    confidence_score: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    subject: str
    sender: str
    email_count: int = 1
    requires_human_review: bool = False
    summary: Optional[str] = None
    content_safety_result: Optional[ContentSafetyResult] = None
    pipeline_step: Optional[str] = None


class CaseResponse(BaseModel):
    """API response model for a case (used in list and detail views)."""
    case_id: str
    status: CaseStatus
    classification_category: Optional[ClassificationCategory] = None
    confidence_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    subject: str
    sender: str
    email_count: int
    requires_human_review: bool
    summary: Optional[str] = None
    content_safety_result: Optional[ContentSafetyResult] = None
    pipeline_step: Optional[str] = None


class CaseListResponse(BaseModel):
    """Paginated case list response."""
    cases: list[CaseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
