"""
Pipeline V2 — All Pydantic models used across stages.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Stage 2/3 — Parsing & Chunking ────────────────────────────────────────

class WordLocation(BaseModel):
    word: str
    bbox: List[float]       # [x1, y1, x2, y2] in document points
    page_number: int


class ChunkData(BaseModel):
    chunk_id: str           # "{filename}::CHUNK_{n:03d}"
    document_name: str
    blob_url: str
    page_number: int
    section_heading: Optional[str] = None
    approximate_position: str = "middle_third"   # top_third | middle_third | bottom_third
    text: str
    word_map: List[WordLocation] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    document_id: str
    filename: str
    blob_url: str
    content_type: str
    full_text: str
    page_count: int
    # Raw ADI output preserved for chunking
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    paragraphs: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)


# ─── Stage 1 — Ingestion ────────────────────────────────────────────────────

class IngestionResult(BaseModel):
    case_id: str
    email_subject: str
    email_sender: str
    email_received_at: str
    email_body: str                              # combined email thread text
    attachment_blob_paths: Dict[str, str]        # filename -> blob_path
    attachment_containers: Dict[str, str]        # filename -> container name
    raw_emails: List[Dict[str, Any]] = Field(default_factory=list)
    raw_documents: List[Dict[str, Any]] = Field(default_factory=list)


# ─── Stage 4 — Document Classification ─────────────────────────────────────

class DocumentClassification(BaseModel):
    filename: str
    role: str
    confidence: float
    reasoning: str


# ─── Stage 5 — Case Classification ─────────────────────────────────────────

class CaseClassification(BaseModel):
    case_type: str
    line_of_business: str
    broker_submitted: bool
    urgency: str            # normal | urgent | critical
    confidence: float
    reasoning: str
    review_required: bool = False


# ─── Stage 6 — Schema ────────────────────────────────────────────────────────

class SchemaField(BaseModel):
    field_name: str
    display_label: str
    mandatory: bool = False
    data_type: str = "string"
    primary_sources: List[str] = Field(default_factory=list)
    fallback_sources: List[str] = Field(default_factory=list)
    web_enrichable: bool = False
    validation_rule: Optional[str] = None


class ExtractionSchema(BaseModel):
    case_type: str
    fields: List[SchemaField]


# ─── Stage 7 — Raw Extraction per Document ───────────────────────────────────

class ExtractedFieldRaw(BaseModel):
    field_name: str
    value: Optional[str] = None
    confidence: float = 0.0
    raw_text: Optional[str] = None      # verbatim phrase from document (10-25 words)
    chunk_id: Optional[str] = None      # which chunk this came from
    not_found_reason: Optional[str] = None
    source_document: str = ""


# ─── Stage 8 — Source Location after Coordinate Resolution ──────────────────

class SourceLocation(BaseModel):
    document_name: str
    blob_url: str
    page_number: int
    bbox: Optional[List[float]] = None          # [x1, y1, x2, y2] in ADI coordinate units
    chunk_id: Optional[str] = None
    section_heading: Optional[str] = None
    approximate_position: Optional[str] = None
    raw_text: Optional[str] = None
    extraction_source: str = "llm_extraction"   # llm_extraction | web_enrichment
    # Page dimensions — needed by frontend to convert bbox → screen pixels
    page_width: Optional[float] = None          # ADI page width (inches for PDFs)
    page_height: Optional[float] = None         # ADI page height (inches for PDFs)
    coordinate_unit: str = "inch"               # "inch" (PDFs) | "pixel" (images)


# ─── Stage 9 — Merged Fields ────────────────────────────────────────────────

class FieldSource(BaseModel):
    document_name: str
    value: str
    confidence: float
    location: Optional[SourceLocation] = None


class MergedField(BaseModel):
    field_name: str
    display_label: str
    value: Optional[str] = None
    confidence: float = 0.0
    mandatory: bool = False
    web_enrichable: bool = False
    status: str = "missing"     # accepted | conflict | missing | low_confidence
    primary_source: Optional[FieldSource] = None
    all_sources: List[FieldSource] = Field(default_factory=list)
    conflict_values: Optional[List[FieldSource]] = None
    enrichment_url: Optional[str] = None


# ─── Stage 10 — Enrichment ───────────────────────────────────────────────────

class EnrichmentFieldResult(BaseModel):
    field_name: str
    value: Optional[str] = None
    source_url: str = ""
    raw_text: str = ""
    confidence: float = 0.0
    steps_taken: List[str] = Field(default_factory=list)


# ─── Stage 11 — Validation ───────────────────────────────────────────────────

class ValidationFlag(BaseModel):
    field_name: str
    flag_type: str      # date_logic | ocr_suspected | contradiction | missing_mandatory | format_error
    severity: str       # warning | error
    description: str
    suggested_action: str


# ─── Stage 12 — Routing ──────────────────────────────────────────────────────

class RoutingDecision(BaseModel):
    route: str          # auto_process | spot_check | full_human_review
    reasons: List[str] = Field(default_factory=list)
    flagged_fields: List[str] = Field(default_factory=list)


# ─── Final Pipeline Result ───────────────────────────────────────────────────

class PipelineResult(BaseModel):
    case_id: str
    status: str         # success | failed | partial
    routing: str
    case_type: str
    line_of_business: str
    urgency: str
    classification_confidence: float
    broker_submitted: bool
    document_roles: Dict[str, str] = Field(default_factory=dict)   # filename -> role
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    conflicts: List[Dict] = Field(default_factory=list)
    missing_mandatory_fields: List[str] = Field(default_factory=list)
    validation_flags: List[Dict] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    processing_duration_seconds: float = 0.0
    pipeline_version: str = "v2"
