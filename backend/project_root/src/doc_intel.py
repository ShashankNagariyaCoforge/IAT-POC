# src/doc_intel.py
from typing import List, Dict, Any
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from config import AZURE_DOC_INTEL_ENDPOINT, AZURE_DOC_INTEL_KEY

def analyze_with_bboxes(file_path: str) -> List[Dict[str, Any]]:
    """
    Analyze a PDF or image with Azure Document Intelligence (prebuilt-read).
    Returns per-page dicts:
      {
        "width": float,
        "height": float,
        "unit": str,
        "page_number": int,
        "content": str,                # concatenated page lines text
        "lines": [ {text, polygon[8], confidence} ],
        "words": [ {text, polygon[8], confidence} ],
        "full_document_content": str   # only attached on the first page if available
      }
    """
    client = DocumentIntelligenceClient(
        endpoint=AZURE_DOC_INTEL_ENDPOINT,
        credential=AzureKeyCredential(AZURE_DOC_INTEL_KEY)
    )

    with open(file_path, "rb") as f:
        poller = client.begin_analyze_document(
            model_id="prebuilt-read",
            body=f
        )
    result = poller.result()

    pages_output: List[Dict[str, Any]] = []

    for p_idx, page in enumerate(getattr(result, "pages", []), start=1):
        page_dict: Dict[str, Any] = {
            "width": getattr(page, "width", None),
            "height": getattr(page, "height", None),
            "unit": getattr(page, "unit", "pixel"),
            "page_number": getattr(page, "page_number", p_idx),
            "content": "",
            "lines": [],
            "words": []
        }

        lines_text = []

        # Lines
        if hasattr(page, "lines") and page.lines:
            for line in page.lines:
                l_text = getattr(line, "content", "") or ""
                l_poly = _normalize_polygon(getattr(line, "polygon", None))
                l_conf = getattr(line, "confidence", None)
                if l_conf is None:
                    l_conf = _average_word_confidence(line)
                if l_text:
                    lines_text.append(l_text)
                if l_poly:
                    page_dict["lines"].append({
                        "text": l_text,
                        "polygon": l_poly,
                        "confidence": float(l_conf if l_conf is not None else 1.0)
                    })

                # Words (if exposed by SDK as line.words)
                if hasattr(line, "words") and line.words:
                    for w in line.words:
                        w_text = getattr(w, "content", "") or getattr(w, "text", "") or ""
                        w_poly = _normalize_polygon(getattr(w, "polygon", None))
                        w_conf = getattr(w, "confidence", None)
                        if w_poly and w_text:
                            page_dict["words"].append({
                                "text": w_text,
                                "polygon": w_poly,
                                "confidence": float(w_conf if w_conf is not None else 1.0)
                            })

        page_dict["content"] = "\n".join(lines_text)
        pages_output.append(page_dict)

    # Attach full document content if present
    if hasattr(result, "content") and isinstance(result.content, str) and pages_output:
        pages_output[0]["full_document_content"] = result.content

    return pages_output


def _average_word_confidence(line_obj) -> float:
    try:
        words = getattr(line_obj, "words", None)
        if not words:
            return 1.0
        vals = []
        for w in words:
            c = getattr(w, "confidence", None)
            if c is not None:
                vals.append(float(c))
        return sum(vals) / len(vals) if vals else 1.0
    except Exception:
        return 1.0


def _normalize_polygon(poly) -> list | None:
    """
    Return 8-number list [x1,y1,x2,y2,x3,y3,x4,y4] or None.
    Handles list[float] or list[Point-like] where point has .x and .y
    """
    if not poly:
        return None
    if isinstance(poly, list) and len(poly) == 8 and all(isinstance(v, (int, float)) for v in poly):
        return [float(v) for v in poly]
    try:
        coords = []
        for pt in poly:
            x = getattr(pt, "x", None)
            y = getattr(pt, "y", None)
            if x is None or y is None:
                # maybe [x, y] list
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    x, y = pt
                else:
                    return None
            coords.extend([float(x), float(y)])
        if len(coords) == 8:
            return coords
    except Exception:
        return None
    return None