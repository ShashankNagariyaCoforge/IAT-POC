"""
Service for integrating with Azure AI Content Safety to detect harmful content.
"""

import logging
from typing import Optional

from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions, AnalyzeTextResult
from azure.core.credentials import AzureKeyCredential

from config import settings
from models.case import ContentSafetyResult

logger = logging.getLogger(__name__)


class ContentSafetyService:
    """Wrapper for the Azure AI Content Safety API."""

    def __init__(self):
        """Initialize the client using Azure credentials."""
        self.endpoint = settings.azure_content_safety_endpoint
        self.key = settings.azure_content_safety_key

        self.configured = bool(self.endpoint and self.key)
        self.client: Optional[ContentSafetyClient] = None

        if not self.endpoint:
            logger.warning("[ContentSafety] AZURE_CONTENT_SAFETY_ENDPOINT is not set — service will be skipped.")
        if not self.key:
            logger.warning("[ContentSafety] AZURE_CONTENT_SAFETY_KEY is not set — service will be skipped.")

        if self.configured:
            try:
                self.client = ContentSafetyClient(
                    endpoint=self.endpoint,
                    credential=AzureKeyCredential(self.key)
                )
                logger.info(f"[ContentSafety] Client initialized. Endpoint: {self.endpoint}")
            except Exception as e:
                logger.error(f"[ContentSafety] Failed to initialize ContentSafetyClient: {e}", exc_info=True)
                self.configured = False
        else:
            logger.info("[ContentSafety] Service not configured — content safety checks will be skipped.")

    async def analyze_text(self, text: str) -> Optional[ContentSafetyResult]:
        """
        Analyze text for harmful content across 4 categories:
        Hate, Self-Harm, Sexual, and Violence.

        Returns:
            ContentSafetyResult with severity scores (0-7), or None if unconfigured/failed.
        """
        if not self.configured or not self.client:
            logger.warning("[ContentSafety] Skipping analysis — service is not configured.")
            return None

        original_len = len(text)
        if original_len > 10000:
            logger.info(f"[ContentSafety] Text is {original_len} chars — truncating to 10,000 chars for API limit.")
            text = text[:10000]

        logger.info(f"[ContentSafety] Sending {len(text)} chars for analysis...")

        try:
            request = AnalyzeTextOptions(text=text)
            response: AnalyzeTextResult = self.client.analyze_text(request)

            result = ContentSafetyResult(
                hate_severity=response.hate_result.severity if response.hate_result else 0,
                self_harm_severity=response.self_harm_result.severity if response.self_harm_result else 0,
                sexual_severity=response.sexual_result.severity if response.sexual_result else 0,
                violence_severity=response.violence_result.severity if response.violence_result else 0,
            )

            logger.info(
                f"[ContentSafety] ✅ Analysis complete — "
                f"Hate={result.hate_severity}, "
                f"SelfHarm={result.self_harm_severity}, "
                f"Sexual={result.sexual_severity}, "
                f"Violence={result.violence_severity}"
            )

            # Warn if any category is flagged (severity > 0)
            flagged = {
                "Hate": result.hate_severity,
                "SelfHarm": result.self_harm_severity,
                "Sexual": result.sexual_severity,
                "Violence": result.violence_severity,
            }
            high = {k: v for k, v in flagged.items() if v > 2}
            if high:
                logger.warning(f"[ContentSafety] ⚠️ High severity detected: {high}")
            elif any(v > 0 for v in flagged.values()):
                logger.info(f"[ContentSafety] Low-level flags (severity 1-2): {flagged}")
            else:
                logger.info("[ContentSafety] No harmful content detected (all severities = 0).")

            return result

        except Exception as e:
            logger.error(f"[ContentSafety] ❌ API call failed: {e}", exc_info=True)
            return None
