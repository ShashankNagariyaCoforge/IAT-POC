"""
Enrichment Service — Web crawling + AI extraction for insurance entity data.

Flow:
  1. Extract URLs + company name from combined text
  2. Crawl websites with Crawl4AI → markdown
  3. Azure OpenAI → extract structured fields with confidence
  4. For null fields → Google Search → crawl top result → re-extract
  5. Merge results → return EnrichmentResult
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Any

from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models.enrichment import EnrichedField, EnrichmentResult

logger = logging.getLogger(__name__)

# ─── Prompts ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
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

FIELDS_PROMPT = """
Extract the following fields for this company from the content below.
Return a JSON object where each key maps to an object with "value" and "confidence".

Fields to extract:
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

Company: {company_name}

Content:
{content}

Respond ONLY with valid JSON in this exact format:
{{
  "entity_type": {{"value": "...", "confidence": 0.95}},
  "naics_code": {{"value": "...", "confidence": 0.8}},
  "entity_structure": {{"value": null, "confidence": 0.0}},
  ... (all fields listed above)
}}
"""

# Maximum content length sent to OpenAI
MAX_CONTENT_FOR_AI = 12000
# Maximum number of null fields to search via Google
MAX_SEARCH_FIELDS = 3
# Request timeout for crawling
CRAWL_TIMEOUT = 30


class EnrichmentService:
    """Orchestrates web-crawling enrichment for insurance entity data."""

    def __init__(self):
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_deployment

    # ─── URL Extraction ─────────────────────────────────────────────────────

    @staticmethod
    def clean_url(url: str) -> str:
        """Strip trailing punctuation and normalise a URL to its homepage root.

        Handles:
        - Trailing punctuation left by email body text: . , ) > " ' ] >
        - Extra paths/params from AI-returned websites (e.g. /about?ref=x)
          → kept as-is so deep pages are still crawlable when extracted from text,
          but AI-provided homepage URLs are normalised to scheme+domain only
          (call with homepage=True for that behaviour).
        """
        # Strip common trailing punctuation that email parsers leave attached
        url = url.rstrip('.,)>"\']')
        return url

    @staticmethod
    def normalise_to_homepage(url: str) -> str:
        """Reduce a URL to just its scheme + domain (strip path, query, fragment)."""
        from urllib.parse import urlparse
        try:
            p = urlparse(url)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}"
        except Exception:
            pass
        return url

    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """Extract HTTP/HTTPS URLs from text content."""
        url_pattern = re.compile(
            r'https?://(?:www\.)?'
            r'[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{2,6}'
            r'(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
            re.IGNORECASE
        )
        raw_urls = list(set(url_pattern.findall(text)))
        # Strip trailing punctuation left by email body formatting
        raw_urls = [EnrichmentService.clean_url(u) for u in raw_urls]
        # Decode any Proofpoint URL Defense wrapped URLs
        raw_urls = [EnrichmentService.decode_proofpoint_url(u) for u in raw_urls]
        # Filter out common non-useful URLs
        skip_patterns = [
            'mailto:', 'javascript:', '.png', '.jpg', '.gif', '.svg',
            'fonts.googleapis', 'cdn.', 'analytics.', 'tracking.',
            'facebook.com', 'twitter.com', 'linkedin.com/share',
            'youtube.com', 'instagram.com', 'urldefense.com',
        ]
        filtered = [
            url for url in raw_urls
            if not any(skip in url.lower() for skip in skip_patterns)
        ]
        return filtered[:10]

    async def identify_entity(self, text: str) -> Dict[str, Any]:
        """Use AI to identify company name, website, and any enrichment fields from text."""
        prompt = f"""
        Identify the primary insurance applicant (Company/Business Name), their website,
        and any of the following fields found DIRECTLY in the text below. 
        Fields: {", ".join(EnrichmentResult.field_keys())}

        Return ONLY valid JSON in this format: 
        {{
            "company_name": "...", 
            "website": "...", 
            "extracted_fields": {{ "field_name": {{ "value": "...", "confidence": 0.9 }}, ... }}
        }}
        If not found, use null.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a business data extraction assistant."},
                    {"role": "user", "content": f"{prompt}\n\nContent:\n{text[:6000]}"}
                ],
                temperature=0.0,
                max_tokens=600,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            logger.info(f"[Enrichment] AI Entity Identification: {data.get('company_name')} (Found {len(data.get('extracted_fields', {}))} fields in text)")
            return data
        except Exception as e:
            logger.warning(f"[Enrichment] AI Entity Identification failed: {e}")
            return {"company_name": None, "website": None, "extracted_fields": {}}

    @staticmethod
    def extract_company_name(text: str, key_fields: Optional[Dict] = None) -> str:
        """Fallback/Legacy company name extraction from key_fields."""
        if key_fields:
            name = key_fields.get("name") or ""
            if not name:
                insured = key_fields.get("insured", {})
                if isinstance(insured, dict):
                    name = insured.get("name", "")
            if name and str(name).lower() not in ["null", "none", "n/a", ""]:
                return str(name)
        return ""

    # ─── Proofpoint URL Defense Decoder ─────────────────────────────────────

    @staticmethod
    def decode_proofpoint_url(url: str) -> str:
        """Decode a Proofpoint URL Defense wrapped URL to get the real URL.

        Handles formats:
          v3: https://urldefense.com/v3/__https://real.url/__
          v2: https://urldefense.proofpoint.com/v2/url?u=...
        """
        if "urldefense.com/v3/__" in url:
            # Extract everything between the first __ and the trailing __
            match = re.search(r'urldefense\.com/v3/__(.+?)(?:__|\Z)', url)
            if match:
                real = match.group(1)
                # Proofpoint v3 encodes : as -3A and / chars — undo common encodings
                real = real.replace("-3A", ":").replace("-2F", "/").replace("-2E", ".")
                if not real.startswith(("http://", "https://")):
                    real = "https://" + real
                return real
        elif "urldefense.proofpoint.com/v2/url" in url:
            match = re.search(r'[?&]u=([^&]+)', url)
            if match:
                from urllib.parse import unquote
                real = unquote(match.group(1)).replace("-", ".").replace("_", "/")
                if not real.startswith(("http://", "https://")):
                    real = "https://" + real
                return real
        return url

    # Domains that always block scrapers — skip them entirely
    _BLOCKED_DOMAINS = {
        "linkedin.com", "zoominfo.com", "bloomberg.com",
        "glassdoor.com", "facebook.com", "instagram.com",
    }

    # ─── Web Crawling ────────────────────────────────────────────────────────

    async def crawl_website(self, url: str) -> str:
        """Crawl a website — uses httpx on Windows (Crawl4AI/Playwright can't spawn
        subprocesses there), Crawl4AI on other platforms with httpx fallback."""
        import sys
        if not url:
            return ""

        # Decode Proofpoint URL Defense wrapping before crawling
        url = self.decode_proofpoint_url(url)

        # Ensure URL has protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Skip domains that always block scrapers
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lstrip("www.")
        if any(blocked in domain for blocked in self._BLOCKED_DOMAINS):
            logger.info(f"[Enrichment] Skipping blocked domain: {domain}")
            return ""

        # On Windows, Crawl4AI's Playwright cannot spawn subprocesses — go straight to httpx
        if sys.platform == "win32":
            return await self._fallback_crawl(url)

        try:
            from crawl4ai import AsyncWebCrawler
            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await asyncio.wait_for(crawler.arun(url=url), timeout=CRAWL_TIMEOUT)
                if result.success and result.markdown:
                    markdown = result.markdown[:MAX_CONTENT_FOR_AI]
                    logger.info(f"[Enrichment] Crawl4AI crawled {url}: {len(markdown)} chars")
                    return markdown
                else:
                    logger.warning(f"[Enrichment] Crawl4AI returned no content for {url}, trying httpx fallback")
                    return await self._fallback_crawl(url)
        except asyncio.TimeoutError:
            logger.warning(f"[Enrichment] Crawl4AI timed out after {CRAWL_TIMEOUT}s for {url}, falling back to httpx")
            return await self._fallback_crawl(url)
        except ImportError:
            return await self._fallback_crawl(url)
        except Exception as e:
            logger.warning(f"[Enrichment] Crawl4AI failed for {url}: {e!r}, falling back to httpx")
            return await self._fallback_crawl(url)

    async def _fallback_crawl(self, url: str) -> str:
        """Crawl with httpx + BeautifulSoup (no browser required)."""
        import httpx
        from bs4 import BeautifulSoup

        try:
            async with httpx.AsyncClient(
                timeout=CRAWL_TIMEOUT,
                follow_redirects=True,
                verify=False,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.google.com/",
                },
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return ""
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                logger.info(f"[Enrichment] httpx crawled {url}: {len(text)} chars")
                return text[:MAX_CONTENT_FOR_AI]
        except Exception as e:
            logger.warning(f"[Enrichment] httpx crawl failed for {url}: {e}")
            return ""

    # ─── AI Field Extraction ────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def extract_fields_from_content(
        self,
        content: str,
        company_name: str,
        source_url: str = "",
    ) -> Dict[str, EnrichedField]:
        """Use Azure OpenAI to extract structured fields from crawled content."""
        if not content or len(content.strip()) < 50:
            logger.info(f"[Enrichment] Content too short for extraction (len: {len(content or '')})")
            return {}

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": FIELDS_PROMPT.format(
                        company_name=company_name,
                        content=content[:MAX_CONTENT_FOR_AI]
                    )}
                ],
                temperature=0.1,
                max_tokens=1500,
            )

            raw = response.choices[0].message.content
            data = json.loads(raw)

            # Convert to EnrichedField objects
            fields: Dict[str, EnrichedField] = {}
            for key in EnrichmentResult.field_keys():
                field_data = data.get(key, {})
                if isinstance(field_data, dict):
                    value = field_data.get("value")
                    confidence = float(field_data.get("confidence", 0.0))
                    if value and str(value).lower() not in ["null", "none", "n/a", ""]:
                        fields[key] = EnrichedField(
                            value=str(value),
                            confidence=min(confidence, 1.0),
                            source=source_url
                        )

            logger.info(
                f"[Enrichment] Extracted {len(fields)} fields from content "
                f"(company: {company_name}, source: {source_url})"
            )
            return fields

        except json.JSONDecodeError as e:
            logger.error(f"[Enrichment] AI returned invalid JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"[Enrichment] AI extraction failed: {e}", exc_info=True)
            raise

    # ─── Google Search Fallback ─────────────────────────────────────────────

    async def search_and_crawl(self, company_name: str, field_name: str) -> str:
        """DuckDuckGo search for a specific field, crawl the top results."""
        try:
            from ddgs import DDGS

            if field_name == "company information":
                query = f'"{company_name}" company business profile USA'
            else:
                # Quote company name to force exact match and reduce wrong-company results
                query = f'"{company_name}" {field_name.replace("_", " ")} USA'

            logger.info(f"[Enrichment] DuckDuckGo search: '{query}'")

            def _search():
                with DDGS() as ddgs:
                    return [r["href"] for r in ddgs.text(query, max_results=5) if r.get("href")]

            urls = await asyncio.to_thread(_search)

            if not urls:
                logger.info(f"[Enrichment] No search results for '{query}'")
                return ""

            logger.info(f"[Enrichment] Search returned {len(urls)} results. Crawling top 2 for '{field_name}'")

            # Crawl top 2 in parallel
            crawl_tasks = [self.crawl_website(u) for u in urls[:2]]
            results = await asyncio.gather(*crawl_tasks)
            contents = [
                f"--- Source: {u} ---\n{c}"
                for u, c in zip(urls[:2], results) if c
            ]
            return "\n\n".join(contents)

        except Exception as e:
            logger.warning(f"[Enrichment] Search failed for '{company_name} {field_name}': {e}")
            return ""

    # ─── Main Orchestrator ──────────────────────────────────────────────────

    async def run_enrichment(
        self,
        combined_text: str,
        company_name: Optional[str] = None,
        key_fields: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Main enrichment pipeline.
        """
        logger.info(f"[Enrichment] Starting pipeline (text length: {len(combined_text)})")

        # Step 1: Identify entity using AI (and extract any fields directly from text)
        entity_info = await self.identify_entity(combined_text)
        
        # Use AI name if provided, else fallback to key_fields/provided name
        if not company_name:
            company_name = entity_info.get("company_name")
        if not company_name:
            company_name = self.extract_company_name(combined_text, key_fields)
        
        logger.info(f"[Enrichment] Pipeline company name: '{company_name}'")

        # Initialize merged_fields with what AI found directly in text
        # source=None means "found in submission documents/emails" (not a web URL)
        merged_fields: Dict[str, EnrichedField] = {}
        ai_extracted = entity_info.get("extracted_fields", {})
        for field_name, info in ai_extracted.items():
            if field_name in EnrichmentResult.field_keys() and info and info.get("value"):
                merged_fields[field_name] = EnrichedField(
                    value=str(info["value"]),
                    confidence=float(info.get("confidence", 0.7)),
                    source=None,  # No URL — sourced from submission documents/emails
                )

        # Step 2: Identify URLs
        urls = self.extract_urls(combined_text)
        ai_site = entity_info.get("website")
        if ai_site:
            ai_site = self.clean_url(ai_site)
            if not ai_site.startswith(("http://", "https://")):
                ai_site = f"https://{ai_site}"
            # Normalise AI-returned site to homepage root (strip /path?params the LLM may add)
            ai_site = self.normalise_to_homepage(ai_site)
            if ai_site not in urls:
                urls.insert(0, ai_site)  # Prioritize AI identified website

        if not company_name and not urls:
            logger.warning("[Enrichment] No company name or URLs found. Enrichment aborted.")
            return EnrichmentResult(enrichment_status="no_data_found").model_dump()

        # Step 3: Crawl URLs and extract fields
        source_urls = []  # Only real web URLs go here

        # 3a. Crawl URLs in parallel (limit to first 3)
        if urls:
            crawl_tasks = [self.crawl_website(url) for url in urls[:3]]
            crawled_contents = await asyncio.gather(*crawl_tasks, return_exceptions=True)

            # 3b. Extract fields from all crawled contents in parallel (Optimization)
            extraction_tasks = []
            valid_source_urls = []
            
            for url, content in zip(urls[:3], crawled_contents):
                if isinstance(content, Exception) or not content:
                    continue
                extraction_tasks.append(self.extract_fields_from_content(content, company_name, url))
                valid_source_urls.append(url)
            
            if extraction_tasks:
                logger.info(f"[Enrichment] Launching {len(extraction_tasks)} parallel extractions from crawled content.")
                results = await asyncio.gather(*extraction_tasks)
                
                for url, fields in zip(valid_source_urls, results):
                    if fields:
                        source_urls.append(url)
                        # Merge: replace only if higher confidence
                        for key, field in fields.items():
                            existing = merged_fields.get(key)
                            if existing is None or (field.value and field.confidence > existing.confidence):
                                merged_fields[key] = field

        # Step 4: Identify null fields and try Google search fallback
        null_fields = [
            k for k in EnrichmentResult.field_keys()
            if k not in merged_fields or merged_fields[k].value is None
        ]

        if null_fields and company_name:
            logger.info(f"[Enrichment] {len(null_fields)} null fields, running parallel search for top 3")
            # Run all 3 searches in parallel instead of sequentially
            search_tasks = [self.search_and_crawl(company_name, fn) for fn in null_fields[:3]]
            search_contents = await asyncio.gather(*search_tasks)

            extract_tasks = [
                self.extract_fields_from_content(sc, company_name, "web_search")
                for sc in search_contents if sc
            ]
            if extract_tasks:
                extract_results = await asyncio.gather(*extract_tasks)
                for search_fields in extract_results:
                    if search_fields:
                        source_urls.append("web_search")
                        for key, field in search_fields.items():
                            existing = merged_fields.get(key)
                            if (existing is None or existing.value is None) and field.value:
                                merged_fields[key] = field

        # Final fallback: Broad search if still very empty
        if len(merged_fields) < 3 and company_name:
            logger.info(f"[Enrichment] Still mostly empty. Final broad search for '{company_name}'")
            search_content = await self.search_and_crawl(company_name, "company information")
            if search_content:
                search_fields = await self.extract_fields_from_content(search_content, company_name, "google_search")
                if search_fields:
                    source_urls.append("google_search")
                    for k, v in search_fields.items():
                        if k not in merged_fields or v.confidence > merged_fields[k].confidence:
                            merged_fields[k] = v

        # Step 5: Build final result
        result = self._build_result(merged_fields, company_name, source_urls)
        logger.info(
            f"[Enrichment] Pipeline complete. "
            f"Extracted {len(merged_fields)} fields from {len(set(source_urls))} sources"
        )
        return result.model_dump()

    def _build_result(
        self,
        fields: Dict[str, EnrichedField],
        company_name: str,
        source_urls: List[str],
    ) -> EnrichmentResult:
        """Build an EnrichmentResult from extracted fields."""
        result_data: Dict[str, Any] = {
            "company_name": company_name or None,
            "source_urls": list(set(source_urls)),
            "enrichment_status": "completed",
        }
        for key in EnrichmentResult.field_keys():
            result_data[key] = fields.get(key)

        return EnrichmentResult(**result_data)
