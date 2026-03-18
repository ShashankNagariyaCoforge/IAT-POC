# main.py
"""
Batch pipeline:
- Scans pdfs/ for all .pdf files
- Scans docs/ for all .docx files (converts to PDF first)
- Scans pngs/ for all .png, .jpg, .jpeg files
- For each document:
    analyze (Azure DI) -> map to schema (Azure OpenAI) ->
    draw overlays for mapped fields only (if DI ran on a PDF or image)
- Saves per-file outputs in output/<sanitized_name>/:
    - <sanitized_name>.json
    - <sanitized_name>_annotated.pdf  (PDFs, DOCX-converted PDFs, PNG/JPG/JPEG)
    - <sanitized_name>_annotated.<ext>  (for PNG/JPG/JPEG inputs)
"""

import os
import glob
import traceback
import sys
import argparse

# Ensure project root on sys.path (optional safety if running from elsewhere)
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# NOTE: Make sure src/__init__.py exists (even empty)
from src.doc_intel import analyze_with_bboxes
from src.llm_mapper import map_entities_with_schema
from src.utils import (
    load_schema, save_json, rasterize_pdf_pages, rasterize_image,
    collect_mapped_polygons, draw_field_overlays_cv2,
    save_images_as_single_pdf, save_annotated_png,  # still used for PNG default
    sanitize_filename, ensure_dir,
    convert_docx_to_pdf, extract_text_from_docx
)

# Extra import to write annotated JPG/JPEG with same extension
import cv2

DEFAULT_SCHEMA_PATH = os.path.join("schemas", "submission_packet.json")
DEFAULT_PDFS_DIR = "pdfs"
DEFAULT_DOCS_DIR = "docs"
DEFAULT_PNGS_DIR = "pngs"  # holds PNG/JPG/JPEG images
DEFAULT_OUTPUT_ROOT = "output"


# -----------------------------
# Per-format processing helpers
# -----------------------------

def process_single_pdf(pdf_path: str, schema: dict, output_root: str = DEFAULT_OUTPUT_ROOT) -> dict:
    """
    Full pipeline for a PDF: DI -> LLM -> mapped-only overlays -> JSON + annotated PDF.
    """
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    safe_base = sanitize_filename(base_name)
    out_dir = os.path.join(output_root, safe_base)
    ensure_dir(out_dir)

    try:
        print(f"\n=== Processing PDF: {pdf_path} ===")
        print("➡️ Analyze with Azure Document Intelligence...")
        pages = analyze_with_bboxes(pdf_path)
        if not pages:
            raise RuntimeError("No pages analyzed (empty result).")

        full_text = pages[0].get("full_document_content") or "\n".join(
            p.get("content", "") for p in pages
        )

        print("➡️ Map entities with Azure OpenAI (GPT‑4.1)...")
        mapped = map_entities_with_schema(full_text, schema)

        json_path = os.path.join(out_dir, f"{safe_base}.json")
        save_json(mapped, json_path)
        print(f"✅ Mapped JSON saved: {json_path}")

        print("➡️ Collect polygons for MAPPED fields only...")
        overlays_per_page = collect_mapped_polygons(pages, mapped)

        print("➡️ Render overlays and save combined PDF...")
        images = rasterize_pdf_pages(pdf_path, dpi=200)

        overlaid = []
        for i, img in enumerate(images):
            page_data = pages[i] if i < len(pages) else {"width": None, "height": None}
            page_overlays = overlays_per_page[i] if i < len(overlays_per_page) else []
            overlaid_img = draw_field_overlays_cv2(img, page_data, page_overlays)
            overlaid.append(overlaid_img)

        annotated_pdf_path = os.path.join(out_dir, f"{safe_base}_annotated.pdf")
        save_images_as_single_pdf(overlaid, out_pdf=annotated_pdf_path)
        print(f"✅ Annotated PDF saved: {annotated_pdf_path}")

        return {
            "input": pdf_path,
            "output_json": json_path,
            "output_pdf": annotated_pdf_path,
            "output_img": None,
            "status": "ok",
            "error": None
        }

    except Exception as e:
        print(f"❌ Error processing PDF {pdf_path}: {e}")
        traceback.print_exc()
        return {
            "input": pdf_path,
            "output_json": None,
            "output_pdf": None,
            "output_img": None,
            "status": "error",
            "error": str(e)
        }


