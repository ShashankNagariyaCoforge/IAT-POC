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
    def extract_urls(text: str) -> List[str]:
        """Extract HTTP/HTTPS URLs from text content."""
        url_pattern = re.compile(
            r'https?://(?:www\.)?'
            r'[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{2,6}'
            r'(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
            re.IGNORECASE
        )
        urls = list(set(url_pattern.findall(text)))
        # Filter out common non-useful URLs
        skip_patterns = [
            'mailto:', 'javascript:', '.png', '.jpg', '.gif', '.svg',
            'fonts.googleapis', 'cdn.', 'analytics.', 'tracking.',
            'facebook.com', 'twitter.com', 'linkedin.com/share',
            'youtube.com', 'instagram.com'
        ]
        filtered = [
            url for url in urls
            if not any(skip in url.lower() for skip in skip_patterns)
        ]
        logger.info(f"[Enrichment] Extracted {len(filtered)} URLs from text (from {len(urls)} total)")
        return filtered[:10]  # Cap at 10 URLs for POC

    @staticmethod
    def extract_company_name(text: str, key_fields: Optional[Dict] = None) -> str:
        """Derive company name from existing key_fields or heuristic extraction."""
        # First try key_fields from classification
        if key_fields:
            name = key_fields.get("name") or ""
            if not name:
                insured = key_fields.get("insured", {})
                if isinstance(insured, dict):
                    name = insured.get("name", "")
            if name and name.lower() not in ["null", "none", "n/a"]:
                return name

        # Heuristic: look for common patterns in text
        patterns = [
            r'(?:insured|applicant|company|business|client)\s*(?:name)?[:\-\s]+([A-Z][A-Za-z\s&.,\'-]+(?:LLC|Inc|Corp|Ltd|LP|LLP)?)',
            r'Re:\s*([A-Z][A-Za-z\s&.,\'-]+(?:LLC|Inc|Corp|Ltd|LP|LLP))',
        ]
        for p in patterns:
            match = re.search(p, text, re.I)
            if match:
                res = match.group(1).split('\n')[0].strip()
                return res

        return ""

    # ─── Web Crawling (Crawl4AI) ────────────────────────────────────────────

    async def crawl_website(self, url: str) -> str:
        """Crawl a website using Crawl4AI and return markdown content."""
        try:
            from crawl4ai import AsyncWebCrawler

            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(url=url)
                if result.success and result.markdown:
                    markdown = result.markdown[:MAX_CONTENT_FOR_AI]
                    logger.info(f"[Enrichment] Crawled {url}: {len(markdown)} chars")
                    return markdown
                else:
                    logger.warning(f"[Enrichment] Crawl4AI returned no content for {url}")
                    return ""
        except ImportError:
            logger.warning("[Enrichment] crawl4ai not installed, falling back to httpx")
            return await self._fallback_crawl(url)
        except Exception as e:
            logger.warning(f"[Enrichment] Crawl4AI failed for {url}: {e}")
            return await self._fallback_crawl(url)

    async def _fallback_crawl(self, url: str) -> str:
        """Fallback crawling with httpx + BeautifulSoup."""
        import httpx
        from bs4 import BeautifulSoup

        try:
            async with httpx.AsyncClient(
                timeout=CRAWL_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "IAT-Insurance-Bot/1.0"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return ""
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                return text[:MAX_CONTENT_FOR_AI]
        except Exception as e:
            logger.warning(f"[Enrichment] Fallback crawl failed for {url}: {e}")
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
            logger.info("[Enrichment] Content too short for extraction, skipping")
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
        """Google search for a specific field, crawl the top result."""
        try:
            from googlesearch import search as google_search

            query = f"{company_name} {field_name.replace('_', ' ')}"
            logger.info(f"[Enrichment] Searching Google: '{query}'")

            # Run synchronous google search in a thread
            urls = await asyncio.to_thread(
                lambda: list(google_search(query, num_results=3))
            )

            if not urls:
                logger.info(f"[Enrichment] No Google results for '{query}'")
                return ""

            # Crawl the top result
            top_url = urls[0]
            logger.info(f"[Enrichment] Crawling top result: {top_url}")
            content = await self.crawl_website(top_url)
            return content

        except ImportError:
            logger.warning("[Enrichment] googlesearch-python not installed, skipping search fallback")
            return ""
        except Exception as e:
            logger.warning(f"[Enrichment] Google search failed for '{company_name} {field_name}': {e}")
            return ""

    # ─── Main Orchestrator ──────────────────────────────────────────────────

    async def run_enrichment(
        self,
        combined_text: str,
        company_name: str = "",
        key_fields: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Main enrichment pipeline:
          1. Extract URLs from combined text
          2. Derive company name
          3. Crawl each URL
          4. AI extract fields
          5. Google search fallback for null fields
          6. Merge and return
        """
        logger.info("[Enrichment] Starting enrichment pipeline")

        # Step 1: Extract company name if not provided
        if not company_name:
            company_name = self.extract_company_name(combined_text, key_fields)
        if not company_name:
            logger.warning("[Enrichment] No company name found, enrichment will be limited")

        # Step 2: Extract URLs from combined text
        urls = self.extract_urls(combined_text)
        if not urls:
            logger.info("[Enrichment] No URLs found in text, trying Google search directly")
            if company_name:
                # Try a broad Google search for the company
                search_content = await self.search_and_crawl(company_name, "company information")
                if search_content:
                    fields = await self.extract_fields_from_content(
                        search_content, company_name, "google_search"
                    )
                    result = self._build_result(fields, company_name, ["google_search"])
                    return result.model_dump()
            # No URLs and no company name — return empty result
            return EnrichmentResult(
                company_name=company_name or None,
                enrichment_status="no_urls_found"
            ).model_dump()

        # Step 3: Crawl URLs and extract fields
        merged_fields: Dict[str, EnrichedField] = {}
        source_urls: List[str] = []

        # Crawl URLs in parallel (limit to first 5)
        crawl_tasks = [self.crawl_website(url) for url in urls[:5]]
        crawled_contents = await asyncio.gather(*crawl_tasks, return_exceptions=True)

        for url, content in zip(urls[:5], crawled_contents):
            if isinstance(content, Exception) or not content:
                continue

            # Extract fields from this crawled content
            fields = await self.extract_fields_from_content(content, company_name, url)
            source_urls.append(url)

            # Merge: only fill fields that are still null or have lower confidence
            for key, field in fields.items():
                existing = merged_fields.get(key)
                if existing is None or (existing.value is None and field.value is not None):
                    merged_fields[key] = field
                elif field.value is not None and field.confidence > (existing.confidence or 0):
                    merged_fields[key] = field

        # Step 4: Identify null fields and try Google search fallback
        null_fields = [
            k for k in EnrichmentResult.field_keys()
            if k not in merged_fields or merged_fields[k].value is None
        ]

        if null_fields and company_name:
            logger.info(f"[Enrichment] {len(null_fields)} null fields, trying Google for top {MAX_SEARCH_FIELDS}")
            for field_name in null_fields[:MAX_SEARCH_FIELDS]:
                search_content = await self.search_and_crawl(company_name, field_name)
                if search_content:
                    search_fields = await self.extract_fields_from_content(
                        search_content, company_name, "google_search"
                    )
                    # Only fill still-null fields
                    for key, field in search_fields.items():
                        existing = merged_fields.get(key)
                        if (existing is None or existing.value is None) and field.value is not None:
                            merged_fields[key] = field
                            source_urls.append("google_search")

        # Step 5: Build final result
        result = self._build_result(merged_fields, company_name, source_urls)
        logger.info(
            f"[Enrichment] Pipeline complete. "
            f"Extracted {sum(1 for k in EnrichmentResult.field_keys() if getattr(result, k) and getattr(result, k).value)} "
            f"fields from {len(source_urls)} sources"
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
