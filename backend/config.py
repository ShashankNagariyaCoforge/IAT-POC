"""
Application configuration loaded from environment variables and Azure Key Vault.
Uses pydantic-settings for validation and type safety.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings. Values come from .env file or environment.
    
    Required Azure credentials are Optional[str] so the app can start without them.
    Services will raise a descriptive error at the time they are called if a
    credential is missing, rather than crashing the entire process on boot.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Azure Key Vault
    azure_key_vault_url: Optional[str] = None

    # Azure Cosmos DB
    azure_cosmos_endpoint: Optional[str] = None
    cosmos_database_name: str = "iatinsurance-db"

    # Azure Blob Storage
    azure_storage_account_url: Optional[str] = None
    azure_storage_connection_string: Optional[str] = None  # Added for ingest sync
    blob_container_raw_emails: str = "iat_documents"  # default matching the ingest script
    blob_container_attachments: str = "raw-attachments"
    blob_container_extracted_text: str = "extracted-text"

    # Azure OpenAI
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-08-01-preview"

    # Azure Document Intelligence (OCR - ACI)
    doc_intelligence_endpoint: Optional[str] = None

    # Microsoft Graph API
    graph_auth_mode: str = "certificate"  # "certificate" or "secret"
    graph_client_id: Optional[str] = None
    graph_tenant_id: Optional[str] = None
    graph_client_secret: Optional[str] = None  # Used when graph_auth_mode = "secret"
    graph_cert_name: str = "graph-api-certificate"  # Used when graph_auth_mode = "certificate"

    # Mailbox routing
    target_mailbox: Optional[str] = None
    downstream_email: Optional[str] = None
    webhook_url: Optional[str] = None

    # Security
    pii_encryption_key: Optional[str] = None  # base64-encoded 32-byte AES-256 key
    webhook_secret: str = ""

    # App settings
    environment: str = "development"
    log_level: str = "INFO"
    dev_bypass_auth: bool = False  # Set DEV_BYPASS_AUTH=true in .env to skip JWT validation
    demo_mode: bool = False  # Set DEMO_MODE=true to use local TinyDB instead of Cosmos DB
    webhook_subscription_renewal_hours: int = 48
    classification_confidence_threshold: float = 0.75
    cases_per_page: int = 50

    # CORS origins (comma-separated, or * for dev)
    _allowed_origins_raw: str = "*"

    @property
    def allowed_origins(self) -> List[str]:
        """Parse comma-separated origins."""
        raw = self._allowed_origins_raw
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @field_validator("azure_key_vault_url", "azure_cosmos_endpoint", "azure_storage_account_url", mode="before")
    @classmethod
    def must_be_url(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if not v.startswith("https://"):
            raise ValueError(f"Must be an HTTPS URL, got: {v}")
        return v

    def require(self, field: str) -> str:
        """Return the value of a required setting, or raise a descriptive error."""
        value = getattr(self, field, None)
        if not value:
            raise RuntimeError(
                f"Missing required configuration: '{field.upper()}'. "
                f"Please set it in your .env file or environment variables."
            )
        return value


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


# Module-level singleton for convenient import
settings: Settings = get_settings()
