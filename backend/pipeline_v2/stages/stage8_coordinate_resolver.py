"""
Stage 8 — Coordinate Resolution (Pure Python, No LLM)
Maps extracted field raw_text → bbox in document using rapidfuzz sliding window
over the chunk's word_map. This replaces the old whole-document word scan.

Why this is more accurate than the old approach:
- LLM told us WHICH CHUNK the value came from → smaller search space
- We match the verbatim context phrase (10-25 words) → more unique than just the value
- rapidfuzz handles minor OCR variations
"""

import logging
from typing import Dict, List, Optional, Tuple

from pipeline_v2.config import v2_settings
from pipeline_v2.models import (
    ChunkData, ExtractedFieldRaw, FieldSource, SourceLocation, WordLocation,
)

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    return text.lower().split()


def _words_bbox(words: List[WordLocation]) -> Optional[List[float]]:
    """Compute bounding box spanning all words."""
    if not words:
        return None
    x1 = min(w.bbox[0] for w in words if w.bbox)
    y1 = min(w.bbox[1] for w in words if w.bbox)
    x2 = max(w.bbox[2] for w in words if w.bbox)
    y2 = max(w.bbox[3] for w in words if w.bbox)
    return [x1, y1, x2, y2]


def _fuzzy_match_in_chunk(
    raw_text: str,
    chunk: ChunkData,
    threshold: int,
) -> Tuple[Optional[List[float]], float]:
    """
    Sliding window fuzzy match of raw_text against chunk.word_map.
    Returns (bbox, score) of best match, or (None, 0.0) if below threshold.
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        logger.warning("[Stage8] rapidfuzz not installed — returning chunk-level bbox fallback")
        return None, 0.0

    if not chunk.word_map or not raw_text:
        return None, 0.0

    query_tokens = _tokenize(raw_text)
    if not query_tokens:
        return None, 0.0

    chunk_words = chunk.word_map
    window_size = min(len(query_tokens), len(chunk_words))
    query_str = " ".join(query_tokens)

    best_score = 0.0
    best_words: List[WordLocation] = []

    # Slide windows of decreasing size (start with exact length, then ±3)
    for w_size in range(max(1, window_size - 3), window_size + 4):
        if w_size > len(chunk_words):
            continue
        for i in range(len(chunk_words) - w_size + 1):
            window = chunk_words[i: i + w_size]
            window_str = " ".join(token for w in window for token in _tokenize(w.word))
            score = fuzz.ratio(query_str, window_str)
            if score > best_score:
                best_score = score
                best_words = window
        if best_score >= 95:  # Early exit on near-perfect match
            break

    if best_score >= threshold and best_words:
        bbox = _words_bbox(best_words)
        return bbox, best_score / 100.0

    return None, 0.0


def _resolve_field(
    field: ExtractedFieldRaw,
    chunk_map: Dict[str, ChunkData],
    threshold: int,
) -> Optional[SourceLocation]:
    """
    Resolve a single extracted field to its SourceLocation with bbox.
    Tries the stated chunk first, then adjacent chunks if needed.
    """
    if not field.raw_text or not field.chunk_id:
        return None

    chunk = chunk_map.get(field.chunk_id)
    if not chunk:
        logger.debug(f"[Stage8] chunk_id not found: {field.chunk_id}")
        return None

    bbox, score = _fuzzy_match_in_chunk(field.raw_text, chunk, threshold)

    # If no match in stated chunk, try adjacent chunks (±1)
    if bbox is None:
        all_chunk_ids = sorted(chunk_map.keys())
        try:
            idx = all_chunk_ids.index(field.chunk_id)
        except ValueError:
            idx = -1

        for offset in (-1, 1, -2, 2):
            adj_idx = idx + offset
            if 0 <= adj_idx < len(all_chunk_ids):
                adj_chunk = chunk_map[all_chunk_ids[adj_idx]]
                if adj_chunk.document_name != chunk.document_name:
                    continue  # Don't cross document boundary
                bbox, score = _fuzzy_match_in_chunk(field.raw_text, adj_chunk, threshold)
                if bbox:
                    logger.debug(f"[Stage8] Found match in adjacent chunk {adj_chunk.chunk_id}")
                    chunk = adj_chunk
                    break

    if bbox is None:
        # Fallback: return chunk-level location without bbox
        logger.debug(
            f"[Stage8] No bbox match for field '{field.field_name}' in chunk {field.chunk_id} "
            f"(raw_text: {field.raw_text[:50]}...)"
        )

    return SourceLocation(
        document_name=chunk.document_name,
        blob_url=chunk.blob_url,
        page_number=chunk.page_number,
        bbox=bbox,
        chunk_id=chunk.chunk_id,
        section_heading=chunk.section_heading,
        approximate_position=chunk.approximate_position,
        raw_text=field.raw_text,
        extraction_source="llm_extraction",
    )


def run(
    extractions: Dict[str, List[ExtractedFieldRaw]],
    chunk_map: Dict[str, ChunkData],
) -> Dict[str, List[Tuple[ExtractedFieldRaw, Optional[SourceLocation]]]]:
    """
    Resolve coordinates for all extracted fields.
    Returns {source_document -> [(ExtractedFieldRaw, SourceLocation|None)]}.
    """
    threshold = v2_settings.v2_fuzzy_match_threshold
    resolved: Dict[str, List[Tuple[ExtractedFieldRaw, Optional[SourceLocation]]]] = {}

    for source_doc, fields in extractions.items():
        doc_results = []
        for field in fields:
            if field.value:
                location = _resolve_field(field, chunk_map, threshold)
            else:
                location = None
            doc_results.append((field, location))
        resolved[source_doc] = doc_results

    total_with_bbox = sum(
        1
        for doc_results in resolved.values()
        for _, loc in doc_results
        if loc and loc.bbox
    )
    total_fields = sum(
        1
        for doc_results in resolved.values()
        for f, _ in doc_results
        if f.value
    )
    logger.info(
        f"[Stage8] Resolved {total_with_bbox}/{total_fields} fields with bbox coordinates"
    )
    return resolved
