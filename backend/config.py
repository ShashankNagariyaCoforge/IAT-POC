"""
Application configuration loaded from environment variables and Azure Key Vault.
Uses pydantic-settings for validation and type safety.
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings. Values come from .env file or environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Azure Key Vault
    azure_key_vault_url: str

    # Azure Cosmos DB
    azure_cosmos_endpoint: str
    cosmos_database_name: str = "iatinsurance-db"

    # Azure Blob Storage
    azure_storage_account_url: str
    blob_container_raw_emails: str = "raw-emails"
    blob_container_attachments: str = "raw-attachments"
    blob_container_extracted_text: str = "extracted-text"

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-08-01-preview"

    # Azure Document Intelligence (OCR - ACI)
    doc_intelligence_endpoint: str

    # Microsoft Graph API
    graph_client_id: str
    graph_tenant_id: str
    graph_cert_name: str = "graph-api-certificate"

    # Mailbox routing
    target_mailbox: str
    downstream_email: str
    webhook_url: str

    # Security
    pii_encryption_key: str  # base64-encoded 32-byte AES-256 key
    webhook_secret: str = ""

    # App settings
    environment: str = "development"
    log_level: str = "INFO"
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

    @field_validator("azure_key_vault_url", "azure_cosmos_endpoint", "azure_storage_account_url")
    @classmethod
    def must_be_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError(f"Must be an HTTPS URL, got: {v}")
        return v


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


# Module-level singleton for convenient import
settings: Settings = get_settings()