def process_single_docx(docx_path: str, schema: dict, output_root: str = DEFAULT_OUTPUT_ROOT) -> dict:
    """
    DOCX pipeline:
      - Try to convert to PDF (preferred) and reuse PDF pipeline (overlays)
      - If conversion fails, do text-only mapping (JSON) and skip overlays
    """
    base_name = os.path.splitext(os.path.basename(docx_path))[0]
    safe_base = sanitize_filename(base_name)
    out_dir = os.path.join(output_root, safe_base)
    ensure_dir(out_dir)

    try:
        print(f"\n=== Processing DOCX: {docx_path} ===")
        converted_pdf = os.path.join(out_dir, f"{safe_base}_converted.pdf")

        print("➡️ Converting DOCX to PDF...")
        converted = convert_docx_to_pdf(docx_path, converted_pdf)

        if converted:
            print(f"✅ Converted to: {converted_pdf}")
            return process_single_pdf(converted_pdf, schema, output_root=output_root)

        # Fallback: text-only mapping (no overlays)
        print("⚠️ Conversion failed. Falling back to text-only mapping (no overlays).")
        text = extract_text_from_docx(docx_path)
        mapped = map_entities_with_schema(text, schema)
        json_path = os.path.join(out_dir, f"{safe_base}.json")
        save_json(mapped, json_path)
        print(f"✅ Mapped JSON saved: {json_path}")
        print("⚠️ Overlays skipped because DI needs PDF/image coordinates.")
        return {
            "input": docx_path,
            "output_json": json_path,
            "output_pdf": None,
            "output_img": None,
            "status": "ok",
            "error": None
        }

    except Exception as e:
        print(f"❌ Error processing DOCX {docx_path}: {e}")
        traceback.print_exc()
        return {
            "input": docx_path,
            "output_json": None,
            "output_pdf": None,
            "output_img": None,
            "status": "error",
            "error": str(e)
        }


def process_single_image(image_path: str, schema: dict, output_root: str = DEFAULT_OUTPUT_ROOT) -> dict:
    """
    Generic image pipeline for PNG/JPG/JPEG:
      - DI directly on the image
      - LLM mapping
      - Mapped-only overlays -> annotated image (same extension) + PDF (single page)
    """
    base_name, ext = os.path.splitext(os.path.basename(image_path))
    safe_base = sanitize_filename(base_name)
    out_dir = os.path.join(output_root, safe_base)
    ensure_dir(out_dir)
    ext_lower = ext.lower().lstrip(".")  # 'png' | 'jpg' | 'jpeg' etc.

    try:
        print(f"\n=== Processing IMAGE: {image_path} ===")
        print("➡️ Analyze with Azure Document Intelligence...")
        pages = analyze_with_bboxes(image_path)
        if not pages:
            raise RuntimeError("No pages analyzed (empty result).")
        if len(pages) != 1:
            # DI usually returns one 'page' for an image; warn but proceed
            print(f"ℹ️ DI returned {len(pages)} pages for image; proceeding with all.")

        full_text = pages[0].get("full_document_content") or "\n".join(
            p.get("content", "") for p in pages
        )

        print("➡️ Map entities with Azure OpenAI (GPT‑4.1)...")
        mapped = map_entities_with_schema(full_text, schema)

        json_path = os.path.join(out_dir, f"{safe_base}.json")
        save_json(mapped, json_path)
        print(f"✅ Mapped JSON saved: {json_path}")

        print("➡️ Collect polygons for MAPPED fields only...")
        overlays_per_page = collect_mapped_polygons(pages, mapped)

        print("➡️ Render overlays on the image and save outputs...")
        img_bgr = rasterize_image(image_path)
        # Treat image as single page
        page_data = pages[0]
        page_overlays = overlays_per_page[0] if overlays_per_page else []
        overlaid = draw_field_overlays_cv2(img_bgr, page_data, page_overlays)

        # Save annotated image with SAME extension as input
        annotated_img_path = os.path.join(out_dir, f"{safe_base}_annotated.{ext_lower}")
        # Use cv2.imwrite directly to retain extension flexibility
        ok = cv2.imwrite(annotated_img_path, overlaid)
        if not ok:
            # Fallback to PNG writer from utils
            annotated_img_path = os.path.join(out_dir, f"{safe_base}_annotated.png")
            save_annotated_png(overlaid, annotated_img_path)
        print(f"✅ Annotated image saved: {annotated_img_path}")

        # Also save as single-page PDF
        annotated_pdf_path = os.path.join(out_dir, f"{safe_base}_annotated.pdf")
        save_images_as_single_pdf([overlaid], out_pdf=annotated_pdf_path)
        print(f"✅ Annotated PDF saved: {annotated_pdf_path}")

        return {
            "input": image_path,
            "output_json": json_path,
            "output_pdf": annotated_pdf_path,
            "output_img": annotated_img_path,
            "status": "ok",
            "error": None
        }

    except Exception as e:
        print(f"❌ Error processing IMAGE {image_path}: {e}")
        traceback.print_exc()
        return {
            "input": image_path,
            "output_json": None,
            "output_pdf": None,
            "output_img": None,
            "status": "error",
            "error": str(e)
        }


