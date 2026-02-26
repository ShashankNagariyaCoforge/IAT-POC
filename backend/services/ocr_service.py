"""
OCR service (Step 8).
Calls the Azure Document Intelligence container (ACI) for scanned/handwritten documents.
Only triggered when the document parser flags ocr_required=True.
"""

import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """Client for the Azure Document Intelligence ACI container."""

    def __init__(self):
        self._endpoint = settings.doc_intelligence_endpoint.rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def extract_text(self, content: bytes, content_type: str = "application/pdf") -> str:
        """
        Send document bytes to the Azure Document Intelligence container for OCR.

        Args:
            content: Raw document bytes (PDF, image, etc.).
            content_type: MIME type of the content.

        Returns:
            Extracted text from OCR.

        Raises:
            Exception: If the OCR request fails after retries.
        """
        try:
            logger.info(f"Sending document to OCR service ({len(content)} bytes, type: {content_type})")
            async with httpx.AsyncClient(timeout=120) as client:
                # Submit the document for analysis
                submit_resp = await client.post(
                    f"{self._endpoint}/formrecognizer/documentModels/prebuilt-read:analyze",
                    content=content,
                    headers={
                        "Content-Type": content_type,
                        "Accept": "application/json",
                    },
                    params={"api-version": "2023-07-31"},
                )
                submit_resp.raise_for_status()

                # Get the operation URL from the response headers
                operation_url = submit_resp.headers.get("Operation-Location")
                if not operation_url:
                    raise ValueError("OCR service did not return an operation URL.")

                # Poll for completion
                import asyncio
                for _ in range(30):
                    await asyncio.sleep(2)
                    result_resp = await client.get(operation_url)
                    result_resp.raise_for_status()
                    result = result_resp.json()

                    status = result.get("status")
                    if status == "succeeded":
                        return self._extract_text_from_result(result)
                    elif status == "failed":
                        raise RuntimeError(f"OCR analysis failed: {result.get('error')}")
                    # status == "running" → continue polling

                raise TimeoutError("OCR operation timed out after 60 seconds.")

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}", exc_info=True)
            raise

    def _extract_text_from_result(self, result: dict) -> str:
        """
        Parse the Document Intelligence response and extract all text content.

        Args:
            result: The JSON response from Document Intelligence.

        Returns:
            Concatenated text string from all pages.
        """
        analyze_result = result.get("analyzeResult", {})
        content = analyze_result.get("content", "")
        if content:
            return content

        # Fallback: extract from pages
        pages = analyze_result.get("pages", [])
        lines = []
        for page in pages:
            for line in page.get("lines", []):
                lines.append(line.get("content", ""))
        return "\n".join(lines)
