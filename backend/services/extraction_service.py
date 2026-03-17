import logging
import httpx
import asyncio
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

class ExtractionService:
    """Service to interface with Azure Document Intelligence for spatial extraction."""

    def __init__(self):
        self._endpoint = settings.doc_intelligence_endpoint.rstrip("/")
        self._api_key = settings.doc_intelligence_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def analyze_document(self, content: bytes, content_type: str) -> Dict[str, Any]:
        """
        Analyzes a document using Azure Document Intelligence Layout model.
        Returns the full analyzeResult which includes text, lines, and polygons.
        """
        try:
            logger.info(f"Analyzing document with Azure DI ({len(content)} bytes, type: {content_type})")
            
            headers = {
                "Content-Type": content_type,
                "Accept": "application/json",
            }
            if self._api_key:
                headers["Ocp-Apim-Subscription-Key"] = self._api_key

            async with httpx.AsyncClient(timeout=120) as client:
                # Submit for analysis
                # Using prebuilt-layout to get text, lines, and selection marks with polygons
                submit_resp = await client.post(
                    f"{self._endpoint}/formrecognizer/documentModels/prebuilt-layout:analyze",
                    content=content,
                    headers=headers,
                    params={"api-version": "2023-07-31"},
                )
                submit_resp.raise_for_status()

                operation_url = submit_resp.headers.get("Operation-Location")
                if not operation_url:
                    raise ValueError("Document Intelligence service did not return an operation URL.")

                # Poll for completion
                for _ in range(30):
                    await asyncio.sleep(2)
                    result_resp = await client.get(operation_url)
                    result_resp.raise_for_status()
                    result = result_resp.json()

                    if result.get("status") == "succeeded":
                        return result.get("analyzeResult", {})
                    elif result.get("status") == "failed":
                        raise RuntimeError(f"DI analysis failed: {result.get('error')}")

                raise TimeoutError("DI operation timed out after 60 seconds.")

        except Exception as e:
            logger.error(f"DI analysis failed: {e}", exc_info=True)
            raise

    def find_field_in_lines(self, analyze_result: Dict[str, Any], search_value: str) -> List[Dict[str, Any]]:
        """
        Searches for a specific value in the DI lines and returns its polygons.
        This is a fuzzy search since the value might be slightly different or contain masks.
        """
        if not search_value or search_value.lower() == "null" or search_value == "—":
            return []

        search_value_clean = search_value.lower().strip()
        matches = []
        
        pages = analyze_result.get("pages", [])
        for page_idx, page in enumerate(pages):
            for line in page.get("lines", []):
                line_content = line.get("content", "").lower()
                
                # Simple exact or partial match for now
                if search_value_clean in line_content:
                    matches.append({
                        "text": line.get("content"),
                        "page": page_idx + 1,
                        "polygon": line.get("polygon"), # [x1, y1, x2, y2, x3, y3, x4, y4]
                        "confidence": line.get("spans", [{}])[0].get("confidence", 0.9),
                        "page_width": page.get("width"),
                        "page_height": page.get("height"),
                        "unit": page.get("unit")
                    })
        
        return matches
    def extract_tables(self, analyze_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extracts structured table data including cell polygons for multi-field grouping.
        """
        tables = []
        raw_tables = analyze_result.get("tables", [])
        
        for table_idx, table in enumerate(raw_tables):
            rows = {}
            for cell in table.get("cells", []):
                r_idx = cell.get("rowIndex")
                if r_idx not in rows:
                    rows[r_idx] = []
                
                # Get polygon for the cell
                polygon = None
                regions = cell.get("boundingRegions", [])
                if regions:
                    polygon = regions[0].get("polygon")
                    page = regions[0].get("pageNumber")
                
                rows[r_idx].append({
                    "content": cell.get("content"),
                    "colIndex": cell.get("columnIndex"),
                    "polygon": polygon,
                    "page": page
                })
            
            # Convert rows dict to sorted list
            sorted_rows = []
            for r in sorted(rows.keys()):
                sorted_rows.append(sorted(rows[r], key=lambda x: x["colIndex"]))
                
            tables.append({
                "id": f"table_{table_idx}",
                "rowCount": table.get("rowCount"),
                "columnCount": table.get("columnCount"),
                "rows": sorted_rows
            })
            
        return tables
