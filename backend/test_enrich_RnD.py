"""
Enrichment R&D Script
=====================
Standalone script to test and compare each layer of web enrichment independently.

Usage:
    python3 test_enrich_RnD.py --url "https://example.com" --company "Acme Corp"
    python3 test_enrich_RnD.py --search "Acme Corp" --company "Acme Corp"
    python3 test_enrich_RnD.py --url "https://example.com" --search "Acme Corp" --company "Acme Corp"
    python3 test_enrich_RnD.py --url "https://example.com"   # company name auto-detected

Layers tested:
    Layer 1 — Crawl4AI (headless browser, best for JS-heavy sites)
    Layer 2 — httpx + BeautifulSoup (lightweight, fast)
    Layer 3 — DuckDuckGo search → crawl top 5 results (both Layer1 + Layer2 per result)

Each layer prints:
    - Raw crawled text (first 2000 chars)
    - Extracted fields with confidence scores
    - Side-by-side comparison at the end
"""

import asyncio
import json
import re
import sys
import argparse
import textwrap
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# ─── Load .env so Azure OpenAI settings are available ─────────────────────────
from dotenv import load_dotenv
load_dotenv()

from openai import AsyncAzureOpenAI
from config import settings

# ─── Constants: all 18 enrichable fields ──────────────────────────────────────

ENRICHABLE_FIELDS: Dict[str, str] = {
    "entity_type": (
        "Legal entity type (e.g. LLC, Corporation, Partnership, Sole Proprietor, Non-Profit). "
        "Look for 'Inc.', 'LLC', 'Corp.' in the business name or explicit statements."
    ),
    "naics_code": (
        "6-digit NAICS industry code. Must be exactly 6 digits — do NOT guess from description. "
        "Only extract if explicitly stated."
    ),
    "entity_structure": (
        "Organizational hierarchy description "
        "(e.g. 'wholly owned subsidiary of X', 'standalone entity', 'parent company with 3 subsidiaries')."
    ),
    "years_in_business": (
        "How long the business has been operating, or its founding year "
        "(e.g. '15 years', 'founded in 2008', 'established 1995')."
    ),
    "number_of_employees": (
        "Total employee headcount "
        "(e.g. '45 full-time employees', 'approximately 120 FTEs', '200+ staff')."
    ),
    "territory_code": (
        "US state or region codes where the business operates "
        "(e.g. 'TX, CA, FL', 'nationwide', 'Mid-Atlantic states')."
    ),
    "limit_of_liability": (
        "Maximum liability coverage limit requested or currently in force "
        "(e.g. '$1,000,000 per occurrence / $2,000,000 aggregate')."
    ),
    "deductible": (
        "Deductible or self-insured retention amount "
        "(e.g. '$10,000 per claim', '$25,000 per occurrence retention')."
    ),
    "class_mass_action_deductible_retention": (
        "Class action or mass action deductible / retention "
        "(e.g. '$500,000 class action retention', 'CMAR: $250K')."
    ),
    "pending_or_prior_litigation_date": (
        "Date of any pending or prior litigation or claim "
        "(e.g. 'prior litigation resolved 2019', 'pending suit filed March 2023')."
    ),
    "duty_to_defend_limit": (
        "Duty-to-defend sublimit, if separate from the main policy limit "
        "(e.g. '$250,000 duty to defend sublimit')."
    ),
    "defense_outside_limit": (
        "Whether defense costs are outside (in addition to) the policy limit. "
        "Extract as Yes/No or the exact clause language (e.g. 'DCOL', 'defense costs in addition to limit')."
    ),
    "employment_category": (
        "Type or category of employees "
        "(e.g. 'W-2 employees only', 'mix of W-2 and 1099 contractors', 'professional staff')."
    ),
    "ec_number_of_employees": (
        "Employee count specific to the Employment Compensation (EC) coverage category."
    ),
    "employee_compensation": (
        "Total compensation/payroll amount for employees "
        "(e.g. '$2,500,000 annual payroll', '$1.8M total compensation')."
    ),
    "number_of_employees_in_each_band": (
        "Employee distribution across compensation bands "
        "(e.g. '10 employees < $100K, 5 employees > $100K')."
    ),
    "employee_location": (
        "Office or work locations for employees "
        "(e.g. 'Dallas TX, Austin TX, Phoenix AZ')."
    ),
    "number_of_employees_in_each_location": (
        "Employee count per location "
        "(e.g. 'Dallas: 30, Austin: 15, Phoenix: 8')."
    ),
}

