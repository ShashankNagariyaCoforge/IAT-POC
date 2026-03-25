# Extraction Traceability — Click-to-Highlight in Document AI

## The Skill in One Sentence

When an LLM extracts a value from a document, make it also tell you **which exact phrase it used** and **which chunk of text it found it in** — then use pure Python to locate those words in the OCR word map, compute a bounding box, and pass `[x1, y1, x2, y2]` + page metadata to the frontend so a single click highlights the source in the rendered PDF.

---

## Why This Is Hard Without This Approach

The naive approach is to ask the LLM to return coordinates. **Don't do that.** LLMs cannot reliably produce pixel/point coordinates — they hallucinate them. The correct split of responsibility is:

| Stage | Who does it | What |
|-------|-------------|------|
| OCR | Azure Document Intelligence | Produces per-word bounding polygons |
| Chunking | Python | Groups words into labelled chunks, preserves the word map |
| Extraction | LLM | Extracts value + verbatim context phrase + chunk ID |
| Coordinate resolution | Python (rapidfuzz) | Fuzzy-matches context phrase against word map → bbox |
| Rendering | Frontend (react-pdf + CSS) | Overlays a `<div>` using percentage coordinates |

---

## Stage 1 — OCR: What You Need to Preserve

Azure Document Intelligence (ADI) `prebuilt-layout` model returns, for each page, a list of words each with an 8-point bounding polygon:

```json
{
  "content": "CRC",
  "polygon": [1.02, 3.44, 1.38, 3.44, 1.38, 3.58, 1.02, 3.58],
  "confidence": 0.997
}
```

The polygon is `[x0,y0, x1,y1, x2,y2, x3,y3]` (four corners, clockwise from top-left). Convert it to `[x1, y1, x2, y2]` by taking min/max:

```python
def _poly_to_bbox(polygon: list[float]) -> list[float]:
    xs = polygon[0::2]   # every even index
    ys = polygon[1::2]   # every odd index
    return [min(xs), min(ys), max(xs), max(ys)]
```

The unit is whatever ADI reports in `page.unit` — usually `"inch"`. Also preserve per-page `width` and `height` in the same unit.

**Minimum data to keep per word:**

```python
{
    "word": "CRC",
    "bbox": [1.02, 3.44, 1.38, 3.58],   # [x1, y1, x2, y2] in page units
    "page_number": 1,
}
```

**Minimum data to keep per page:**

```python
{
    "page_number": 1,
    "width": 8.5,    # inches (or pixels depending on unit)
    "height": 11.0,
    "unit": "inch",
    "words": [ ... ]   # list of word dicts above
}
```

---

## Stage 2 — Chunking: Building the Word Map

A **chunk** is a logically coherent section of a document (a paragraph, a section under a heading, a table). The critical addition over plain text chunking is: **each chunk carries a `word_map` — the list of all word objects (with bboxes) that belong to that chunk's text**.

### Chunk ID Format

```
"{filename}::CHUNK_{n:03d}"
# e.g. "claim_form.pdf::CHUNK_007"
```

This is the key the LLM will return to tell you where it found a value.

### Chunk Data Structure

```python
class WordLocation:
    word: str
    bbox: list[float]    # [x1, y1, x2, y2]
    page_number: int

class ChunkData:
    chunk_id: str              # "filename.pdf::CHUNK_007"
    document_name: str         # "filename.pdf"
    blob_url: str              # URL to the stored document
    page_number: int           # which page this chunk is primarily on
    section_heading: str|None  # nearest heading above this chunk
    approximate_position: str  # "top_third" | "middle_third" | "bottom_third"
    text: str                  # clean text for the LLM prompt
    word_map: list[WordLocation]  # every word with its bbox — for Stage 8
```

### Chunking Strategy (Priority Order)

1. **ADI section headings** — Use `role == "sectionHeading" | "title"` as boundaries. Every paragraph under a heading becomes part of that chunk.
2. **Word-count limit** — If a section is too long, flush at `max_words` (e.g. 300). Never split mid-sentence.
3. **Tables** — Each table becomes its own chunk with its text serialised as `col1 | col2 | col3`.
4. **Fallback** — If no ADI paragraphs, split `full_text` by word count.

