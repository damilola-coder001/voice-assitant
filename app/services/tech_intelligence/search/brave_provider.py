import logging
import os
from typing import List, Optional
import httpx

from app.services.tech_intelligence.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

class BraveSearchProvider(BaseSearchProvider):
    """Brave Search API integration (activated when BRAVE_SEARCH_API_KEY is configured)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY")

    @property
    def name(self) -> str:
        return "brave"

    async def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: Optional[str] = None,
    ) -> List[SearchResult]:
        if not await self.is_available():
            return []

        results: List[SearchResult] = []
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": max_results,
        }
        if time_range == "today":
            params["freshness"] = "pd"
        elif time_range == "this_week":
            params["freshness"] = "pw"
        elif time_range == "this_month":
            params["freshness"] = "pm"

        try:
            async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
                res = await client.get("https://api.search.brave.com/res/v1/web/search", params=params)
                if res.status_code == 200:
                    data = res.json()
                    web_results = data.get("web", {}).get("results", [])
                    for item in web_results:
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                snippet=item.get("description", ""),
                                published_date=item.get("page_age"),
                            )
                        )
                else:
                    logger.warning(f"Brave Search API returned status {res.status_code}")
        except Exception as e:
            logger.warning(f"Brave Search API error: {e}")

        return results[:max_results]
