import logging
import os
from typing import List, Optional
import httpx

from app.services.tech_intelligence.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

class TavilySearchProvider(BaseSearchProvider):
    """Tavily Search API integration (activated when TAVILY_API_KEY is configured)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")

    @property
    def name(self) -> str:
        return "tavily"

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
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": max_results,
        }
        if time_range in ["today", "this_week"]:
            payload["days"] = 7 if time_range == "this_week" else 1

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post("https://api.tavily.com/search", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("results", []):
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                snippet=item.get("content", ""),
                                published_date=item.get("published_date"),
                            )
                        )
                else:
                    logger.warning(f"Tavily Search API returned status {res.status_code}")
        except Exception as e:
            logger.warning(f"Tavily Search API error: {e}")

        return results[:max_results]
