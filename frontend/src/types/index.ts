/**
 * TypeScript interfaces that mirror the Pydantic v2 backend models.
 * Used across all components and API calls.
 */

export type CaseStatus =
    | 'RECEIVED'
    | 'PROCESSING'
    | 'CLASSIFIED'
    | 'PENDING_REVIEW'
    | 'PROCESSED'
    | 'FAILED'
    | 'BLOCKED_SAFETY'
    | 'NEEDS_REVIEW_SAFETY'
    | 'UPDATED';

export interface ContentSafetyResult {
    hate_severity: number;
    self_harm_severity: number;
    sexual_severity: number;
    violence_severity: number;
}

export type ClassificationCategory =
    | 'New'
    | 'Renewal'
    | 'Query/General'
    | 'Follow-up'
    | 'Complaint/Escalation'
    | 'Regulatory/Legal'
    | 'Documentation/Evidence'
    | 'Spam/Irrelevant'
    | 'BOR';

export interface Case {
    case_id: string;
    status: CaseStatus;
    classification_category: ClassificationCategory | null;
    confidence_score: number | null;
    created_at: string;
    updated_at: string;
    subject: string;
    sender: string;
    email_count: number;
    requires_human_review: boolean;
    summary: string | null;
    content_safety_result?: ContentSafetyResult;
}

export interface CaseListResponse {
    cases: Case[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

export interface Email {
    email_id: string;
    case_id: string;
    sender: string;
    recipients: string[];
    subject: string;
    body_preview: string | null;
    body_masked?: string;
    body: string;
    received_at: string;
    has_attachments: boolean;
    attachment_count: number;
}

export interface Document {
    document_id: string;
    email_id: string;
    file_name: string;
    file_type: string;
    ocr_applied: boolean;
    has_urls: boolean;
    crawled_urls: string[];
    processing_status: string;
    extracted_text_preview: string | null;
}

export interface InsuredInfo {
    name?: string;
    address?: string;
}

export interface AgentInfo {
    agencyName?: string;
    name?: string;
    email?: string;
    phone?: string;
}

export interface CoverageInfo {
    coverage?: string;
    coverageDescription?: string;
    limit?: string;
    deductible?: string;
}

export interface ExposureInfo {
    exposureType?: string;
    exposureDescription?: string;
    value?: string;
}

export interface DocumentInfo {
    fileName?: string;
    fileType?: string;
    documentDescription?: string;
}

export interface KeyFields {
    name?: string;
    insured?: InsuredInfo;
    agent?: AgentInfo;
    submission_description?: string;
    coverages: CoverageInfo[];
    exposures: ExposureInfo[];
    documents: DocumentInfo[];

    // New Fields
    licensed_producer?: string;
    segment?: string;
    submission_type?: string;
    applicant_name?: string;
    effective_date?: string;
    business_description?: string;
    primary_rating_state?: string;
    iat_product?: string;
    uw_am?: string;
    naics_code?: string;
    sic_code?: string;
    primary_phone?: string;
    email_address?: string;
    entity_type?: string;
    agency?: string;
    address?: string;
    agent_email?: string;
    agent_phone?: string;
    field_confidence?: Record<string, number>;

    // Legacy fields
    document_type?: string;
    urgency?: string;
    policy_reference?: string;
    claim_type?: string;
}

export interface ExtractionInstance {
    value: string;
    confidence: number;
    doc_id: string;
    page: number;
    polygon: number[]; // [x1, y1, x2, y2, x3, y3, x4, y4]
    page_width: number;
    page_height: number;
    unit: string;
}

export interface ExtractionResult {
    field: string;
    instances: ExtractionInstance[];
}

export interface TableCell {
    content: string;
    colIndex: number;
    polygon: number[] | null;
    page: number;
}

export interface ExtractedTable {
    id: string;
    rowCount: number;
    columnCount: number;
    rows: TableCell[][];
    doc_id: string;
}

export interface V2FieldTraceability {
    page_number: number;
    bbox: [number, number, number, number] | null; // [x1, y1, x2, y2] in ADI units
    page_width: number | null;
    page_height: number | null;
    coordinate_unit: string;   // "inch" | "pixel"
    doc_id: string;            // document UUID — use for /api/cases/{id}/documents/{doc_id}/pdf
    document_name: string;
    raw_text: string | null;
    chunk_id: string | null;
    section_heading: string | null;
    extraction_source: string;
    enrichment_url: string | null;
}

export interface ClassificationResult {
    result_id: string;
    case_id: string;
    classification_category: ClassificationCategory;
    confidence_score: number;
    summary: string;
    key_fields: KeyFields;
    requires_human_review: boolean;
    classified_at: string;
    extraction_results?: ExtractionResult[];
    extracted_tables?: ExtractedTable[];
    annotated_docs?: Record<string, string>;
    downstream_notification_sent: boolean;
    downstream_notification_at: string | null;
    // V2 click-to-highlight data
    v2_traceability?: Record<string, V2FieldTraceability>;
}

export interface TimelineEvent {
    timestamp: string;
    event: string;
    details: string | null;
}

export interface Stats {
    total_cases: number;
    by_status: Record<string, number>;
    by_category: Record<string, number>;
    pending_human_review: number;
}

export type AgentStatusType = 'pending' | 'active' | 'completed' | 'failed' | 'warning';

export interface AgentStatus {
    id: string;
    name: string;
    type: string;
    detail: string;
    score: number;
    status: AgentStatusType;
}

export interface PipelineStatus {
    case_id: string;
    status: CaseStatus;
    agents: AgentStatus[];
    current_agent_index: number;
    is_terminal: boolean;
}

export interface EnrichedField {
    value: string | null;
    confidence: number;
    source: string | null;
    is_critical?: boolean;
}

export interface EnrichmentData {
    entity_type?: EnrichedField;
    naics_code?: EnrichedField;
    entity_structure?: EnrichedField;
    years_in_business?: EnrichedField;
    number_of_employees?: EnrichedField;
    territory_code?: EnrichedField;
    limit_of_liability?: EnrichedField;
    deductible?: EnrichedField;
    class_mass_action_deductible_retention?: EnrichedField;
    pending_or_prior_litigation_date?: EnrichedField;
    duty_to_defend_limit?: EnrichedField;
    defense_outside_limit?: EnrichedField;
    employment_category?: EnrichedField;
    ec_number_of_employees?: EnrichedField;
    employee_compensation?: EnrichedField;
    number_of_employees_in_each_band?: EnrichedField;
    employee_location?: EnrichedField;
    number_of_employees_in_each_location?: EnrichedField;
    source_urls: string[];
    company_name: string | null;
    website: string | null;
    enrichment_status: string;
}

export interface EnrichmentResult {
    case_id: string;
    result_id: string;
    enrichment: EnrichmentData;
    enriched_at: string;
}