### Building the word_map for a chunk

The simplest correct approach: **collect all OCR words from the chunk's page whose text appears in the chunk text**.

```python
def _words_in_text_range(page_words: list[WordLocation], chunk_text: str) -> list[WordLocation]:
    text_lower = chunk_text.lower()
    return [w for w in page_words if w.word.lower() in text_lower]
```

This is a best-effort filter. It works well in practice because chunks are typically 50–300 words from a single page section, so word-level collisions are rare. More precise alternatives (span matching using character offsets) exist but require ADI's span data.

### The Chunk Map

```python
chunk_map: dict[str, ChunkData]  # chunk_id → ChunkData
```

This is the lookup table for Stage 8. Build it once, pass it through the whole pipeline.

---

## Stage 3 — LLM Extraction Prompt: The Critical Instructions

The LLM prompt must instruct the model to return **three things per extracted field**, not just the value:

```
For each field return:
  - value: the normalised extracted value
  - raw_text: the EXACT VERBATIM phrase from the document (include 10-25 surrounding
              words for context). This must be copied word-for-word. Never paraphrase.
  - chunk_id: copy exactly from the chunk label (e.g. "claim_form.pdf::CHUNK_003")
  - confidence: 0.0–1.0
```

Present document chunks to the LLM with the chunk ID as a visible label:

```
[claim_form.pdf::CHUNK_001]
INSURED INFORMATION
Name of Insured: CRC Speciality Hospital, registered under...

[claim_form.pdf::CHUNK_002]
Policy Number: POL-2024-00123
Effective Date: 01 Feb 2024 to 01 Feb 2025...
```

**Why `raw_text` over just the value?**
The value alone is often 1–3 words. A fuzzy match of 1–3 words in a 300-word chunk returns many false positives. A 10–25-word verbatim phrase is nearly unique within a chunk and tolerates minor OCR noise (OCR reads `0` as `O`, `l` as `1`, etc.).

**Example LLM output:**

```json
{
  "insured_name": {
    "value": "CRC Speciality Hospital",
    "raw_text": "Name of Insured: CRC Speciality Hospital, registered under the Companies",
    "chunk_id": "claim_form.pdf::CHUNK_001",
    "confidence": 0.96
  },
  "policy_number": {
    "value": "POL-2024-00123",
    "raw_text": "Policy Number: POL-2024-00123\nEffective Date: 01 Feb 2024",
    "chunk_id": "claim_form.pdf::CHUNK_002",
    "confidence": 0.98
  }
}
```

---

## Stage 4 — Coordinate Resolution: Pure Python

This stage takes `raw_text + chunk_id` and returns a `bbox`.

### Algorithm

```python
from rapidfuzz import fuzz

def resolve_coordinates(raw_text: str, chunk_id: str, chunk_map: dict) -> list[float] | None:
    chunk = chunk_map.get(chunk_id)
    if not chunk or not chunk.word_map:
        return None   # fallback: try adjacent chunks (see below)

    query_tokens = raw_text.lower().split()
    window_size = len(query_tokens)
    query_str = " ".join(query_tokens)

    best_score = 0.0
    best_words = []

    # Slide a window of ±3 tokens around the expected size
    for w_size in range(max(1, window_size - 3), window_size + 4):
        if w_size > len(chunk.word_map):
            continue
        for i in range(len(chunk.word_map) - w_size + 1):
            window = chunk.word_map[i : i + w_size]
            window_str = " ".join(w.word.lower() for w in window)
            score = fuzz.ratio(query_str, window_str)
            if score > best_score:
                best_score = score
                best_words = window
        if best_score >= 95:
            break   # near-perfect match found, stop early

    if best_score >= threshold and best_words:  # threshold ≈ 80
        return compute_bbox(best_words)         # min/max of individual bboxes

    return None   # below threshold → no reliable location
```

### Computing the Spanning Bbox

