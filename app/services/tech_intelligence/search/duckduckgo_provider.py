import html
import logging
import re
from typing import List, Optional
from urllib.parse import parse_qs, unquote, urlparse
import httpx

from app.services.tech_intelligence.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

class DuckDuckGoSearchProvider(BaseSearchProvider):
    """
    Production-grade DuckDuckGo web search provider.
    Zero external keys or subscription required. Returns live web search results.
    """

    @property
    def name(self) -> str:
        return "duckduckgo"

    async def is_available(self) -> bool:
        return True

    async def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: Optional[str] = None,
    ) -> List[SearchResult]:
        results: List[SearchResult] = []
        clean_q = query.strip()
        if not clean_q:
            return results

        # Time parameter for DuckDuckGo (d: past day, w: past week, m: past month)
        df_param = ""
        if time_range == "today":
            df_param = "d"
        elif time_range == "this_week":
            df_param = "w"
        elif time_range == "this_month":
            df_param = "m"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # Query DuckDuckGo HTML endpoint
        url = "https://html.duckduckgo.com/html/"
        data = {"q": clean_q}
        if df_param:
            data["df"] = df_param

        try:
            async with httpx.AsyncClient(headers=headers, timeout=4.0, follow_redirects=True) as client:
                resp = await client.post(url, data=data)
                if resp.status_code == 200:
                    results = self._parse_html(resp.text, max_results)
                else:
                    logger.warning(f"DuckDuckGo search responded with status {resp.status_code}")
        except Exception as e:
            logger.warning(f"DuckDuckGo search connection error: {e}")

        # Fallback to DuckDuckGo Lite if primary endpoint was blocked or empty
        if not results:
            try:
                lite_url = f"https://lite.duckduckgo.com/lite/"
                async with httpx.AsyncClient(headers=headers, timeout=3.0, follow_redirects=True) as client:
                    resp = await client.post(lite_url, data={"q": clean_q})
                    if resp.status_code == 200:
                        results = self._parse_lite_html(resp.text, max_results)
            except Exception as e:
                logger.warning(f"DuckDuckGo Lite fallback error: {e}")

        return results[:max_results]

    def _parse_html(self, html_content: str, max_results: int) -> List[SearchResult]:
        results: List[SearchResult] = []
        # Pattern for standard DuckDuckGo HTML result items
        # Matches: <a class="result__url" href="..."> or <a class="result__snippet" ...>
        # Result blocks are usually separated by class="result results_links"
        result_blocks = re.split(r'class="result\s+results_links', html_content)
        
        for block in result_blocks[1:]:
            if len(results) >= max_results:
                break

            # Extract Title & Link
            link_match = re.search(r'<a\s+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not link_match:
                continue

            raw_url = link_match.group(1)
            raw_title = link_match.group(2)

            # DuckDuckGo redirects through /l/?uddg=...
            actual_url = self._extract_actual_url(raw_url)
            if not actual_url or "duckduckgo.com" in actual_url:
                continue

            title = self._clean_text(raw_title)

            # Extract Snippet
            snippet = ""
            snippet_match = re.search(r'<a\s+class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
            if snippet_match:
                snippet = self._clean_text(snippet_match.group(1))

            if title and actual_url:
                results.append(
                    SearchResult(
                        title=title,
                        url=actual_url,
                        snippet=snippet,
                    )
                )

        return results

    def _parse_lite_html(self, html_content: str, max_results: int) -> List[SearchResult]:
        results: List[SearchResult] = []
        # Lite table layout has class="result-link" and class="result-snippet"
        matches = re.findall(
            r'<a\s+class=["\']result-link["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>.*?'
            r'<td\s+class=["\']result-snippet["\'][^>]*>(.*?)</td>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )
        for raw_url, raw_title, raw_snippet in matches:
            if len(results) >= max_results:
                break
            actual_url = self._extract_actual_url(raw_url)
            if not actual_url or "duckduckgo.com" in actual_url:
                continue
            title = self._clean_text(raw_title)
            snippet = self._clean_text(raw_snippet)
            if title and actual_url:
                results.append(
                    SearchResult(
                        title=title,
                        url=actual_url,
                        snippet=snippet,
                    )
                )
        return results

    def _extract_actual_url(self, raw_url: str) -> str:
        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url
        if "duckduckgo.com/l/?" in raw_url:
            parsed = urlparse(raw_url)
            qs = parse_qs(parsed.query)
            if "uddg" in qs and qs["uddg"]:
                return unquote(qs["uddg"][0])
        return unquote(raw_url)

    def _clean_text(self, text: str) -> str:
        # Strip HTML tags
        no_tags = re.sub(r"<[^>]+>", " ", text)
        # Unescape HTML entities
        unescaped = html.unescape(no_tags)
        # Collapse extra spaces
        return re.sub(r"\s+", " ", unescaped).strip()
