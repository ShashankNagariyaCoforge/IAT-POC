"""
Azure Key Vault service.
Retrieves secrets and certificates at startup using DefaultAzureCredential.
All sensitive values (Graph certs, encryption keys) are loaded from Key Vault.
"""

import logging
from functools import lru_cache

from azure.identity.aio import DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient
from azure.keyvault.certificates.aio import CertificateClient

from config import settings

logger = logging.getLogger(__name__)


class KeyVaultService:
    """Async client for Azure Key Vault secrets and certificates."""

    def __init__(self):
        self._vault_url = settings.azure_key_vault_url
        self._credential = DefaultAzureCredential()
        self._secret_client = SecretClient(vault_url=self._vault_url, credential=self._credential)
        self._cert_client = CertificateClient(vault_url=self._vault_url, credential=self._credential)

    async def get_secret(self, secret_name: str) -> str:
        """
        Retrieve a secret value from Azure Key Vault.

        Args:
            secret_name: The name of the secret in Key Vault.

        Returns:
            The secret value as a string.

        Raises:
            Exception: If the secret cannot be retrieved.
        """
        try:
            secret = await self._secret_client.get_secret(secret_name)
            logger.debug(f"Retrieved secret '{secret_name}' from Key Vault.")
            return secret.value
        except Exception as e:
            logger.error(f"Failed to retrieve secret '{secret_name}' from Key Vault: {e}")
            raise

    async def get_certificate(self, cert_name: str) -> bytes:
        """
        Retrieve the PEM-encoded private key of a certificate from Key Vault.

        Args:
            cert_name: The name of the certificate in Key Vault.

        Returns:
            PEM-encoded certificate bytes.

        Raises:
            Exception: If the certificate cannot be retrieved.
        """
        try:
            # Key Vault stores the private key as a secret with the same name as the cert
            secret = await self._secret_client.get_secret(cert_name)
            logger.debug(f"Retrieved certificate '{cert_name}' from Key Vault.")
            # The value is base64-encoded PFX; return as bytes
            import base64
            return base64.b64decode(secret.value)
        except Exception as e:
            logger.error(f"Failed to retrieve certificate '{cert_name}' from Key Vault: {e}")
            raise

    async def close(self):
        """Close the Key Vault clients."""
        await self._secret_client.close()
        await self._cert_client.close()
        await self._credential.close()


@lru_cache()
def get_keyvault_service() -> KeyVaultService:
    """Cached Key Vault service singleton."""
    return KeyVaultService()
