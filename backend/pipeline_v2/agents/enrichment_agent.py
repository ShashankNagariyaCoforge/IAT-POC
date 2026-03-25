"""
Enrichment Agent V2
Mirrors enrichment_service.py logic exactly, adapted for V2 pipeline.

Flow (matches V1):
  1. identify_entity() — scan email text for company name, website, directly extractable fields
  2. Crawl discovered URLs in PARALLEL (up to 3)
  3. Extract fields from all crawled content in PARALLEL
  4. Merge by highest confidence (not first-found)
  5. Google search fallback for still-null fields (up to MAX_SEARCH_FIELDS)
  6. Final broad "company information" search if still mostly empty
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional

from pipeline_v2.config import v2_settings
from pipeline_v2.models import EnrichmentFieldResult, MergedField
from pipeline_v2.utils import web_crawler
from pipeline_v2.utils.llm_client import call_llm

logger = logging.getLogger(__name__)

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

# Maximum content sent to LLM per extraction call (matches V1)
MAX_CONTENT_FOR_AI = 12000
# Maximum null fields to try Google search for (matches V1)
MAX_SEARCH_FIELDS = 3

# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """
You are a business data extraction assistant specializing in insurance and
corporate entity data. Extract fields precisely. Return ONLY valid JSON.
If a field cannot be found, return null for its value and 0.0 for its confidence.
Never guess — only extract what is explicitly stated or can be strongly inferred.

For each field, provide:
- "value": the extracted value (string or null)
- "confidence": a float 0.0–1.0 indicating certainty
  - 0.9+ = explicitly and clearly stated in the content
  - 0.6–0.89 = strongly inferred from context
  - 0.3–0.59 = weakly inferred or partially available
  - 0.0 = not found at all
"""

# Field descriptions mirror V1's FIELDS_PROMPT exactly
_FIELDS_DESCRIPTION = """
- entity_type (e.g. LLC, Corporation, Partnership, Sole Proprietor)
- naics_code (6-digit industry code, derive from business type if not explicit)
- entity_structure (organizational hierarchy description)
- years_in_business (or founding year)
- number_of_employees (total headcount)
- territory_code (state/region codes they operate in)
- limit_of_liability
- deductible
- class_mass_action_deductible_retention
- pending_or_prior_litigation_date
- duty_to_defend_limit
- defense_outside_limit
- employment_category
- ec_number_of_employees
- employee_compensation
- number_of_employees_in_each_band
- employee_location (list of office locations as comma-separated string)
- number_of_employees_in_each_location
- business_description (what the company does)
- primary_rating_state (primary US state of operations)
"""

_FIELDS_PROMPT_TEMPLATE = """\
Extract the following fields for this company from the content below.
Return a JSON object where each key maps to an object with "value" and "confidence".

Fields to extract:
{fields_description}

Company: {company_name}

Content:
{content}

Respond ONLY with valid JSON where every listed field appears as a key.
"""

_IDENTIFY_PROMPT = """\
Identify the primary insurance applicant (Company/Business Name) and their website URL.
Also extract any of the following fields found DIRECTLY in the text below.
Fields: entity_type, naics_code, years_in_business, number_of_employees, territory_code,
        employee_location, business_description, primary_rating_state, entity_structure,
        limit_of_liability, deductible, employment_category, employee_compensation

