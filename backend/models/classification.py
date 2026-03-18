"""Pydantic v2 models for Classification results."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from models.case import ClassificationCategory


class InsuredInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None

class AgentInfo(BaseModel):
    agencyName: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class CoverageInfo(BaseModel):
    coverage: Optional[str] = None
    description: Optional[str] = None
    limit: Optional[str] = None
    deductible: Optional[str] = None

class ExposureInfo(BaseModel):
    exposureType: Optional[str] = None
    description: Optional[str] = None
    value: Optional[str] = None

class DocumentInfo(BaseModel):
    fileName: Optional[str] = None
    fileType: Optional[str] = None
    description: Optional[str] = None

class KeyFields(BaseModel):
    """Structured key fields extracted by GPT-4o-mini."""
    name: Optional[str] = Field(None, description="Insured Business Name")
    insured: Optional[InsuredInfo] = None
    agent: Optional[AgentInfo] = None
    description: Optional[str] = None
    coverages: List[CoverageInfo] = Field(default_factory=list)
    exposures: List[ExposureInfo] = Field(default_factory=list)
    documents: List[DocumentInfo] = Field(default_factory=list)
    
    # New Fields
    licensed_producer: Optional[str] = None
    segment: Optional[str] = None
    submission_type: Optional[str] = None
    applicant_name: Optional[str] = None
    effective_date: Optional[str] = None
    business_description: Optional[str] = None
    primary_rating_state: Optional[str] = None
    iat_product: Optional[str] = None
    uw_am: Optional[str] = None
    naics_code: Optional[str] = None
    sic_code: Optional[str] = None
    primary_phone: Optional[str] = None
    email_address: Optional[str] = None
    entity_type: Optional[str] = None
    agency: Optional[str] = None
    address: Optional[str] = None

    # Legacy fields (keeping for compatibility with existing UI if needed)
    document_type: Optional[str] = None
    urgency: Optional[str] = None
    policy_reference: Optional[str] = None


class ClassificationResult(BaseModel):
    """Cosmos DB document for the 'classification_results' container."""
    result_id: str = Field(..., description="Unique result identifier (UUID)")
    case_id: str
    email_id: str
    classification_category: ClassificationCategory
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    key_fields: KeyFields
    requires_human_review: bool
    classified_at: datetime = Field(default_factory=datetime.utcnow)
    masked_text_blob_path: Optional[str] = None  # blob path of masked text used for classification
    extraction_results: Optional[list] = None  # Unified list of mapped polygons and sources
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
