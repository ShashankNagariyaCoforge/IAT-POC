"""Pydantic v2 models for Classification results."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from models.case import ClassificationCategory


class KeyFields(BaseModel):
    """Structured key fields extracted by GPT-4o-mini."""
    document_type: Optional[str] = None
    urgency: Optional[str] = None  # low | medium | high
    policy_reference: Optional[str] = None  # masked value
    claim_type: Optional[str] = None


class ClassificationResult(BaseModel):
    """Cosmos DB document for the 'classification_results' container."""
    result_id: str = Field(..., description="Unique result identifier (UUID)")
    case_id: str
    email_id: str
    classification_category: ClassificationCategory
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    key_fields: KeyFields
    routing_recommendation: str
    requires_human_review: bool
    classified_at: datetime = Field(default_factory=datetime.utcnow)
    masked_text_blob_path: Optional[str] = None  # blob path of masked text used for classification
    downstream_notification_sent: bool = False
    downstream_notification_at: Optional[datetime] = None

    @field_validator("confidence_score")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 4)


class ClassificationResponse(BaseModel):
    """API response for classification details."""
    result_id: str
    case_id: str
    classification_category: ClassificationCategory
    confidence_score: float
    summary: str
    key_fields: KeyFields
    routing_recommendation: str
    requires_human_review: bool
    classified_at: datetime
    downstream_notification_sent: bool
    downstream_notification_at: Optional[datetime] = None


class TimelineEvent(BaseModel):
    """A single event in the case processing timeline."""
    timestamp: datetime
    event: str
    details: Optional[str] = None
