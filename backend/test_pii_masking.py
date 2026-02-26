"""
PII Masking Test Script
=======================
Tests the PIIMasker service against the synthetic PDF files WITHOUT
requiring any Azure services (no Cosmos DB, no Blob Storage, no Key Vault).

Usage:
    cd /home/azureuser/Documents/projects/IAT-POC/backend
    python3 test_pii_masking.py

Output:
    - Prints a before/after comparison for each PDF
    - Shows all detected PII entities per document
    - Saves a detailed HTML report to: /tmp/pii_masking_report.html
"""

import asyncio
import base64
import os
import sys
from pathlib import Path

# ── Patch settings BEFORE importing PIIMasker ──────────────────────────────────
# Generate a random 32-byte AES key for local testing (not stored anywhere)
_TEST_KEY = base64.b64encode(os.urandom(32)).decode()
os.environ["PII_ENCRYPTION_KEY"] = _TEST_KEY
os.environ["DEV_BYPASS_AUTH"] = "true"
# ───────────────────────────────────────────────────────────────────────────────

import fitz  # PyMuPDF — already in requirements.txt


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def highlight_pii(original: str, masked: str) -> dict:
    """Compute stats comparing original vs masked text."""
    import re
    placeholders = re.findall(r'\[(?:NAME|EMAIL|PHONE|SSN|DOB|ADDRESS|URL|IP|IBAN|CARD|POLICY_NUMBER|REDACTED)\]', masked)
    return {
        "total_pii_found": len(placeholders),
        "by_type": {p: placeholders.count(p) for p in set(placeholders)},
    }


async def test_pdf(pdf_path: str, masker):
    """Run PII masking on a single PDF and return results."""
    from presidio_analyzer import AnalyzerEngine

    name = Path(pdf_path).name
    print(f"\n{'='*60}")
    print(f"  Processing: {name}")
    print(f"{'='*60}")

    # Extract text
    text = extract_text_from_pdf(pdf_path)
    char_count = len(text)
    print(f"  Extracted {char_count:,} characters from PDF\n")

    if char_count == 0:
        print("  ⚠  No text extracted (might be a scanned/image PDF).")
        return None

    # Show a snippet of original text
    snippet_len = 500
    print(f"  ── Original text (first {snippet_len} chars) ──")
    print(f"  {text[:snippet_len].replace(chr(10), chr(10) + '  ')}")
    print()

    # Run masking
    masked_text, pii_mappings = await masker.mask_text(
        text=text,
        case_id="test-case-001",
        document_id=f"doc-{name}",
    )

    # Show masked snippet
    print(f"  ── Masked text (first {snippet_len} chars) ──")
    print(f"  {masked_text[:snippet_len].replace(chr(10), chr(10) + '  ')}")
    print()

    # Stats
    stats = highlight_pii(text, masked_text)
    print(f"  ── PII Summary ──")
    print(f"  Total PII entities found & masked: {stats['total_pii_found']}")
    for ptype, count in sorted(stats["by_type"].items()):
        print(f"    {ptype:<20} : {count}")

    # Show the actual masked values (what was replaced)
    if pii_mappings:
        print(f"\n  ── Masked Values (showing first 10) ──")
        for m in pii_mappings:
            # Decrypt and store plaintext on the dict for HTML report
            m["original_value"] = masker._decrypt(m["original_value_encrypted"])
        for m in pii_mappings[:10]:
            print(f"    [{m['pii_type']:<20}]  '{m['original_value']}'  →  '{m['masked_value']}'")
        if len(pii_mappings) > 10:
            print(f"    ... and {len(pii_mappings) - 10} more")

    return {
        "pdf": name,
        "chars": char_count,
        "pii_count": len(pii_mappings),
        "by_type": stats["by_type"],
        "original_snippet": text[:snippet_len],
        "masked_snippet": masked_text[:snippet_len],
        "all_mappings": pii_mappings,
    }


