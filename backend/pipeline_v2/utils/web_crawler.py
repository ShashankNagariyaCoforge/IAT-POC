"""
Web Crawler — URL crawling and Google search for enrichment.
"""

import logging
import re
from typing import List

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CRAWL_TIMEOUT = 30
MAX_CONTENT = 12000

_URL_RE = re.compile(
    r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{2,6}'
    r'(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
    re.IGNORECASE,
)
_SKIP = [
    "mailto:", "javascript:", ".png", ".jpg", ".gif", ".svg",
    "fonts.googleapis", "cdn.", "analytics.", "tracking.",
    "facebook.com", "twitter.com", "linkedin.com/share",
    "youtube.com", "instagram.com",
]


def extract_urls(text: str) -> List[str]:
    urls = list(set(_URL_RE.findall(text)))
    return [u for u in urls if not any(s in u.lower() for s in _SKIP)][:10]


async def crawl_url(url: str) -> str:
    """Crawl a URL and return clean text content."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Try Crawl4AI first, fall back to httpx
    try:
        from crawl4ai import AsyncWebCrawler
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
            if result.success and result.markdown:
                return result.markdown[:MAX_CONTENT]
    except Exception:
        pass

    return await _httpx_crawl(url)


async def _httpx_crawl(url: str) -> str:
    try:
        async with httpx.AsyncClient(
            timeout=CRAWL_TIMEOUT,
            follow_redirects=True,
            verify=False,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            if "text/html" not in resp.headers.get("content-type", ""):
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)[:MAX_CONTENT]
    except Exception as e:
        logger.warning(f"[Crawler] Failed to crawl {url}: {e}")
        return ""


async def google_search(query: str, n: int = 5) -> List[str]:
    """
    Return top N URLs for a Google search query.

    Uses Google Custom Search JSON API when V2_GOOGLE_SEARCH_API_KEY +
    V2_GOOGLE_SEARCH_ENGINE_ID are configured (reliable, rate-limited by quota).
    Falls back to the free `googlesearch` library when keys are absent.
    """
    from pipeline_v2.config import v2_settings

    api_key = v2_settings.v2_google_search_api_key
    cx      = v2_settings.v2_google_search_engine_id

    if api_key and cx:
        return await _google_custom_search(query, n, api_key, cx)

    # Free library fallback — no key needed, but rate-limited and fragile
    try:
        import asyncio
        from googlesearch import search as _search
        urls = await asyncio.to_thread(lambda: list(_search(query, num_results=n)))
        return urls
    except Exception as e:
        logger.warning(f"[Crawler] Google search (free) failed for '{query}': {e}")
        return []


async def _google_custom_search(query: str, n: int, api_key: str, cx: str) -> List[str]:
    """Google Custom Search JSON API — returns up to 10 results per call."""
    try:
        params = {
            "key": api_key,
            "cx":  cx,
            "q":   query,
            "num": min(n, 10),  # API max per call is 10
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://www.googleapis.com/customsearch/v1", params=params
            )
            resp.raise_for_status()
            data = resp.json()
        urls = [item["link"] for item in data.get("items", []) if "link" in item]
        logger.debug(f"[Crawler] Custom Search returned {len(urls)} URLs for '{query}'")
        return urls
    except Exception as e:
        logger.warning(f"[Crawler] Google Custom Search failed for '{query}': {e}")
        return []
