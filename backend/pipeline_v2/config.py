"""
Pipeline V2 configuration.
All V2_ env vars. Falls back to existing base settings if V2_ vars not set.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class V2Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Azure OpenAI — V2 can override or fall back to base settings
    # If not set, llm_client.py resolves these from AZURE_OPENAI_* keys
    v2_azure_openai_endpoint: Optional[str] = None
    v2_azure_openai_api_key: Optional[str] = None
    v2_azure_openai_api_version: Optional[str] = None       # falls back to AZURE_OPENAI_API_VERSION
    v2_azure_openai_deployment_large: Optional[str] = None  # falls back to AZURE_OPENAI_DEPLOYMENT
    v2_azure_openai_deployment_small: Optional[str] = None  # falls back to AZURE_OPENAI_DEPLOYMENT

    # Azure Document Intelligence — V2 can override or fall back to base settings
    v2_adi_endpoint: Optional[str] = None
    v2_adi_key: Optional[str] = None
    v2_adi_model: str = "prebuilt-layout"

    # Blob Storage — NEW container, reuses existing connection
    v2_blob_container_name: str = "insurance-cases-v2"

    # Cosmos DB — NEW database + collections, reuses existing connection
    v2_cosmos_database_name: str = "insurance_v2"
    v2_cosmos_cases_collection: str = "cases_v2"
    v2_cosmos_extractions_collection: str = "extractions_v2"
    v2_cosmos_documents_collection: str = "documents_v2"
    v2_cosmos_logs_collection: str = "pipeline_logs_v2"

    # Pipeline thresholds
    v2_classification_confidence_threshold: float = 0.80
    v2_field_confidence_threshold: float = 0.75
    v2_fuzzy_match_threshold: int = 75

    # Enrichment agent config
    v2_enrichment_max_iterations: int = 10
    v2_enrichment_timeout_seconds: int = 30
    v2_enrichment_fixed_sites: str = ""
    v2_google_search_api_key: Optional[str] = None
    v2_google_search_engine_id: Optional[str] = None

    # Document taxonomy (comma-separated, fully configurable)
    v2_document_roles: str = (
        "claim_form,broker_cover_letter,policy_schedule,invoice,"
        "survey_report,legal_notice,id_document,photo_evidence,"
        "medical_report,correspondence,unknown"
    )

    # Case types (comma-separated, fully configurable)
    v2_case_types: str = (
        "new_claim,renewal,endorsement,mid_term_adjustment,cancellation,"
        "general_query,follow_up,complaint_escalation,regulatory_legal,"
        "documentation_evidence,spam_irrelevant,bor"
    )

    # Lines of business (comma-separated, fully configurable)
    v2_lines_of_business: str = (
        "cargo,property,liability,motor,marine,professional_indemnity,"
        "life,health,unknown"
    )

    # Chunking config
    v2_chunk_max_words: int = 300
    v2_chunk_overlap_sentences: int = 1

    # LLM token limits (max output tokens per stage call)
    # 39 fields × ~200 tokens per field (value + raw_text + chunk_id) = ~8K output tokens minimum.
    # Set headroom above that so Azure OpenAI never hits the cap and silently drops trailing fields.
    v2_max_tokens_extraction: int = 32000      # stage7: 39 fields × ~200 tokens each + headroom
    v2_max_tokens_classification: int = 600    # stage5: single JSON object, small
    v2_max_tokens_doc_classification: int = 200 # stage4: 3-field JSON, very small
    v2_max_tokens_validation: int = 4000       # stage11: flag list per field, raised from 2000

    # Extraction chunk limit — how many chars of document chunks sent to LLM per doc
    # GPT-4o context is 128K tokens; 100K chars ≈ 25K tokens, leaving headroom for fields + prompt
    v2_extraction_chunk_char_limit: int = 100000  # was 24000 — old value missed pages 4+

    # Email body extraction limit — how many chars of email body to include in the extraction prompt.
    # Previously hardcoded to 8000 (≈2K tokens) which silently dropped fields in long emails.
    # 100K chars matches the document chunk limit — same budget for email as for PDF docs.
    v2_email_body_char_limit: int = 100000

    # Logging
    v2_log_level: str = "INFO"
    v2_log_pipeline_steps: bool = True

    # Prompt file names (relative to pipeline_v2/prompts/)
    v2_prompt_doc_classification: str = "doc_classification.txt"
    v2_prompt_case_classification: str = "case_classification.txt"
    v2_prompt_extraction_base: str = "extraction_base.txt"
    v2_prompt_enrichment_agent: str = "enrichment_agent.txt"
    v2_prompt_cross_doc_reasoning: str = "cross_doc_reasoning.txt"
    v2_prompt_validation: str = "validation.txt"

    @property
    def document_roles_list(self) -> List[str]:
        return [r.strip() for r in self.v2_document_roles.split(",") if r.strip()]

    @property
    def case_types_list(self) -> List[str]:
        return [t.strip() for t in self.v2_case_types.split(",") if t.strip()]

    @property
    def lines_of_business_list(self) -> List[str]:
        return [x.strip() for x in self.v2_lines_of_business.split(",") if x.strip()]

    @property
    def enrichment_fixed_sites_list(self) -> List[str]:
        if not self.v2_enrichment_fixed_sites:
            return []
        return [s.strip() for s in self.v2_enrichment_fixed_sites.split(",") if s.strip()]


@lru_cache()
def get_v2_settings() -> V2Settings:
    return V2Settings()


v2_settings: V2Settings = get_v2_settings()
