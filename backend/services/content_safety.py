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
        
        # We only throw an error if this is actually called without config, 
        # protecting dev environments that might not use this feature.
        self.configured = bool(self.endpoint and self.key)
        self.client: Optional[ContentSafetyClient] = None
        
        if self.configured:
            try:
                self.client = ContentSafetyClient(
                    endpoint=self.endpoint,
                    credential=AzureKeyCredential(self.key)
                )
            except Exception as e:
                logger.error(f"Failed to initialize ContentSafetyClient: {e}")
                self.configured = False

    async def analyze_text(self, text: str) -> Optional[ContentSafetyResult]:
        """
        Analyze text for harmful content across 4 categories:
        Hate, Self-Harm, Sexual, and Violence.
        
        Args:
            text: The document text to analyze.
            
        Returns:
            ContentSafetyResult with severity scores (0-7), or None if unconfigured/failed.
        """
        if not self.configured or not self.client:
            logger.warning("Content Safety is not configured. Skipping analysis.")
            return None

        # The API has a text length limit (usually 10,000 chars per request).
        # We process the first 10,000 characters as that is usually sufficient 
        # to detect the overall tone/safety of an email/document.
        if len(text) > 10000:
            logger.info("Truncating text to 10k chars for Content Safety API")
            text = text[:10000]

        try:
            request = AnalyzeTextOptions(text=text)
            response: AnalyzeTextResult = self.client.analyze_text(request)
            
            # Map Azure's response to our internal model
            result = ContentSafetyResult(
                hate_severity=response.hate_result.severity if response.hate_result else 0,
                self_harm_severity=response.self_harm_result.severity if response.self_harm_result else 0,
                sexual_severity=response.sexual_result.severity if response.sexual_result else 0,
                violence_severity=response.violence_result.severity if response.violence_result else 0,
            )
            
            logger.info(f"Content Safety Result: Hate={result.hate_severity}, "
                        f"SelfHarm={result.self_harm_severity}, "
                        f"Sexual={result.sexual_severity}, "
                        f"Violence={result.violence_severity}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error calling Azure Content Safety: {e}", exc_info=True)
            return None
