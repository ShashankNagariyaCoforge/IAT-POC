"""
Microsoft Graph API client.
Handles:
  - Certificate-based authentication via MSAL
  - Fetching emails and attachments from the target mailbox
  - Creating and renewing webhook subscriptions
  - Sending downstream notification emails
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
import msal

from config import settings
from services.keyvault import get_keyvault_service

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """Async Microsoft Graph API client with certificate-based authentication."""

    def __init__(self):
        self._auth_mode = settings.graph_auth_mode
        self._tenant_id = settings.graph_tenant_id
        self._client_id = settings.graph_client_id
        self._client_secret = settings.graph_client_secret
        self._cert_name = settings.graph_cert_name
        self._target_mailbox = settings.target_mailbox
        self._webhook_url = settings.webhook_url
        self._subscription_id: Optional[str] = None
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    async def _load_certificate(self) -> bytes:
        """Load the PFX certificate bytes from Azure Key Vault."""
        kv = get_keyvault_service()
        return await kv.get_certificate(self._cert_name)

    async def _get_access_token(self) -> str:
        """
        Obtain an access token using certificate-based or secret-based authentication.
        Caches the token until 5 minutes before expiry.

        Returns:
            Bearer token string.
        """
        now = datetime.now(timezone.utc)
        if self._token and self._token_expiry and now < self._token_expiry - timedelta(minutes=5):
            return self._token

        import asyncio

        if self._auth_mode == "secret":
            if not self._client_secret:
                raise RuntimeError("graph_client_secret is required when graph_auth_mode is 'secret'")
            
            token_result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._acquire_token_with_secret,
            )
        else:
            cert_bytes = await self._load_certificate()
            token_result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._acquire_token_with_cert,
                cert_bytes,
            )

        if "access_token" not in token_result:
            raise RuntimeError(f"Graph token acquisition failed: {token_result.get('error_description', token_result.get('error'))}")

        self._token = token_result["access_token"]
        expires_in = token_result.get("expires_in", 3600)
        self._token_expiry = now + timedelta(seconds=expires_in)
        logger.info(f"Graph API access token acquired/refreshed using '{self._auth_mode}' mode.")
        return self._token

    def _acquire_token_with_cert(self, cert_bytes: bytes) -> Dict:
        """Synchronous MSAL certificate token acquisition."""
        app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            client_credential={"private_key": cert_bytes, "thumbprint": ""},
        )
        return app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    def _acquire_token_with_secret(self) -> Dict:
        """Synchronous MSAL client secret token acquisition."""
        app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            client_credential=self._client_secret,
        )
        return app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    async def _get_headers(self) -> Dict[str, str]:
        """Build request headers with a valid Bearer token."""
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def fetch_email(self, message_id: str) -> Dict:
        """
        Fetch a single email message including all properties.

        Args:
            message_id: The Graph API message ID.

        Returns:
            Dictionary with email properties.
        """
        headers = await self._get_headers()
        url = f"{GRAPH_BASE_URL}/users/{self._target_mailbox}/messages/{message_id}"
        params = {"$select": "id,subject,from,toRecipients,receivedDateTime,body,internetMessageId,internetMessageHeaders,hasAttachments"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_attachments(self, message_id: str) -> List[Dict]:
        """
        Fetch all attachments for a given email message.

        Args:
            message_id: The Graph API message ID.

        Returns:
            List of attachment metadata dicts (including contentBytes as base64).
        """
        headers = await self._get_headers()
        url = f"{GRAPH_BASE_URL}/users/{self._target_mailbox}/messages/{message_id}/attachments"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("value", [])

    async def send_email(
        self,
        to: str,
        subject: str,
        body_html: str,
    ) -> None:
        """
        Send an email via Graph API from the target mailbox.
        Used for downstream team notifications.

        Args:
            to: Recipient email address.
            subject: Email subject.
            body_html: HTML body content.
        """
        headers = await self._get_headers()
        url = f"{GRAPH_BASE_URL}/users/{self._target_mailbox}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": to}}],
            }
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        logger.info(f"Email sent to {to}: {subject}")

    async def ensure_webhook_subscription(self) -> None:
        """
        On startup, check if a valid Graph webhook subscription exists.
        Create one if not, or if expired.
        """
        headers = await self._get_headers()
        async with httpx.AsyncClient(timeout=30) as client:
            # List existing subscriptions
            resp = await client.get(f"{GRAPH_BASE_URL}/subscriptions", headers=headers)
            resp.raise_for_status()
            subscriptions = resp.json().get("value", [])

            now = datetime.now(timezone.utc)
            valid_sub = None
            for sub in subscriptions:
                expiry = datetime.fromisoformat(sub["expirationDateTime"].replace("Z", "+00:00"))
                if (
                    sub.get("resource") == f"users/{self._target_mailbox}/mailFolders/Inbox/messages"
                    and expiry > now
                ):
                    valid_sub = sub
                    break

            if valid_sub:
                self._subscription_id = valid_sub["id"]
                logger.info(f"Using existing Graph subscription: {self._subscription_id}")
            else:
                await self._create_subscription(headers, client)

    async def _create_subscription(self, headers: Dict, client: httpx.AsyncClient) -> None:
        """Create a new Graph API webhook subscription."""
        expiry = (datetime.now(timezone.utc) + timedelta(hours=settings.webhook_subscription_renewal_hours)).isoformat()
        payload = {
            "changeType": "created",
            "notificationUrl": self._webhook_url,
            "resource": f"users/{self._target_mailbox}/mailFolders/Inbox/messages",
            "expirationDateTime": expiry,
            "clientState": settings.webhook_secret,
        }
        resp = await client.post(f"{GRAPH_BASE_URL}/subscriptions", headers=headers, json=payload)
        resp.raise_for_status()
        sub = resp.json()
        self._subscription_id = sub["id"]
        logger.info(f"Created new Graph subscription: {self._subscription_id}")

    async def renew_webhook_subscription(self) -> None:
        """Renew the existing Graph webhook subscription (called every 48 hours)."""
        if not self._subscription_id:
            logger.warning("No subscription ID found; creating a new subscription.")
            await self.ensure_webhook_subscription()
            return

        headers = await self._get_headers()
        new_expiry = (datetime.now(timezone.utc) + timedelta(hours=settings.webhook_subscription_renewal_hours)).isoformat()
        payload = {"expirationDateTime": new_expiry}
        url = f"{GRAPH_BASE_URL}/subscriptions/{self._subscription_id}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(url, headers=headers, json=payload)
            if resp.status_code == 404:
                logger.warning("Subscription not found; creating new one.")
                await self._create_subscription(headers, client)
            else:
                resp.raise_for_status()
                logger.info(f"Renewed Graph subscription {self._subscription_id} until {new_expiry}")
