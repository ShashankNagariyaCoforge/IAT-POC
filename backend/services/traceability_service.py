"""
Traceability service — resolves a verbatim raw_text phrase to a bounding box
inside an Azure Document Intelligence analyze_result.

Approach: anchor + verify (no full sliding window scan)
  1. Pick first distinctive word from raw_text (skip short stopwords)
  2. Find all positions in the page word list where that word appears (O(N) scan)
  3. At each anchor position, run rapidfuzz on a window = len(raw_text tokens) ± 3
  4. Accept the first window that scores above threshold
  5. Compute spanning bbox [x1, y1, x2, y2] from matched words

Polygon format from ADI is 8-point [x0,y0,x1,y1,x2,y2,x3,y3].
We convert to [x1, y1, x2, y2] = [min_x, min_y, max_x, max_y].
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Words too common to be reliable anchors
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "to", "for", "is", "are",
    "was", "were", "be", "been", "by", "on", "at", "as", "it", "its",
    "with", "from", "that", "this", "have", "has", "had", "not", "but",
    "we", "our", "you", "he", "she", "they", "their", "will", "would",
}

_FUZZY_THRESHOLD = 78  # minimum rapidfuzz ratio (0-100) to accept a match


def _poly_to_bbox(polygon: List[float]) -> Optional[List[float]]:
    """Convert ADI 8-point polygon → [x1, y1, x2, y2]."""
    if not polygon or len(polygon) < 6:
        return None
    xs = polygon[0::2]
    ys = polygon[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = re.sub(r"[^\w\s]", " ", text)
    return " ".join(t.lower().split())


def _anchor_word(tokens: List[str]) -> Optional[str]:
    """Pick first token that is long enough and not a stopword."""
    for tok in tokens:
        if len(tok) >= 3 and tok not in _STOPWORDS:
            return tok
    # Fallback: just use the first token whatever it is
    return tokens[0] if tokens else None


def _span_bbox(words_in_window: List[Dict]) -> Optional[List[float]]:
    """Compute spanning [x1,y1,x2,y2] across a list of word dicts."""
    bboxes = []
    for w in words_in_window:
        poly = w.get("polygon")
        if poly:
            bb = _poly_to_bbox(poly)
            if bb:
                bboxes.append(bb)
    if not bboxes:
        return None
    x1 = min(b[0] for b in bboxes)
    y1 = min(b[1] for b in bboxes)
    x2 = max(b[2] for b in bboxes)
    y2 = max(b[3] for b in bboxes)
    return [x1, y1, x2, y2]


def resolve_bbox(
    raw_text: str,
    analyze_result: Dict[str, Any],
    threshold: int = _FUZZY_THRESHOLD,
) -> Optional[Dict[str, Any]]:
    """
    Find raw_text in the OCR analyze_result and return location metadata.

    Returns:
        {
            "bbox": [x1, y1, x2, y2],
            "page": 1,
            "page_width": 8.5,
            "page_height": 11.0,
            "unit": "inch"
        }
        or None if not found.
    """
    if not raw_text or not analyze_result:
        return None

    query_norm = _normalize(raw_text)
    query_tokens = query_norm.split()
    if not query_tokens:
        return None

    anchor = _anchor_word(query_tokens)
    if not anchor:
        return None

    query_len = len(query_tokens)
    pages = analyze_result.get("pages", [])

    for page in pages:
        page_num = page.get("pageNumber", 1)
        page_w = page.get("width")
        page_h = page.get("height")
        unit = page.get("unit", "inch")
        words = page.get("words", [])

        if not words:
            continue

        # Normalize all words once per page
        norm_words = [_normalize(w.get("content", w.get("text", ""))) for w in words]

        # Step 1: find anchor positions
        anchor_positions = [i for i, nw in enumerate(norm_words) if nw == anchor]

        if not anchor_positions:
            # Partial match fallback for anchor (handles OCR noise in the anchor word itself)
            anchor_positions = [
                i for i, nw in enumerate(norm_words)
                if nw and fuzz.ratio(anchor, nw) >= 85
            ]

        if not anchor_positions:
            continue

        # Step 2: verify at each anchor with window of query_len ± 3
        best_score = 0
        best_window_words = []

        for anchor_pos in anchor_positions:
            # Figure out how far back the anchor could be within the query
            # (anchor might not be the first token of the window)
            anchor_idx_in_query = query_tokens.index(anchor) if anchor in query_tokens else 0
            start_range = max(0, anchor_pos - anchor_idx_in_query - 3)
            end_range = anchor_pos + (query_len - anchor_idx_in_query) + 3

            for w_size in range(max(1, query_len - 3), query_len + 4):
                for start in range(start_range, min(end_range, len(words) - w_size + 1)):
                    window_norm = " ".join(norm_words[start: start + w_size])
                    score = fuzz.ratio(query_norm, window_norm)
                    if score > best_score:
                        best_score = score
                        best_window_words = words[start: start + w_size]
                    if best_score >= 97:
                        break
                if best_score >= 97:
                    break

        if best_score >= threshold and best_window_words:
            bbox = _span_bbox(best_window_words)
            if bbox:
                logger.debug(
                    f"[Traceability] Matched '{raw_text[:50]}' on page {page_num} "
                    f"score={best_score} bbox={bbox}"
                )
                return {
                    "bbox": bbox,
                    "page": page_num,
                    "page_width": page_w,
                    "page_height": page_h,
                    "unit": unit,
                }

    logger.debug(f"[Traceability] No match found for: '{raw_text[:60]}'")
    return None