```python
def compute_bbox(words: list[WordLocation]) -> list[float]:
    x1 = min(w.bbox[0] for w in words)
    y1 = min(w.bbox[1] for w in words)
    x2 = max(w.bbox[2] for w in words)
    y2 = max(w.bbox[3] for w in words)
    return [x1, y1, x2, y2]
```

### Fallback: Adjacent Chunks

If no match is found in the stated chunk (LLM sometimes gets the chunk ID slightly wrong, or the phrase spans a chunk boundary):

```python
# Sort all chunk IDs for this document; try ±1, ±2 neighbours
all_ids = sorted(k for k in chunk_map if chunk_map[k].document_name == chunk.document_name)
idx = all_ids.index(chunk_id)
for offset in (-1, 1, -2, 2):
    adj_chunk = chunk_map.get(all_ids[idx + offset])
    if adj_chunk:
        bbox = fuzzy_match(raw_text, adj_chunk)
        if bbox:
            return bbox
```

If still no match: return `None` and let the UI fall back to page-level (no highlight, but still navigates to the right page).

---

## Stage 5 — What to Pass to the API Response

For each extracted field, include a `traceability` object:

```json
{
  "insured_name": {
    "value": "CRC Speciality Hospital",
    "confidence": 0.96,
    "status": "accepted",
    "traceability": {
      "doc_id": "uuid-of-document",
      "document_name": "claim_form.pdf",
      "blob_url": "https://storage.blob.core.windows.net/...",
      "page_number": 1,
      "bbox": [1.02, 3.44, 4.87, 3.62],
      "page_width": 8.5,
      "page_height": 11.0,
      "coordinate_unit": "inch",
      "raw_text": "Name of Insured: CRC Speciality Hospital, registered under",
      "chunk_id": "claim_form.pdf::CHUNK_001",
      "section_heading": "Insured Information",
      "extraction_source": "llm_extraction"
    }
  }
}
```

**Critical fields for the UI:**

| Field | Purpose |
|-------|---------|
| `blob_url` | Where to load the PDF |
| `page_number` | Which page to render |
| `bbox` | The highlight rectangle in document units |
| `page_width` + `page_height` | The page's full dimensions in the same unit |
| `coordinate_unit` | `"inch"` or `"pixel"` (for the maths below) |

If `bbox` is `null` (coordinate resolution failed), the UI still navigates to the correct page — it just doesn't draw a highlight rectangle.

---

## Stage 6 — Frontend: Rendering the Highlight

### The Core Insight: Percentage Coordinates

You do **not** need to know the pixel dimensions of the rendered PDF canvas. Convert the ADI coordinates to percentages of the page, then apply them as CSS `position: absolute` on a `<div>` overlaid on the rendered page. The percentages work at **any zoom level or container width** automatically.

```typescript
// highlight: { bbox, page_width, page_height, page, ... }

const [x1, y1, x2, y2] = highlight.bbox;

const style = {
    position: 'absolute' as const,
    pointerEvents: 'none',
    left:   `${(x1 / highlight.page_width)  * 100}%`,
    top:    `${(y1 / highlight.page_height) * 100}%`,
    width:  `${((x2 - x1) / highlight.page_width)  * 100}%`,
    height: `${((y2 - y1) / highlight.page_height) * 100}%`,
    border: '2px solid #6366f1',
    background: 'rgba(99, 102, 241, 0.18)',
    borderRadius: '3px',
};
```

### React Implementation (react-pdf)

```tsx
import { Document, Page } from 'react-pdf';

function PdfWithHighlight({ url, highlight }) {
    return (
        // position: relative makes the overlay div's absolute positioning work
        <div style={{ position: 'relative', display: 'inline-block' }}>
            <Document file={url}>
                <Page
                    pageNumber={highlight.page}
                    renderTextLayer={false}      // disable — prevents z-index conflicts
                    renderAnnotationLayer={false}
                />
            </Document>

            {/* Highlight overlay */}
            {highlight.bbox && (
                <div style={{
                    position: 'absolute',
                    pointerEvents: 'none',
                    left:   `${(highlight.bbox[0] / highlight.page_width)  * 100}%`,
                    top:    `${(highlight.bbox[1] / highlight.page_height) * 100}%`,
                    width:  `${((highlight.bbox[2] - highlight.bbox[0]) / highlight.page_width)  * 100}%`,
                    height: `${((highlight.bbox[3] - highlight.bbox[1]) / highlight.page_height) * 100}%`,
                    border: '2px solid #6366f1',
                    background: 'rgba(99, 102, 241, 0.18)',
                    borderRadius: '3px',
                }} />
            )}
        </div>
    );
}
```