# -----------------------------
# Batch runner
# -----------------------------

def run_batch(
    pdfs_dir: str,
    docs_dir: str,
    imgs_dir: str,
    schema_path: str,
    output_root: str
):
    # Load schema once
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema not found at: {schema_path}")
    schema = load_schema(schema_path)

    # Collect inputs
    pdf_paths  = sorted(glob.glob(os.path.join(pdfs_dir, "*.pdf")))
    docx_paths = sorted(glob.glob(os.path.join(docs_dir, "*.docx")))

    # Images in imgs_dir: PNG, JPG, JPEG (case-insensitive handling by including upper-case too)
    img_patterns = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
    img_paths = []
    for pat in img_patterns:
        img_paths.extend(glob.glob(os.path.join(imgs_dir, pat)))
    img_paths = sorted(set(img_paths))  # de-duplicate

    if not pdf_paths and not docx_paths and not img_paths:
        print(f"No PDFs in: {pdfs_dir}, no DOCX in: {docs_dir}, and no images in: {imgs_dir}")
        return []

    print(
        f"Found {len(pdf_paths)} PDF(s), {len(docx_paths)} DOCX file(s), and {len(img_paths)} image file(s) "
        f"(png/jpg/jpeg). Starting batch..."
    )
    results = []

    for pdf in pdf_paths:
        res = process_single_pdf(pdf, schema, output_root=output_root)
        results.append(res)

    for docx in docx_paths:
        res = process_single_docx(docx, schema, output_root=output_root)
        results.append(res)

    for img in img_paths:
        res = process_single_image(img, schema, output_root=output_root)
        results.append(res)

    # Summary
    print("\n=== Batch Summary ===")
    ok = [r for r in results if r["status"] == "ok"]
    err = [r for r in results if r["status"] == "error"]
    print(f"Total: {len(results)} | Success: {len(ok)} | Failed: {len(err)}")
    if ok:
        print("\nSuccessful outputs:")
        for r in ok:
            print(f"- {r['input']}")
            print(f"  JSON: {r['output_json']}")
            print(f"  PDF : {r['output_pdf']}")
            if r.get("output_img"):
                print(f"  IMG : {r['output_img']}")
    if err:
        print("\nFailed:")
        for r in err:
            print(f"- {r['input']} -> {r['error']}")

    return results


# -----------------------------
# CLI entrypoint
# -----------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Batch DI + LLM mapping with mapped-only overlays (PDF/DOCX/PNG/JPG/JPEG).")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA_PATH, help="Path to JSON schema file.")
    parser.add_argument("--pdfs",   default=DEFAULT_PDFS_DIR,   help="Folder containing PDF files.")
    parser.add_argument("--docs",   default=DEFAULT_DOCS_DIR,   help="Folder containing DOCX files.")
    parser.add_argument("--imgs",   default=DEFAULT_PNGS_DIR,   help="Folder containing image files (PNG/JPG/JPEG).")
    parser.add_argument("--out",    default=DEFAULT_OUTPUT_ROOT, help="Output root folder.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_batch(
        pdfs_dir=args.pdfs,
        docs_dir=args.docs,
        imgs_dir=args.imgs,
        schema_path=args.schema,
        output_root=args.out
    )
