"""Pydantic models for UW Worksheet."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UWSection(BaseModel):
    """One section of the underwriter worksheet."""
    title: str
    content: str  # Markdown-formatted text
    section_key: str


class UWWorksheet(BaseModel):
    """Persisted UW worksheet document (stored in uw_worksheets collection)."""
    case_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    last_edited_at: Optional[datetime] = None
    sections: List[UWSection] = Field(default_factory=list)
    generation_status: str = "complete"  # complete | partial | failed


class UWWorksheetPatch(BaseModel):
    """Payload for PATCH /uw-worksheet — saves edited sections."""
    sections: List[UWSection]