### What Triggers the Highlight

When the user clicks a field name in the extracted-fields list:

```typescript
function onFieldClick(field) {
    const t = field.traceability;
    if (!t?.bbox) return;          // no coordinates — open PDF browse mode instead

    setActivePdf({
        url: t.blob_url,
        name: t.document_name,
        highlight: {
            page:        t.page_number,
            bbox:        t.bbox,
            page_width:  t.page_width,
            page_height: t.page_height,
            coordinate_unit: t.coordinate_unit,
        }
    });
}
```

The `<InlinePdfViewer>` receives the `highlight` prop and automatically:
1. Renders only the target page (not the whole PDF) using `react-pdf`
2. Overlays the highlight `<div>` using percentage CSS
3. Re-jumps to the new page whenever the user clicks a different field

---

## Data Flow Diagram

```
  PDF/image bytes
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Azure Document Intelligence (prebuilt-layout) │
  │  Returns: per-word bboxes, paragraphs, tables  │
  │  Polygon [8 pts] → bbox [x1,y1,x2,y2]          │
  └──────────────────┬──────────────────────────┘
                     │  ParsedDocument
                     ▼
  ┌─────────────────────────────────────────────┐
  │  Stage 3: Chunking                           │
  │  Split by headings / word-count / tables     │
  │  Each chunk: id, text, word_map (bbox/word)  │
  └──────────────────┬──────────────────────────┘
                     │  chunk_map: {chunk_id → ChunkData}
                     ▼
  ┌─────────────────────────────────────────────┐
  │  Stage 7: LLM Extraction                     │
  │  Prompt includes chunk text with chunk IDs   │
  │  LLM returns: value + raw_text + chunk_id    │
  └──────────────────┬──────────────────────────┘
                     │  ExtractedFieldRaw per field
                     ▼
  ┌─────────────────────────────────────────────┐
  │  Stage 8: Coordinate Resolution (Python)     │
  │  rapidfuzz sliding-window on chunk.word_map  │
  │  Outputs bbox [x1,y1,x2,y2] per field        │
  └──────────────────┬──────────────────────────┘
                     │  SourceLocation with bbox
                     ▼
  ┌─────────────────────────────────────────────┐
  │  API Response                                │
  │  field.traceability = {bbox, page_number,    │
  │    page_width, page_height, blob_url, ...}   │
  └──────────────────┬──────────────────────────┘
                     │  JSON
                     ▼
  ┌─────────────────────────────────────────────┐
  │  Frontend (react-pdf)                        │
  │  User clicks field → renders target page     │
  │  Absolute <div> at (x1/W)%, (y1/H)%         │
  │  Width = (x2-x1)/W %, Height = (y2-y1)/H %  │
  └─────────────────────────────────────────────┘
```

---

## Dependencies

### Backend
```
azure-ai-documentintelligence >= 1.0.0   # OCR + word-level bboxes
rapidfuzz >= 3.6.0                        # fuzzy matching for Stage 8
```

### Frontend
```
react-pdf          # renders individual PDF pages (not the whole PDF)
pdfjs-dist         # required peer dependency
```

> **Why react-pdf instead of an iframe?**
> An `<iframe>` embeds the full PDF viewer with its own scroll position — you cannot control which page is shown or overlay a highlight. `react-pdf` renders a single page onto a `<canvas>`, giving you a DOM element you can absolutely-position a highlight `<div>` over.

---

## Configuration Knobs

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `V2_FUZZY_MATCH_THRESHOLD` | `80` | Minimum rapidfuzz score (0–100) to accept a match. Lower → more false positives. Higher → more missed matches. |
| `V2_CHUNK_MAX_WORDS` | `300` | Max words per chunk. Shorter chunks = smaller search space = faster + more accurate matching. |
| `raw_text context length` | 10–25 words | Longer context = more unique match. Shorter = less chance LLM copies it faithfully. |