Return ONLY valid JSON:
{{
    "company_name": "...",
    "website": "...",
    "extracted_fields": {{
        "field_name": {{"value": "...", "confidence": 0.9}},
        ...
    }}
}}
If not found, use null.
"""


def _load_prompt() -> str:
    path = os.path.join(_PROMPTS_DIR, "enrichment_agent.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return _SYSTEM_PROMPT.strip()


_PROMPT: Optional[str] = None


def _get_system_prompt() -> str:
    global _PROMPT
    if _PROMPT is None:
        _PROMPT = _load_prompt()
    return _PROMPT


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _identify_entity(email_body: str, case_id: str = "") -> dict:
    """
    Step 1 (mirrors V1 identify_entity): scan email text for company name,
    website, and any fields directly extractable from the text.
    """
    try:
        result = await call_llm(
            system_prompt="You are a business data extraction assistant. Return ONLY valid JSON.",
            user_message=f"{_IDENTIFY_PROMPT}\n\nContent:\n{email_body[:6000]}",
            stage_name="enrichment_identify_entity",
            model="small",
            json_mode=True,
            max_tokens=600,
            case_id=case_id,
        )
        logger.info(
            f"[EnrichmentAgent] identify_entity: company='{result.get('company_name')}' "
            f"website='{result.get('website')}' "
            f"direct_fields={len(result.get('extracted_fields', {}))}"
        )
        return result
    except Exception as e:
        logger.warning(f"[EnrichmentAgent] identify_entity failed: {e}")
        return {"company_name": None, "website": None, "extracted_fields": {}}


async def _extract_from_content(
    content: str,
    field_names: List[str],
    company_name: str,
    source_url: str,
    case_id: str = "",
) -> Dict[str, EnrichmentFieldResult]:
    """
    Extract specific fields from crawled page content.
    Returns {field_name: EnrichmentFieldResult} for fields that were found.
    Mirrors V1's extract_fields_from_content().
    """
    if not content or len(content.strip()) < 50:
        return {}

    # Build a fields description scoped to what we need
    all_known = _FIELDS_DESCRIPTION
    fields_json = json.dumps(field_names)

    user_msg = _FIELDS_PROMPT_TEMPLATE.format(
        fields_description=all_known,
        company_name=company_name or "Unknown",
        content=content[:MAX_CONTENT_FOR_AI],
    ) + f"\nOnly return these field names: {fields_json}"

    # Two attempts (mirrors V1 tenacity retry)
    for attempt in range(2):
        try:
            result = await call_llm(
                system_prompt=_get_system_prompt(),
                user_message=user_msg,
                stage_name="enrichment_extract",
                model="small",
                json_mode=True,
                max_tokens=1500,
                case_id=case_id,
            )
            break
        except Exception as e:
            if attempt == 1:
                logger.warning(f"[EnrichmentAgent] Extract failed for {source_url} after 2 attempts: {e}")
                return {}
            await asyncio.sleep(2)

    found: Dict[str, EnrichmentFieldResult] = {}
    for field_name in field_names:
        raw = result.get(field_name, {})
        if not isinstance(raw, dict):
            continue
        value = raw.get("value")
        if value and str(value).lower() not in ("null", "none", "n/a", ""):
            confidence = float(raw.get("confidence", 0.6))
            found[field_name] = EnrichmentFieldResult(
                field_name=field_name,
                value=str(value).strip(),
                source_url=source_url,
                raw_text=f"{value}",
                confidence=min(confidence, 1.0),
                steps_taken=[f"extracted from {source_url}"],
            )

    logger.info(
        f"[EnrichmentAgent] Extracted {len(found)}/{len(field_names)} fields "
        f"from {source_url}"
    )
    return found


def _merge_higher_confidence(
    current: Dict[str, EnrichmentFieldResult],
    new_results: Dict[str, EnrichmentFieldResult],
) -> Dict[str, EnrichmentFieldResult]:
    """Merge new_results into current, keeping highest-confidence value per field."""
    merged = dict(current)
    for field_name, new in new_results.items():
        existing = merged.get(field_name)
        if existing is None or (new.value and new.confidence > existing.confidence):
            merged[field_name] = new
    return merged


# ── Main Agent ────────────────────────────────────────────────────────────────

class EnrichmentAgent:
    def __init__(self, case_id: str = ""):
        self._case_id = case_id

    async def enrich(
        self,
        fields_to_enrich: List[MergedField],
        email_body: str,
    ) -> List[EnrichmentFieldResult]:
        """
        Enrich missing fields using web sources.
        Mirrors V1 run_enrichment() logic exactly.
        Returns list of EnrichmentFieldResult for fields that were found.
        """
        field_names = [f.field_name for f in fields_to_enrich]
        if not field_names:
            return []

        # ── Step 1: identify_entity — extract company name, website, direct fields ──
        entity_info = await _identify_entity(email_body, self._case_id)
        company_name: str = entity_info.get("company_name") or ""

        # Seed merged_fields with anything extractable directly from the email text
        merged: Dict[str, EnrichmentFieldResult] = {}
        for fn, info in (entity_info.get("extracted_fields") or {}).items():
            if fn in field_names and isinstance(info, dict) and info.get("value"):
                merged[fn] = EnrichmentFieldResult(
                    field_name=fn,
                    value=str(info["value"]),
                    source_url="source_text",
                    raw_text=str(info["value"]),
                    confidence=float(info.get("confidence", 0.7)),
                    steps_taken=["extracted directly from email body"],
                )

        # ── Step 2: Collect URLs — AI-identified website + URLs in email body ────
        urls_in_email = web_crawler.extract_urls(email_body)
        ai_website = entity_info.get("website")
        if ai_website:
            if not ai_website.startswith(("http://", "https://")):
                ai_website = f"https://{ai_website}"
            if ai_website not in urls_in_email:
                urls_in_email.insert(0, ai_website)  # AI-identified site first

        # Also include fixed regulatory sites from config
        all_urls = urls_in_email[:3] + v2_settings.enrichment_fixed_sites_list

        def _remaining() -> List[str]:
            return [fn for fn in field_names if fn not in merged]

        # ── Step 3: Crawl all URLs in PARALLEL, then extract in PARALLEL ─────────
        if all_urls and _remaining():
            crawl_tasks = [web_crawler.crawl_url(url) for url in all_urls[:3]]
            crawled = await asyncio.gather(*crawl_tasks, return_exceptions=True)

            extract_tasks = []
            valid_urls = []
            for url, content in zip(all_urls[:3], crawled):
                if isinstance(content, Exception) or not content:
                    continue
                extract_tasks.append(
                    _extract_from_content(content, _remaining(), company_name, url, self._case_id)
                )
                valid_urls.append(url)

            if extract_tasks:
                logger.info(
                    f"[EnrichmentAgent] Launching {len(extract_tasks)} parallel extractions"
                )
                extraction_results = await asyncio.gather(*extract_tasks, return_exceptions=True)
                for url, result in zip(valid_urls, extraction_results):
                    if not isinstance(result, Exception):
                        merged = _merge_higher_confidence(merged, result)

        # ── Step 4: Google search fallback for still-null fields ──────────────────
        still_null = _remaining()
        if still_null and company_name:
            logger.info(
                f"[EnrichmentAgent] {len(still_null)} fields still missing — trying Google search"
            )
            for field_name in still_null[:MAX_SEARCH_FIELDS]:
                if field_name in merged:
                    continue
                query = f"{company_name} {field_name.replace('_', ' ')} insurance"
                search_urls = await web_crawler.google_search(query, n=3)

                contents = []
                for search_url in search_urls[:2]:
                    content = await web_crawler.crawl_url(search_url)
                    if content:
                        contents.append(f"--- Source: {search_url} ---\n{content}")

                if contents:
                    combined = "\n\n".join(contents)
                    result = await _extract_from_content(
                        combined, [field_name], company_name,
                        "google_search", self._case_id
                    )
                    if result:
                        for r in result.values():
                            r.steps_taken.insert(0, f"google_search: {query}")
                        merged = _merge_higher_confidence(merged, result)

        # ── Step 5: Final broad fallback if still very empty (mirrors V1) ─────────
        if len(merged) < 3 and company_name:
            logger.info(
                f"[EnrichmentAgent] Still < 3 fields found — broad 'company information' search"
            )
            broad_query = f"{company_name} business overview"
            broad_urls = await web_crawler.google_search(broad_query, n=3)
            contents = []
            for url in broad_urls[:2]:
                content = await web_crawler.crawl_url(url)
                if content:
                    contents.append(f"--- Source: {url} ---\n{content}")
            if contents:
                combined = "\n\n".join(contents)
                result = await _extract_from_content(
                    combined, _remaining(), company_name,
                    "google_search_broad", self._case_id
                )
                merged = _merge_higher_confidence(merged, result)

        found_count = len(merged)
        logger.info(
            f"[EnrichmentAgent] Complete: {found_count}/{len(field_names)} fields enriched "
            f"company='{company_name}'"
        )
        return list(merged.values())
