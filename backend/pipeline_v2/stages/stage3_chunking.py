"""
Stage 3 — Chunking
Builds a ChunkMap from parsed documents.
Each chunk tracks text + word_map (every word with its bbox).
This is the foundation for Stage 8 coordinate resolution.

Chunking strategy (priority order):
1. ADI-identified section headings → use as chunk boundaries
2. No headings → paragraph groups (max V2_CHUNK_MAX_WORDS words per chunk)
3. Tables → each table gets its own chunk
"""

import logging
from typing import Dict, List

from pipeline_v2.config import v2_settings
from pipeline_v2.models import ChunkData, ParsedDocument, WordLocation

logger = logging.getLogger(__name__)


def _approximate_position(page_number: int, page_count: int) -> str:
    if page_count <= 1:
        return "middle_third"
    ratio = (page_number - 1) / max(page_count - 1, 1)
    if ratio < 0.33:
        return "top_third"
    if ratio < 0.67:
        return "middle_third"
    return "bottom_third"


def _words_for_page(parsed_doc: ParsedDocument, page_number: int) -> List[WordLocation]:
    """Extract WordLocation objects for a specific page."""
    for page in parsed_doc.pages:
        if page.get("page_number") == page_number:
            return [
                WordLocation(
                    word=w["word"],
                    bbox=w["bbox"],
                    page_number=w["page_number"],
                )
                for w in page.get("words", [])
                if w.get("word") and w.get("bbox")
            ]
    return []


def _words_in_text_range(all_words: List[WordLocation], text: str) -> List[WordLocation]:
    """
    Return subset of words that are likely part of the given text block.
    We use a simple approach: words whose content appears in the text.
    This is a best-effort for chunk word_map building.
    """
    text_lower = text.lower()
    return [w for w in all_words if w.word.lower() in text_lower]


def _chunk_document(parsed_doc: ParsedDocument) -> List[ChunkData]:
    chunks: List[ChunkData] = []
    filename = parsed_doc.filename
    blob_url = parsed_doc.blob_url
    page_count = parsed_doc.page_count
    max_words = v2_settings.v2_chunk_max_words

    # Build a flat list of all words across all pages for word_map assignment
    all_words_by_page: Dict[int, List[WordLocation]] = {}
    for page in parsed_doc.pages:
        pn = page.get("page_number", 1)
        all_words_by_page[pn] = [
            WordLocation(word=w["word"], bbox=w["bbox"], page_number=w["page_number"])
            for w in page.get("words", [])
            if w.get("word") and w.get("bbox")
        ]

    chunk_idx = 0

    def _make_chunk(text: str, page_number: int, heading: str = None) -> ChunkData:
        nonlocal chunk_idx
        chunk_idx += 1
        words = _words_in_text_range(all_words_by_page.get(page_number, []), text)
        return ChunkData(
            chunk_id=f"{filename}::CHUNK_{chunk_idx:03d}",
            document_name=filename,
            blob_url=blob_url,
            page_number=page_number,
            section_heading=heading,
            approximate_position=_approximate_position(page_number, page_count),
            text=text,
            word_map=words,
        )

    # Strategy 1: Use ADI paragraphs with section headings as boundaries
    if parsed_doc.paragraphs:
        current_heading = None
        current_parts: List[str] = []
        current_page = 1
        current_word_count = 0

        for para in parsed_doc.paragraphs:
            role = para.get("role")
            text = para.get("text", "").strip()
            page = para.get("page_number", 1)

            if not text:
                continue

            if role in ("title", "sectionHeading"):
                # Flush current buffer
                if current_parts:
                    chunk_text = "\n".join(current_parts)
                    chunks.append(_make_chunk(chunk_text, current_page, current_heading))
                    current_parts = []
                    current_word_count = 0
                current_heading = text
                current_page = page
                continue

            word_count = len(text.split())

            # Flush if buffer would exceed max words
            if current_word_count + word_count > max_words and current_parts:
                chunk_text = "\n".join(current_parts)
                chunks.append(_make_chunk(chunk_text, current_page, current_heading))
                current_parts = []
                current_word_count = 0

            current_parts.append(text)
            current_word_count += word_count
            current_page = page

        if current_parts:
            chunks.append(_make_chunk("\n".join(current_parts), current_page, current_heading))

    # Strategy 2: Fallback — use full_text split into word-count windows
    if not chunks and parsed_doc.full_text:
        words = parsed_doc.full_text.split()
        page_number = 1
        for i in range(0, len(words), max_words):
            chunk_words = words[i: i + max_words]
            chunk_text = " ".join(chunk_words)
            # Estimate page: distribute evenly
            page_number = max(1, round((i / max(len(words), 1)) * page_count) + 1)
            page_number = min(page_number, page_count)
            chunks.append(_make_chunk(chunk_text, page_number))

    # Strategy 3: Add each table as its own chunk
    for tidx, table in enumerate(parsed_doc.tables):
        rows = table.get("rows", [])
        table_lines = []
        page_number = 1
        for row in rows:
            cells = [c.get("content", "") for c in row]
            table_lines.append(" | ".join(cells))
            if row and row[0].get("page_number"):
                page_number = row[0]["page_number"]
        if table_lines:
            table_text = "\n".join(table_lines)
            chunks.append(_make_chunk(table_text, page_number, heading=f"Table {tidx + 1}"))

    if not chunks and parsed_doc.full_text:
        chunks.append(_make_chunk(parsed_doc.full_text[:5000], 1))

    logger.info(f"[Stage3] {filename}: {len(chunks)} chunks")
    return chunks


def run(parsed_docs: List[ParsedDocument]) -> Dict[str, ChunkData]:
    """Build a flat chunk_map: {chunk_id -> ChunkData} across all documents."""
    chunk_map: Dict[str, ChunkData] = {}
    for doc in parsed_docs:
        for chunk in _chunk_document(doc):
            chunk_map[chunk.chunk_id] = chunk
    logger.info(f"[Stage3] Total chunks in map: {len(chunk_map)}")
    return chunk_map