---

## Common Failure Modes and How to Handle Them

### 1. `bbox` is `null` — coordinate resolution failed
**Cause**: LLM returned a raw_text that doesn't match any word sequence in the chunk (paraphrased, too short, OCR noise too high).
**UI handling**: Still navigate to the correct page. Show the raw_text as a tooltip. Do not show a highlight rect. This is graceful degradation — the user can see the page and find the field manually.

### 2. LLM returns wrong `chunk_id`
**Cause**: LLM misreads the chunk label, especially if chunk IDs look similar.
**Fix**: Try adjacent chunks (±1, ±2) as fallback before giving up.

### 3. Highlight appears in wrong position
**Cause**: `page_width`/`page_height` mismatch — the percentage maths only works if you use the values from the **same ADI result** that produced the bboxes, not a different rendering's dimensions.
**Fix**: Always store and return `page_width`, `page_height`, and `coordinate_unit` from `page.width`, `page.height`, `page.unit` in the ADI response.

### 4. Highlight is accurate for some docs but off for others
**Cause**: Scanned PDFs where ADI returns pixel-unit coordinates instead of inch. The page dimensions would be e.g. 2550×3300 (300 DPI scan) instead of 8.5×11.
**Fix**: Always pass through `coordinate_unit` (`"inch"` or `"pixel"`) and handle it in the UI or normalise at ingest time. Since we use percentage-based rendering, the actual unit doesn't matter — as long as `bbox` and `page_width`/`page_height` are in the **same unit**, the percentages are correct.

### 5. Multi-page fields (e.g. a table spanning two pages)
**Cause**: The chunk may be assigned to page N but some words are on page N+1.
**Fix**: Use the page number stored in `WordLocation.page_number` (per-word), not the chunk's page number, when computing the bbox. For cross-page spans, either split the match to two bboxes or use only the words on the primary page.

---

## Minimal Implementation Checklist

To implement this in a new project from scratch:

- [ ] **OCR step**: Preserve per-word bbox, per-page width/height/unit
- [ ] **Polygon→bbox**: `[min(x), min(y), max(x), max(y)]` from ADI's 8-point polygon
- [ ] **Chunk IDs**: Deterministic, unique, reproducible — `"{filename}::CHUNK_{n:03d}"`
- [ ] **Word map on chunk**: List of `{word, bbox, page_number}` for every word in the chunk
- [ ] **LLM prompt**: Explicitly instruct to return `raw_text` (verbatim, 10–25 words) and `chunk_id`
- [ ] **Fuzzy match**: Sliding window of ±3 tokens, `rapidfuzz.fuzz.ratio`, threshold ≈ 80
- [ ] **Spanning bbox**: `[min(x1), min(y1), max(x2), max(y2)]` across matched words
- [ ] **Adjacent chunk fallback**: Try ±1, ±2 neighbours in same document
- [ ] **API output**: Send `bbox`, `page_number`, `page_width`, `page_height`, `coordinate_unit`, `blob_url`
- [ ] **Frontend**: `react-pdf` for single-page render, `position: absolute` overlay `<div>` with percentage coordinates derived from bbox/page dimensions
- [ ] **Graceful degradation**: If `bbox` is null, still open PDF at the correct page

---

## What Makes This Architecture Robust

1. **LLM only does text** — coordinates are always computed in code. This removes hallucination from the coordinate path entirely.

2. **Context phrase > value** — The LLM returns 10–25 words of context, not just the 1–3-word value. This makes the fuzzy match unique and tolerant of OCR noise.

3. **Chunk ID narrows the search** — Instead of scanning the entire document (potentially thousands of words), we search only the ~50–300 words in the stated chunk. This is both faster and more accurate.

4. **Percentage CSS** — The highlight works at any container width and zoom level without knowing the canvas pixel size at render time.

5. **Two rendering modes** — Use a native `<iframe>` for browse mode (cheap, full PDF), switch to `react-pdf` only when a highlight is needed (renders one page with full DOM control).
