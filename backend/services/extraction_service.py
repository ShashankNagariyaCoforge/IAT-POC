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
                    # Azure requires the key on the polling GET request as well
                    result_resp = await client.get(operation_url, headers=headers)
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
        Searches for a specific value in the DI lines and words and returns its polygons.
        Uses exact and fuzzy word-level sliding windows for highly accurate bounding boxes.
        """
        if not search_value or search_value.lower() == "null" or search_value == "—":
            return []

        import re
        import difflib
        
        def normalize(text: str) -> str:
            t = re.sub(r'[^\w\s]', '', text)
            return " ".join(t.lower().split())

        def union_polygon(polys: List[List[float]]) -> Optional[List[float]]:
            xs, ys = [], []
            for p in polys:
                if not p or len(p) != 8:
                    continue
                xs.extend([p[0], p[2], p[4], p[6]])
                ys.extend([p[1], p[3], p[5], p[7]])
            if not xs or not ys:
                return None
            x_min, y_min = min(xs), min(ys)
            x_max, y_max = max(xs), max(ys)
            return [x_min, y_min, x_max, y_min, x_max, y_max, x_min, y_max]

        target = normalize(search_value)
        if not target:
            return []

        is_short = len(target) < 4
        matches = []
        pages = analyze_result.get("pages", [])
        
        for page_idx, page in enumerate(pages):
            page_w = page.get("width")
            page_h = page.get("height")
            unit = page.get("unit")
            
            words = page.get("words", [])
            lines = page.get("lines", [])
            
            # 1. WORD-level sliding window (Highest Box Fidelity)
            if words:
                w_norm = [normalize(w.get("content", w.get("text", ""))) for w in words]
                max_len = min(15, len(words))
                
                for i in range(len(words)):
                    if not w_norm[i]:
                        continue
                    concat = w_norm[i]
                    polys = [words[i].get("polygon")]
                    
                    # Single word match
                    if target == concat:
                        matches.append({
                            "text": concat,
                            "page": page_idx + 1,
                            "polygon": union_polygon(polys),
                            "confidence": words[i].get("confidence", 0.9),
                            "similarity": 1.0,
                            "source": "word",
                            "page_width": page_w, "page_height": page_h, "unit": unit
                        })
                        continue
                        
                    # Sliding window
                    for j in range(i + 1, min(i + max_len, len(words))):
                        if w_norm[j]:
                            concat += " " + w_norm[j]
                            polys.append(words[j].get("polygon"))
                            
                            # Exact match or very high fuzzy match for longer strings
                            similarity = difflib.SequenceMatcher(None, target, concat).ratio()
                            if target == concat or (not is_short and similarity > 0.9):
                                poly_union = union_polygon(polys)
                                if poly_union:
                                    matches.append({
                                        "text": concat,
                                        "page": page_idx + 1,
                                        "polygon": poly_union,
                                        "confidence": sum(w.get("confidence", 0.9) for w in words[i:j+1]) / (j-i+1),
                                        "similarity": similarity,
                                        "source": "word_window",
                                        "page_width": page_w, "page_height": page_h, "unit": unit
                                    })
            
            # 2. LINE-level fallback (if OCR spacing makes word windows fail)
            if not matches and lines:
                for line in lines:
                    line_content = line.get("content", "")
                    line_norm = normalize(line_content)
                    if not line_norm:
                        continue
                        
                    similarity = difflib.SequenceMatcher(None, target, line_norm).ratio()
                    sub_sim = 0
                    if not is_short and target in line_norm:
                        sub_sim = len(target) / len(line_norm)
                    
                    similarity = max(similarity, sub_sim)
                    
                    if (is_short and similarity > 0.85) or (not is_short and similarity > 0.6):
                        matches.append({
                            "text": line_content,
                            "page": page_idx + 1,
                            "polygon": line.get("polygon"),
                            "confidence": line.get("spans", [{}])[0].get("confidence", 0.9),
                            "similarity": similarity,
                            "source": "line",
                            "page_width": page_w, "page_height": page_h, "unit": unit
                        })
        
        # Sort by similarity and confidence to ensure "Winner Takes All" in process.py gets the best box
        matches.sort(key=lambda x: (x["similarity"], x["confidence"]), reverse=True)
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