def save_html_report(results: list):
    """Save a readable HTML report of all masking results."""
    lines = [
        "<!DOCTYPE html><html><head>",
        "<meta charset='utf-8'>",
        "<title>PII Masking Report</title>",
        "<style>",
        "body{font-family:monospace;background:#1a1a1a;color:#e0e0e0;padding:20px;}",
        "h1{color:#60a5fa;} h2{color:#34d399;border-bottom:1px solid #444;padding-bottom:6px;}",
        ".stat{color:#fbbf24;} .original{background:#2d1515;padding:12px;border-radius:6px;white-space:pre-wrap;margin:8px 0;}",
        ".masked{background:#152d15;padding:12px;border-radius:6px;white-space:pre-wrap;margin:8px 0;}",
        "table{border-collapse:collapse;width:100%;margin:10px 0;}",
        "th{background:#333;padding:6px 12px;text-align:left;}",
        "td{padding:6px 12px;border-bottom:1px solid #333;}",
        ".label{color:#a78bfa;font-weight:bold;}",
        "</style></head><body>",
        "<h1>🔒 PII Masking Test Report</h1>",
    ]
    for r in results:
        if not r:
            continue
        lines.append(f"<h2>📄 {r['pdf']}</h2>")
        lines.append(f"<p>Characters extracted: <span class='stat'>{r['chars']:,}</span> &nbsp;|&nbsp; PII entities found: <span class='stat'>{r['pii_count']}</span></p>")

        # Type breakdown
        if r["by_type"]:
            lines.append("<table><tr><th>PII Type</th><th>Count</th></tr>")
            for ptype, count in sorted(r["by_type"].items()):
                lines.append(f"<tr><td class='label'>{ptype}</td><td>{count}</td></tr>")
            lines.append("</table>")

        lines.append("<b>Original snippet:</b>")
        lines.append(f"<div class='original'>{r['original_snippet']}</div>")
        lines.append("<b>Masked snippet:</b>")
        lines.append(f"<div class='masked'>{r['masked_snippet']}</div>")

        # All mappings table
        if r["all_mappings"]:
            lines.append("<b>All detected PII (first 20):</b>")
            lines.append("<table><tr><th>Type</th><th>Original Value</th><th>Replaced With</th></tr>")
            for m in r["all_mappings"][:20]:
                original = m.get("original_value", m["original_value_encrypted"][:20] + "…")
                lines.append(f"<tr><td class='label'>{m['pii_type']}</td><td>{original}</td><td>{m['masked_value']}</td></tr>")
            lines.append("</table>")

    lines.append("</body></html>")

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    report_path = str(output_dir / "pii_masking_report.html")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\n✅ HTML report saved to: {report_path}")
    return report_path


async def main():
    # Import masker AFTER env patches are set
    from services.pii_masker import PIIMasker

    print("🔑 Using ephemeral test AES-256 key (randomly generated, not stored)")
    print("📦 Initializing Presidio Analyzer & Anonymizer engines...")
    masker = PIIMasker()
    print("✅ PIIMasker initialized successfully.\n")

    # PDFs to test
    pdf_dir = Path(__file__).parent.parent  # IAT-POC root
    pdfs = sorted(pdf_dir.glob("synthetic_*.pdf"))

    if not pdfs:
        print(f"❌ No synthetic_*.pdf files found in: {pdf_dir}")
        sys.exit(1)

    print(f"Found {len(pdfs)} PDF(s) to test:")
    for p in pdfs:
        print(f"  • {p.name}  ({p.stat().st_size / 1024 / 1024:.1f} MB)")

    results = []
    for pdf in pdfs:
        result = await test_pdf(str(pdf), masker)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("  OVERALL SUMMARY")
    print(f"{'='*60}")
    total_pii = sum(r["pii_count"] for r in results if r)
    print(f"  PDFs processed  : {len([r for r in results if r])}")
    print(f"  Total PII found : {total_pii}")

    save_html_report(results)


if __name__ == "__main__":
    asyncio.run(main())