# ─── LLM settings ─────────────────────────────────────────────────────────────

MAX_CONTENT_FOR_LLM = 12000   # chars sent to OpenAI per extraction call
CRAWL_TIMEOUT       = 30      # seconds per crawl request
SEARCH_RESULTS      = 5       # top N DuckDuckGo results to crawl

# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a business data extraction assistant specialising in insurance and corporate entity data.
Extract fields precisely from the content provided.
Return ONLY valid JSON — no markdown, no extra text.

For each field, provide:
  "value"      : the extracted value (string) or null if not found
  "confidence" : float 0.0–1.0
    0.9+  = explicitly and clearly stated
    0.6–0.89 = strongly inferred from context
    0.3–0.59 = weakly inferred or ambiguous
    0.0   = not found at all (use null for value)

Never guess. Only extract what is explicitly stated or can be strongly inferred."""

def build_extraction_prompt(company_name: str, content: str) -> str:
    field_lines = "\n".join(
        f"- {key}: {desc}"
        for key, desc in ENRICHABLE_FIELDS.items()
    )
    json_template = json.dumps(
        {key: {"value": "...", "confidence": 0.0} for key in ENRICHABLE_FIELDS},
        indent=2
    )
    return f"""Extract the following fields for the company: {company_name or "(unknown)"}

FIELDS TO EXTRACT:
{field_lines}

CONTENT:
{content[:MAX_CONTENT_FOR_LLM]}

Respond ONLY with valid JSON exactly matching this structure (all {len(ENRICHABLE_FIELDS)} keys must be present):
{json_template}"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _print_header(title: str, char: str = "═", width: int = 80) -> None:
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def _print_subheader(title: str) -> None:
    print(f"\n  ── {title} {'─' * max(0, 60 - len(title))}")


def _truncate(text: str, n: int = 2000) -> str:
    if len(text) <= n:
        return text
    return text[:n] + f"\n  ... [{len(text) - n} more chars truncated]"


def _decode_proofpoint(url: str) -> str:
    if "urldefense.com/v3/__" in url:
        m = re.search(r'urldefense\.com/v3/__(.+?)(?:__|\Z)', url)
        if m:
            real = m.group(1).replace("-3A", ":").replace("-2F", "/").replace("-2E", ".")
            return real if real.startswith("http") else "https://" + real
    elif "urldefense.proofpoint.com/v2/url" in url:
        m = re.search(r'[?&]u=([^&]+)', url)
        if m:
            from urllib.parse import unquote
            real = unquote(m.group(1)).replace("-", ".").replace("_", "/")
            return real if real.startswith("http") else "https://" + real
    return url


_BLOCKED_DOMAINS = {
    "linkedin.com", "zoominfo.com", "bloomberg.com",
    "glassdoor.com", "facebook.com", "instagram.com",
}


