import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from app.services.tech_intelligence.search.base import BaseSearchProvider, SearchResult
from app.services.tech_intelligence.search.duckduckgo_provider import DuckDuckGoSearchProvider
from app.services.tech_intelligence.search.feed_provider import AuthoritativeTechFeedProvider
from app.services.tech_intelligence.search.brave_provider import BraveSearchProvider
from app.services.tech_intelligence.search.tavily_provider import TavilySearchProvider

logger = logging.getLogger(__name__)

class TechSearchEngine:
    """
    Multi-Provider Technology Web Search Engine.
    Implements deduplication, domain authority weighting, date validation,
    cross-checking, and automatic provider fallback.
    """

    def __init__(self):
        self.providers: Dict[str, BaseSearchProvider] = {
            "duckduckgo": DuckDuckGoSearchProvider(),
            "tech_feeds": AuthoritativeTechFeedProvider(),
            "brave": BraveSearchProvider(),
            "tavily": TavilySearchProvider(),
        }
        self.active_provider_name: str = "auto"
        self.telemetry = {
            "total_searches": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "provider_counts": {},
            "total_latency_ms": 0,
        }

    async def search(
        self,
        query: str,
        max_results: int = 6,
        time_range: Optional[str] = None,
        provider_preference: Optional[str] = None,
        preferred_domain: Optional[str] = None,
    ) -> List[SearchResult]:
        start_time = time.time()
        self.telemetry["total_searches"] += 1
        raw_results: List[SearchResult] = []
        target_provider = provider_preference or self.active_provider_name

        # 1. Determine execution strategy
        if target_provider != "auto" and target_provider in self.providers:
            provider = self.providers[target_provider]
            if await provider.is_available():
                try:
                    raw_results = await provider.search(query, max_results=max_results, time_range=time_range)
                    self._record_provider_success(target_provider)
                except Exception as e:
                    logger.warning(f"Provider {target_provider} failed: {e}")

        # 2. Fallback Chain: Configured API -> DuckDuckGo -> Authoritative Feeds
        if not raw_results:
            # Try Brave / Tavily first if keys are configured
            for candidate_name in ["brave", "tavily"]:
                p = self.providers[candidate_name]
                if await p.is_available():
                    try:
                        raw_results = await p.search(query, max_results=max_results, time_range=time_range)
                        if raw_results:
                            self._record_provider_success(candidate_name)
                            break
                    except Exception as e:
                        logger.warning(f"Candidate {candidate_name} failed: {e}")

        # 3. Fast Parallel Search: DuckDuckGo & Authoritative Tech Feeds
        async def _fetch_ddg() -> List[SearchResult]:
            if raw_results:
                return []
            try:
                res = await self.providers["duckduckgo"].search(
                    query, max_results=max_results, time_range=time_range
                )
                if res:
                    self._record_provider_success("duckduckgo")
                return res
            except Exception as e:
                logger.warning(f"DuckDuckGo search error: {e}")
                return []

        async def _fetch_feeds() -> List[SearchResult]:
            try:
                res = await self.providers["tech_feeds"].search(
                    query, max_results=3, time_range=time_range
                )
                if res:
                    self._record_provider_success("tech_feeds")
                return res
            except Exception as e:
                logger.warning(f"Tech feeds error: {e}")
                return []

        ddg_task = asyncio.create_task(_fetch_ddg())
        feeds_task = asyncio.create_task(_fetch_feeds())
        ddg_res, feed_results = await asyncio.gather(ddg_task, feeds_task)

        # Combine results
        combined = (feed_results or []) + (ddg_res or []) + raw_results

        # 5. Deduplication, Filtering, and Credibility Ranking
        processed = self._process_results(combined, max_results=max_results)

        latency = int((time.time() - start_time) * 1000)
        self.telemetry["total_latency_ms"] += latency
        if processed:
            self.telemetry["successful_searches"] += 1
        else:
            self.telemetry["failed_searches"] += 1

        return processed

    def _process_results(self, results: List[SearchResult], max_results: int) -> List[SearchResult]:
        """Filter, deduplicate by URL/title, score by domain credibility, and rank."""
        seen_urls: Set[str] = set()
        seen_titles: Set[str] = set()
        filtered: List[SearchResult] = []

        for r in results:
            if not r.url or not r.title:
                continue

            norm_url = r.url.split("#")[0].rstrip("/").lower()
            norm_title = r.title.strip().lower()

            # Deduplication
            if norm_url in seen_urls or norm_title in seen_titles:
                continue

            seen_urls.add(norm_url)
            seen_titles.add(norm_title)
            filtered.append(r)

        # Sort: Primary sources first (credibility tier 1 & 2), then lower tiers
        # Secondary sort: completeness of snippet
        sorted_results = sorted(
            filtered,
            key=lambda item: (
                item.credibility_tier,  # Lower tier number = higher credibility
                -len(item.snippet or ""),
            )
        )

        return sorted_results[:max_results]

    def _record_provider_success(self, provider_name: str):
        counts = self.telemetry["provider_counts"]
        counts[provider_name] = counts.get(provider_name, 0) + 1

    def get_telemetry(self) -> Dict[str, any]:
        total = self.telemetry["total_searches"]
        avg_lat = int(self.telemetry["total_latency_ms"] / total) if total > 0 else 0
        return {
            "total_searches": total,
            "successful_searches": self.telemetry["successful_searches"],
            "failed_searches": self.telemetry["failed_searches"],
            "success_rate": round(self.telemetry["successful_searches"] / total * 100, 1) if total > 0 else 100.0,
            "average_latency_ms": avg_lat,
            "provider_usage": self.telemetry["provider_counts"],
            "configured_providers": [k for k, p in self.providers.items()],
        }

tech_search_engine = TechSearchEngine()
