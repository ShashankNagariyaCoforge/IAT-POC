import logging
import httpx
import asyncio
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

# Standalone worker for ProcessPoolExecutor
def find_field_worker(analyze_result: Dict[str, Any], search_value: str) -> List[Dict[str, Any]]:
    """
    Standalone version of find_field_in_lines for multi-processing.
    Searches for a specific value in the DI lines and words and returns its polygons.
    """
    if not search_value or search_value.lower() in ("null", "none", "—", "n/a"):
        return []

    import re
    import difflib

    # Pre-compile regex for performance
    _NORM_SUB = re.compile(r'[^\w\s]')
    
    def normalize(text: str) -> str:
        if not text: return ""
        t = _NORM_SUB.sub('', text)
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
        return [min(xs), min(ys), max(xs), min(ys), max(xs), max(ys), min(xs), max(ys)]

    target = normalize(search_value)
    if not target:
        return []

    target_len = len(target)
    is_short = target_len < 4
    matches = []
    pages = analyze_result.get("pages", [])
    
    for page_idx, page in enumerate(pages):
        page_w = page.get("width")
        page_h = page.get("height")
        unit = page.get("unit")
        
        words = page.get("words", [])
        lines = page.get("lines", [])
        
        # 1. WORD-level sliding window
        if words:
            w_norm = [normalize(w.get("content", w.get("text", ""))) for w in words]
            max_window = min(12, len(words)) # Reduced window slightly for speed
            
            for i in range(len(words)):
                if not w_norm[i]:
                    continue
                
                concat = w_norm[i]
                polys = [words[i].get("polygon")]
                
                # Check single word match
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
                    # Found exact match for this starting word, continue to next i
                    continue
                    
                for j in range(i + 1, min(i + max_window, len(words))):
                    if not w_norm[j]:
                        continue
                        
                    concat += " " + w_norm[j]
                    polys.append(words[j].get("polygon"))
                    
                    # Quick length filter before expensive SequenceMatcher
                    if abs(len(concat) - target_len) > (target_len * 0.5):
                        if len(concat) > target_len * 1.5: # Way too long
                            break
                        continue

                    if target == concat:
                        matches.append({
                            "text": concat,
                            "page": page_idx + 1,
                            "polygon": union_polygon(polys),
                            "confidence": sum(w.get("confidence", 0.9) for w in words[i:j+1]) / (j-i+1),
                            "similarity": 1.0,
                            "source": "word_window_exact",
                            "page_width": page_w, "page_height": page_h, "unit": unit
                        })
                        break # Exact match found, stop expanding this window
                    
                    if not is_short:
                        similarity = difflib.SequenceMatcher(None, target, concat).ratio()
                        if similarity > 0.9:
                            matches.append({
                                "text": concat,
                                "page": page_idx + 1,
                                "polygon": union_polygon(polys),
                                "confidence": sum(w.get("confidence", 0.9) for w in words[i:j+1]) / (j-i+1),
                                "similarity": similarity,
                                "source": "word_window_fuzzy",
                                "page_width": page_w, "page_height": page_h, "unit": unit
                            })
                            if similarity > 0.98: # Near perfect fuzzy match
                                break
        
        # 2. LINE-level fallback
        if not matches and lines:
            for line in lines:
                line_content = line.get("content", "")
                line_norm = normalize(line_content)
                if not line_norm or abs(len(line_norm) - target_len) > (target_len * 2):
                    continue
                    
                if target == line_norm:
                    similarity = 1.0
                else:
                    similarity = difflib.SequenceMatcher(None, target, line_norm).ratio()
                    sub_sim = 0
                    if not is_short and target in line_norm:
                        sub_sim = target_len / len(line_norm)
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
    
    matches.sort(key=lambda x: (x["similarity"], x["confidence"]), reverse=True)
    return matches

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
        Supports native PDFs, scanned PDFs, image-embedded PDFs, and direct images.
        """
        try:
            logger.info(
                f"[DI] Submitting document — "
                f"size={len(content)} bytes, content_type={content_type}, "
                f"endpoint={self._endpoint}"
            )

            headers = {
                "Content-Type": content_type,
                "Accept": "application/json",
            }
            if self._api_key:
                headers["Ocp-Apim-Subscription-Key"] = self._api_key

            # ocrHighResolution improves OCR accuracy for photographed/scanned documents
            # and image-embedded PDFs (e.g. photos inserted in Word then converted to PDF).
            params = {
                "api-version": "2024-11-30",
                "features": "ocrHighResolution",
            }

            submit_url = f"{self._endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze"
            logger.info(f"[DI] POST {submit_url} | params={params}")

            async with httpx.AsyncClient(timeout=180) as client:
                submit_resp = await client.post(
                    submit_url,
                    content=content,
                    headers=headers,
                    params=params,
                )
                logger.info(f"[DI] Submit response — HTTP {submit_resp.status_code}")

                if submit_resp.status_code != 202:
                    logger.error(
                        f"[DI] Unexpected submit status {submit_resp.status_code}. "
                        f"Body: {submit_resp.text[:500]}"
                    )
                submit_resp.raise_for_status()

                operation_url = submit_resp.headers.get("Operation-Location")
                if not operation_url:
                    raise ValueError("Document Intelligence service did not return an operation URL.")
                logger.info(f"[DI] Operation URL received — polling started")

                # Poll for completion — image-heavy PDFs can take 2-3 minutes
                for attempt in range(60):
                    await asyncio.sleep(3)
                    result_resp = await client.get(operation_url, headers=headers)

                    if result_resp.status_code != 200:
                        logger.error(
                            f"[DI] Poll HTTP {result_resp.status_code} on attempt {attempt + 1}. "
                            f"Body: {result_resp.text[:300]}"
                        )
                    result_resp.raise_for_status()
                    result = result_resp.json()

                    status = result.get("status")
                    if status == "succeeded":
                        analyze_result = result.get("analyzeResult", {})
                        content_text = analyze_result.get("content", "")
                        page_count = len(analyze_result.get("pages", []))
                        word_count = sum(len(p.get("words", [])) for p in analyze_result.get("pages", []))
                        logger.info(
                            f"[DI] SUCCESS — "
                            f"pages={page_count}, "
                            f"words={word_count}, "
                            f"content_length={len(content_text)}, "
                            f"completed_on_attempt={attempt + 1}"
                        )
                        if not content_text:
                            logger.warning(
                                f"[DI] WARNING — DI returned 0 content despite success "
                                f"(pages={page_count}, words={word_count}). "
                                f"The document may contain unreadable images or very low quality scans."
                            )
                        return analyze_result

                    elif status == "failed":
                        error = result.get("error", {})
                        logger.error(f"[DI] FAILED — error={error}")
                        raise RuntimeError(f"DI analysis failed: {error}")

                    else:
                        if attempt % 5 == 0:
                            logger.info(f"[DI] Still processing... status={status}, attempt={attempt + 1}/60")

                logger.error(f"[DI] TIMEOUT — operation did not complete within 180 seconds")
                raise TimeoutError("DI operation timed out after 180 seconds.")

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[DI] HTTP error — status={e.response.status_code}, "
                f"url={e.request.url}, "
                f"body={e.response.text[:500]}"
            )
            raise
        except Exception as e:
            logger.error(f"[DI] Unexpected error — {type(e).__name__}: {e}")
            raise
    


    def find_field_in_lines(self, analyze_result: Dict[str, Any], search_value: str) -> List[Dict[str, Any]]:
        """
        Searches for a specific value in the DI lines and words and returns its polygons.
        Proxies to the standalone find_field_worker.
        """
        return find_field_worker(analyze_result, search_value)

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
