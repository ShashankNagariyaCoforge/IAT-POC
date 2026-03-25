"""
OCR Client — Azure Document Intelligence wrapper.
Returns structured output optimised for chunking and coordinate resolution.
Polygon (8 points) → bbox [x1, y1, x2, y2] conversion happens here.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from pipeline_v2.config import v2_settings
from config import settings as base_settings

logger = logging.getLogger(__name__)


def _poly_to_bbox(polygon: Optional[List[float]]) -> Optional[List[float]]:
    """Convert ADI 8-point polygon to [x1, y1, x2, y2]."""
    if not polygon or len(polygon) < 8:
        return None
    xs = polygon[0::2]
    ys = polygon[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def _get_creds():
    endpoint = (v2_settings.v2_adi_endpoint or base_settings.doc_intelligence_endpoint or "").rstrip("/")
    key = v2_settings.v2_adi_key or base_settings.doc_intelligence_key
    return endpoint, key


async def analyze_document(content: bytes, content_type: str) -> Dict[str, Any]:
    """
    Run Azure Document Intelligence prebuilt-layout on document bytes.
    Returns structured dict with pages (words+lines with bboxes) and paragraphs.
    """
    endpoint, api_key = _get_creds()
    if not endpoint or not api_key:
        raise RuntimeError("ADI endpoint/key not configured (V2_ADI_ENDPOINT / V2_ADI_KEY or existing DOC_INTELLIGENCE_*)")

    headers = {
        "Content-Type": content_type,
        "Ocp-Apim-Subscription-Key": api_key,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        submit = await client.post(
            f"{endpoint}/formrecognizer/documentModels/prebuilt-layout:analyze",
            content=content,
            headers=headers,
            params={"api-version": "2023-07-31"},
        )
        submit.raise_for_status()

        operation_url = submit.headers.get("Operation-Location")
        if not operation_url:
            raise RuntimeError("ADI did not return Operation-Location header")

        for _ in range(40):
            await asyncio.sleep(2)
            poll = await client.get(operation_url, headers={"Ocp-Apim-Subscription-Key": api_key})
            poll.raise_for_status()
            data = poll.json()
            if data.get("status") == "succeeded":
                return _parse_adi_result(data.get("analyzeResult", {}))
            if data.get("status") == "failed":
                raise RuntimeError(f"ADI analysis failed: {data.get('error')}")

    raise TimeoutError("ADI polling timed out")


def _parse_adi_result(adi: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform raw ADI analyzeResult into clean structured format.
    Each word and paragraph gets a [x1,y1,x2,y2] bbox.
    """
    pages_out = []
    full_text_parts = []

    for page in adi.get("pages", []):
        page_num = page.get("pageNumber", 1)
        width = page.get("width")
        height = page.get("height")
        unit = page.get("unit", "inch")

        words_out = []
        for w in page.get("words", []):
            bbox = _poly_to_bbox(w.get("polygon"))
            if bbox:
                words_out.append({
                    "word": w.get("content", ""),
                    "bbox": bbox,
                    "page_number": page_num,
                    "confidence": w.get("confidence", 1.0),
                })

        lines_out = []
        for ln in page.get("lines", []):
            bbox = _poly_to_bbox(ln.get("polygon"))
            lines_out.append({
                "text": ln.get("content", ""),
                "bbox": bbox,
                "page_number": page_num,
            })
            full_text_parts.append(ln.get("content", ""))

        pages_out.append({
            "page_number": page_num,
            "width": width,
            "height": height,
            "unit": unit,
            "words": words_out,
            "lines": lines_out,
        })

    paragraphs_out = []
    for para in adi.get("paragraphs", []):
        regions = para.get("boundingRegions", [{}])
        page_num = regions[0].get("pageNumber", 1) if regions else 1
        bbox = _poly_to_bbox(regions[0].get("polygon")) if regions else None
        paragraphs_out.append({
            "text": para.get("content", ""),
            "role": para.get("role"),       # sectionHeading | title | paragraph | etc.
            "page_number": page_num,
            "bbox": bbox,
        })

    # Extract tables
    tables_out = []
    for tidx, table in enumerate(adi.get("tables", [])):
        rows: Dict[int, list] = {}
        for cell in table.get("cells", []):
            r = cell.get("rowIndex", 0)
            regions = cell.get("boundingRegions", [{}])
            bbox = _poly_to_bbox(regions[0].get("polygon")) if regions else None
            page_num = regions[0].get("pageNumber", 1) if regions else 1
            rows.setdefault(r, []).append({
                "content": cell.get("content", ""),
                "col": cell.get("columnIndex", 0),
                "bbox": bbox,
                "page_number": page_num,
            })
        sorted_rows = [sorted(rows[r], key=lambda c: c["col"]) for r in sorted(rows)]
        tables_out.append({
            "id": f"table_{tidx}",
            "row_count": table.get("rowCount"),
            "col_count": table.get("columnCount"),
            "rows": sorted_rows,
        })

    return {
        "pages": pages_out,
        "paragraphs": paragraphs_out,
        "tables": tables_out,
        "full_text": "\n".join(full_text_parts),
    }
