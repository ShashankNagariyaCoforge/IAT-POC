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
    file_name: string;
    file_type: string;
    ocr_applied: boolean;
    has_urls: boolean;
    crawled_urls: string[];
    processing_status: string;
    extracted_text_preview: string | null;
}

export interface KeyFields {
    document_type: string | null;
    urgency: 'low' | 'medium' | 'high' | null;
    policy_reference: string | null;
    claim_type: string | null;
    // Entity Info
    insured_name: string | null;
    broker_name: string | null;
    obligor: string | null;
    // Policy Details
    effective_date: string | null;
    expiration_date: string | null;
    tenor: string | null;
    // Financials
    limit_of_liability: string | null;
    premium_amount: string | null;
    currency: string | null;
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
    downstream_notification_sent: boolean;
    downstream_notification_at: string | null;
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