def _is_blocked(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lstrip("www.")
        return any(b in domain for b in _BLOCKED_DOMAINS)
    except Exception:
        return False


# ─── LLM extraction ───────────────────────────────────────────────────────────

async def extract_fields_with_llm(
    content: str,
    company_name: str,
    source_label: str,
    client: AsyncAzureOpenAI,
    deployment: str,
) -> Dict[str, Any]:
    """Call OpenAI to extract enrichable fields from crawled content."""
    if not content or len(content.strip()) < 80:
        print(f"    [LLM] Skipping — content too short ({len(content)} chars)")
        return {}

    print(f"    [LLM] Calling OpenAI on {len(content)} chars of content from: {source_label}")
    try:
        response = await client.chat.completions.create(
            model=deployment,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_extraction_prompt(company_name, content)},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        found = {k: v for k, v in data.items() if isinstance(v, dict) and v.get("value")}
        print(f"    [LLM] Extracted {len(found)}/{len(ENRICHABLE_FIELDS)} fields with values.")
        return data
    except json.JSONDecodeError as e:
        print(f"    [LLM] JSON parse error: {e}")
        return {}
    except Exception as e:
        print(f"    [LLM] API call failed: {e}")
        return {}


# ─── Layer 1: Crawl4AI ────────────────────────────────────────────────────────

async def layer1_crawl4ai(url: str) -> str:
    """Crawl a URL using Crawl4AI (headless browser, handles JS-heavy sites)."""
    print(f"    [Crawl4AI] Crawling: {url}")
    try:
        from crawl4ai import AsyncWebCrawler
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await asyncio.wait_for(crawler.arun(url=url), timeout=CRAWL_TIMEOUT)
            if result.success and result.markdown:
                text = result.markdown[:MAX_CONTENT_FOR_LLM]
                print(f"    [Crawl4AI] ✓ Got {len(text)} chars (markdown)")
                return text
            else:
                print(f"    [Crawl4AI] ✗ No content returned (success={result.success})")
                return ""
    except asyncio.TimeoutError:
        print(f"    [Crawl4AI] ✗ Timed out after {CRAWL_TIMEOUT}s")
        return ""
    except ImportError:
        print("    [Crawl4AI] ✗ Not installed (pip install crawl4ai)")
        return ""
    except Exception as e:
        print(f"    [Crawl4AI] ✗ Error: {e!r}")
        return ""


# ─── Layer 2: httpx + BeautifulSoup ──────────────────────────────────────────

async def layer2_httpx(url: str) -> str:
    """Crawl a URL using httpx + BeautifulSoup (no browser required)."""
    import httpx
    from bs4 import BeautifulSoup

    print(f"    [httpx] Crawling: {url}")
    try:
        async with httpx.AsyncClient(
            timeout=CRAWL_TIMEOUT,
            follow_redirects=True,
            verify=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "text/html" not in ctype and "text/plain" not in ctype:
                print(f"    [httpx] ✗ Non-HTML content-type: {ctype}")
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)[:MAX_CONTENT_FOR_LLM]
            print(f"    [httpx] ✓ Got {len(text)} chars (plain text)")
            return text
    except Exception as e:
        print(f"    [httpx] ✗ Error: {e}")
        return ""


# ─── Layer 3: DuckDuckGo search + crawl top N ────────────────────────────────

async def layer3_search_and_crawl(
    company_name: str,
    query_suffix: str = "company business profile insurance",
    max_results: int = SEARCH_RESULTS,
) -> List[Dict[str, Any]]:
    """DuckDuckGo search for company, return list of {url, crawl4ai_text, httpx_text}."""
    from ddgs import DDGS

    query = f'"{company_name}" {query_suffix}'
    print(f"    [DuckDuckGo] Query: {query!r}")

    def _search():
        with DDGS() as ddgs:
            return [r for r in ddgs.text(query, max_results=max_results) if r.get("href")]

    try:
        raw_results = await asyncio.to_thread(_search)
    except Exception as e:
        print(f"    [DuckDuckGo] ✗ Search failed: {e}")
        return []

    if not raw_results:
        print("    [DuckDuckGo] ✗ No results returned")
        return []

    print(f"    [DuckDuckGo] ✓ Found {len(raw_results)} results:")
    for i, r in enumerate(raw_results, 1):
        print(f"        {i}. {r.get('href')}  —  {r.get('title', '')[:60]}")

    # Crawl each result with both methods in parallel
    async def _crawl_one(result: dict) -> Dict[str, Any]:
        url = _decode_proofpoint(result["href"])
        if _is_blocked(url):
            print(f"      [Skip] Blocked domain: {urlparse(url).netloc}")
            return {"url": url, "crawl4ai": "", "httpx": ""}
        c4ai, hx = await asyncio.gather(layer1_crawl4ai(url), layer2_httpx(url))
        return {"url": url, "title": result.get("title", ""), "crawl4ai": c4ai, "httpx": hx}

    print(f"\n    [DuckDuckGo] Crawling top {len(raw_results)} results in parallel...")
    crawl_tasks = [_crawl_one(r) for r in raw_results]
    return await asyncio.gather(*crawl_tasks)


# ─── Pretty-print a field result dict ────────────────────────────────────────

def print_field_results(results: Dict[str, Any], label: str) -> None:
    _print_subheader(f"Extraction results — {label}")
    if not results:
        print("    (no results)")
        return
    for key in ENRICHABLE_FIELDS:
        field = results.get(key, {})
        if not isinstance(field, dict):
            continue
        value = field.get("value")
        conf  = field.get("confidence", 0.0)
        if value:
            bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            print(f"    {key:<45}  {bar}  {conf:.2f}  →  {str(value)[:80]}")
        else:
            print(f"    {key:<45}  {'░' * 10}  0.00  →  (not found)")


def print_comparison_table(all_results: Dict[str, Dict[str, Any]]) -> None:
    """Print a comparison table of all layers for fields that at least one layer found."""
    _print_header("COMPARISON TABLE — fields found by at least one layer", "═")
    sources = list(all_results.keys())
    col_w = 22

    # Header row
    header = f"  {'Field':<40}" + "".join(f"  {s:<{col_w}}" for s in sources)
    print(header)
    print("  " + "─" * (40 + len(sources) * (col_w + 2)))

    for key in ENRICHABLE_FIELDS:
        row_values = {
            src: all_results[src].get(key, {}) for src in sources
        }
        # Only print if at least one source found a value
        any_found = any(
            isinstance(v, dict) and v.get("value")
            for v in row_values.values()
        )
        if not any_found:
            continue

        row = f"  {key:<40}"
        for src in sources:
            field = row_values[src]
            if isinstance(field, dict) and field.get("value"):
                val = str(field["value"])[:18]
                conf = field.get("confidence", 0.0)
                cell = f"{val} ({conf:.2f})"
            else:
                cell = "—"
            row += f"  {cell:<{col_w}}"
        print(row)

    print()


# ─── Main R&D runner ──────────────────────────────────────────────────────────

async def run_rnd(
    url: Optional[str],
    company_name: Optional[str],
    search_query: Optional[str],
    run_layer1: bool = True,
    run_layer2: bool = True,
    run_layer3: bool = True,
) -> None:

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )
    deployment = settings.azure_openai_deployment

    all_extraction_results: Dict[str, Dict[str, Any]] = {}

    # ── If a URL is provided: test Layer 1 and Layer 2 on it ──────────────────
    if url:
        url = _decode_proofpoint(url.strip())
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        _print_header(f"TARGET URL:  {url}")

        # Layer 1 — Crawl4AI
        if run_layer1:
            _print_header("LAYER 1 — Crawl4AI (headless browser)", "─")
            c4ai_text = await layer1_crawl4ai(url)

            _print_subheader("Raw crawled content (first 2000 chars)")
            if c4ai_text:
                print(textwrap.indent(_truncate(c4ai_text, 2000), "    "))
            else:
                print("    (empty — crawl failed)")

            if c4ai_text and company_name:
                c4ai_extraction = await extract_fields_with_llm(
                    c4ai_text, company_name, "Crawl4AI", client, deployment
                )
                all_extraction_results["Layer1_Crawl4AI"] = c4ai_extraction
                print_field_results(c4ai_extraction, "Layer 1 — Crawl4AI")

        # Layer 2 — httpx
        if run_layer2:
            _print_header("LAYER 2 — httpx + BeautifulSoup", "─")
            httpx_text = await layer2_httpx(url)

            _print_subheader("Raw crawled content (first 2000 chars)")
            if httpx_text:
                print(textwrap.indent(_truncate(httpx_text, 2000), "    "))
            else:
                print("    (empty — crawl failed)")

            if httpx_text and company_name:
                httpx_extraction = await extract_fields_with_llm(
                    httpx_text, company_name, "httpx", client, deployment
                )
                all_extraction_results["Layer2_httpx"] = httpx_extraction
                print_field_results(httpx_extraction, "Layer 2 — httpx")

    # ── Layer 3 — DuckDuckGo search ────────────────────────────────────────────
    if run_layer3 and company_name:
        q_suffix = search_query or "company business profile insurance employees"
        _print_header(f"LAYER 3 — DuckDuckGo Search + Crawl Top {SEARCH_RESULTS}", "─")
        _print_subheader(f"Search company: {company_name!r}  |  suffix: {q_suffix!r}")

        search_results = await layer3_search_and_crawl(company_name, q_suffix, SEARCH_RESULTS)

        # Accumulate content from all crawled pages
        all_crawl4ai_text = ""
        all_httpx_text    = ""

        for i, res in enumerate(search_results, 1):
            _print_subheader(f"Search result #{i}: {res['url']}")
            print(f"    Title : {res.get('title', '—')}")

            if res.get("crawl4ai"):
                print(f"    Crawl4AI: {len(res['crawl4ai'])} chars")
                print("    --- first 500 chars ---")
                print(textwrap.indent(_truncate(res["crawl4ai"], 500), "    "))
                all_crawl4ai_text += f"\n\n--- Source: {res['url']} ---\n{res['crawl4ai']}"
            else:
                print("    Crawl4AI: (empty)")

            if res.get("httpx"):
                print(f"    httpx   : {len(res['httpx'])} chars")
                print("    --- first 500 chars ---")
                print(textwrap.indent(_truncate(res["httpx"], 500), "    "))
                all_httpx_text += f"\n\n--- Source: {res['url']} ---\n{res['httpx']}"
            else:
                print("    httpx   : (empty)")

        # Extract from combined crawl4ai search content
        if all_crawl4ai_text:
            _print_subheader("Extracting from combined Crawl4AI search content")
            search_c4ai_extraction = await extract_fields_with_llm(
                all_crawl4ai_text, company_name, "Search+Crawl4AI", client, deployment
            )
            all_extraction_results["Layer3_Search_Crawl4AI"] = search_c4ai_extraction
            print_field_results(search_c4ai_extraction, "Layer 3 — Search + Crawl4AI")

        # Extract from combined httpx search content
        if all_httpx_text:
            _print_subheader("Extracting from combined httpx search content")
            search_httpx_extraction = await extract_fields_with_llm(
                all_httpx_text, company_name, "Search+httpx", client, deployment
            )
            all_extraction_results["Layer3_Search_httpx"] = search_httpx_extraction
            print_field_results(search_httpx_extraction, "Layer 3 — Search + httpx")

    # ── Final comparison table ─────────────────────────────────────────────────
    if len(all_extraction_results) > 1:
        print_comparison_table(all_extraction_results)
    elif len(all_extraction_results) == 1:
        _print_header("FINAL RESULTS", "═")
        label, data = next(iter(all_extraction_results.items()))
        print_field_results(data, label)

    # ── Summary ────────────────────────────────────────────────────────────────
    _print_header("SUMMARY", "═")
    for label, data in all_extraction_results.items():
        found = [k for k, v in data.items() if isinstance(v, dict) and v.get("value")]
        high_conf = [k for k in found if data[k].get("confidence", 0) >= 0.75]
        print(f"  {label:<35}  {len(found):>2} fields found  |  {len(high_conf):>2} with confidence ≥ 0.75")

    print()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrichment R&D: test Crawl4AI / httpx / DuckDuckGo extraction layers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          # Test a specific URL (both Layer 1 and Layer 2):
          python3 test_enrich_RnD.py --url "https://acme.com" --company "Acme Corp"

          # Only run DuckDuckGo search layer:
          python3 test_enrich_RnD.py --company "Acme Corp" --no-l1 --no-l2

          # Test URL + also search:
          python3 test_enrich_RnD.py --url "https://acme.com" --company "Acme Corp" --search "number of employees"

          # Skip Crawl4AI (faster):
          python3 test_enrich_RnD.py --url "https://acme.com" --company "Acme Corp" --no-l1
        """),
    )
    parser.add_argument("--url",     help="URL to crawl directly (Layers 1 & 2)")
    parser.add_argument("--company", help="Company name for extraction prompt and DuckDuckGo search")
    parser.add_argument("--search",  help="Extra search query suffix for DuckDuckGo (default: 'company business profile insurance employees')")
    parser.add_argument("--no-l1",   action="store_true", help="Skip Layer 1 (Crawl4AI)")
    parser.add_argument("--no-l2",   action="store_true", help="Skip Layer 2 (httpx)")
    parser.add_argument("--no-l3",   action="store_true", help="Skip Layer 3 (DuckDuckGo search)")

    args = parser.parse_args()

    if not args.url and not args.company:
        parser.error("Provide at least --url or --company (or both)")

    print("\n" + "═" * 80)
    print("  IAT ENRICHMENT R&D SCRIPT")
    print("═" * 80)
    print(f"  URL     : {args.url or '(not provided — skipping Layers 1 & 2)'}")
    print(f"  Company : {args.company or '(not provided — LLM extraction will have no company context)'}")
    print(f"  Search  : {args.search or '(default suffix)'}")
    print(f"  Layers  : {'1' if not args.no_l1 else ''}{'2' if not args.no_l2 else ''}{'3' if not args.no_l3 else ''} active")
    print(f"  Fields  : {len(ENRICHABLE_FIELDS)} enrichable fields defined")
    print("═" * 80)

    asyncio.run(run_rnd(
        url=args.url,
        company_name=args.company,
        search_query=args.search,
        run_layer1=not args.no_l1,
        run_layer2=not args.no_l2,
        run_layer3=not args.no_l3,
    ))
