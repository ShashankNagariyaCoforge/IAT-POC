import os
from pathlib import Path

def generate_case_pii_report(case_id: str, original_text: str, masked_text: str, pii_mappings: list) -> str:
    """
    Generates an HTML report of PII masking for a specific case and saves it
    to frontend/public/reports/{case_id}.html
    """
    # Compute stats
    pii_count = len(pii_mappings)
    by_type = {}
    for m in pii_mappings:
        t = m.get("pii_type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1

    lines = [
        "<!DOCTYPE html><html><head>",
        "<meta charset='utf-8'>",
        f"<title>PII Masking Report - {case_id}</title>",
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
        f"<h1>🔒 Case {case_id} - PII Masking Report</h1>",
        f"<p>Characters analyzed: <span class='stat'>{len(original_text):,}</span> &nbsp;|&nbsp; PII entities found: <span class='stat'>{pii_count}</span></p>"
    ]

    # Type breakdown
    if by_type:
        lines.append("<table><tr><th>PII Type</th><th>Count</th></tr>")
        for ptype, count in sorted(by_type.items()):
            lines.append(f"<tr><td class='label'>{ptype}</td><td>{count}</td></tr>")
        lines.append("</table>")

    lines.append("<b>Original text:</b>")
    lines.append(f"<div class='original'>{original_text}</div>")
    lines.append("<b>Masked text:</b>")
    lines.append(f"<div class='masked'>{masked_text}</div>")

    # Mappings table
    if pii_mappings:
        lines.append("<b>Detected PII:</b>")
        lines.append("<table><tr><th>Type</th><th>Original Value</th><th>Replaced With</th></tr>")
        for m in pii_mappings:
            original = m.get("original_value", m.get("original_value_encrypted", "")[:20] + "…")
            lines.append(f"<tr><td class='label'>{m.get('pii_type')}</td><td>{original}</td><td>{m.get('masked_value')}</td></tr>")
        lines.append("</table>")

    lines.append("</body></html>")

    output_dir = Path(__file__).parent.parent.parent / "frontend" / "public" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{case_id}.html"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    return f"/reports/{case_id}.html"
