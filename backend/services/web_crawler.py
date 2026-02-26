"""
Web crawler service (Step 9).
Extracts text content from URLs found in documents.
Uses Playwright for JS-rendered pages, BeautifulSoup for static pages.
Only triggered when URLs are detected in document text.
"""

import asyncio
import logging
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15  # seconds per URL
MAX_CONTENT_LENGTH = 50_000  # max chars to extract per URL


class WebCrawler:
    """Crawls URLs found in documents to extract readable text content."""

    async def crawl_urls(self, urls: List[str]) -> Dict[str, str]:
        """
        Crawl a list of URLs and return extracted text per URL.

        Args:
            urls: List of URLs to crawl.

        Returns:
            Dict mapping URL → extracted text (empty string if failed).
        """
        results = {}
        for url in urls:
            try:
                text = await self._crawl_single(url)
                results[url] = text
                logger.info(f"Crawled URL: {url} ({len(text)} chars)")
            except Exception as e:
                logger.warning(f"Failed to crawl URL {url}: {e}")
                results[url] = ""
        return results

    async def _crawl_single(self, url: str) -> str:
        """
        Crawl a single URL. First tries a simple HTTP GET with BeautifulSoup.
        Falls back to Playwright for JS-rendered pages.

        Args:
            url: The URL to crawl.

        Returns:
            Extracted text content.
        """
        # First attempt: simple HTTP GET (covers most static pages)
        try:
            text = await self._fetch_static(url)
            if text and len(text) > 200:
                return text[:MAX_CONTENT_LENGTH]
        except Exception as e:
            logger.debug(f"Static fetch failed for {url}: {e}. Trying Playwright.")

        # Fallback: Playwright for JS-heavy pages
        try:
            text = await self._fetch_with_playwright(url)
            return text[:MAX_CONTENT_LENGTH]
        except Exception as e:
            logger.warning(f"Playwright fetch also failed for {url}: {e}")
            raise

    async def _fetch_static(self, url: str) -> str:
        """Fetch a page with httpx and parse with BeautifulSoup."""
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "IAT-Insurance-Bot/1.0"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return ""
            soup = BeautifulSoup(resp.text, "lxml")
            # Remove script and style elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)

    async def _fetch_with_playwright(self, url: str) -> str:
        """Fetch a JS-rendered page using headless Playwright."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=REQUEST_TIMEOUT * 1000, wait_until="networkidle")
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)
            finally:
                await browser.close()
