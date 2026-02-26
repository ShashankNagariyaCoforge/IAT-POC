"""Pydantic v2 models for Document data."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    """Cosmos DB document for the 'documents' container."""
    document_id: str = Field(..., description="Unique document identifier (UUID)")
    email_id: str
    case_id: str
    file_name: str
    file_type: str  # e.g. "pdf", "docx", "jpg"
    blob_path: str  # Path in raw-attachments container
    ocr_required: bool = False
    ocr_applied: bool = False
    extracted_text_blob_path: Optional[str] = None
    has_urls: bool = False
    crawled_urls: List[str] = Field(default_factory=list)
    processing_status: str = "PENDING"  # PENDING, DONE, FAILED
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentResponse(BaseModel):
    """API response for a single document."""
    document_id: str
    file_name: str
    file_type: str
    ocr_applied: bool
    has_urls: bool
    crawled_urls: List[str]
    processing_status: str
    extracted_text_preview: Optional[str] = None  # First 500 chars (PII masked)
