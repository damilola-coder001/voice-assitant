import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional

from app.services.tech_intelligence.cache import tech_cache
from app.services.tech_intelligence.search.base import SearchResult
from app.services.tech_intelligence.search.search_engine import tech_search_engine
from app.services.tech_intelligence.cleaner import (
    clean_news_headline,
    clean_news_snippet,
)
from app.services.tech_intelligence.taxonomy import (
    DOMAIN_EMOJIS,
    DOMAIN_LABELS,
    TechDomain,
)

logger = logging.getLogger(__name__)

class BriefingItem:
    def __init__(
        self,
        domain: TechDomain,
        headline: str,
        summary: str,
        source: Optional[SearchResult] = None,
        importance: str = "high",
    ):
        self.domain = domain
        self.headline = headline
        self.summary = summary
        self.source = source
        self.importance = importance

    def to_dict(self) -> Dict[str, any]:
        return {
            "domain": self.domain.value,
            "domain_label": DOMAIN_LABELS.get(self.domain, self.domain.value),
            "domain_emoji": DOMAIN_EMOJIS.get(self.domain, ""),
            "headline": self.headline,
            "summary": self.summary,
            "importance": self.importance,
            "source": self.source.to_dict() if self.source else None,
        }

class TechBriefing:
    def __init__(
        self,
        briefing_type: str,
        items: List[BriefingItem],
        spoken_script: str,
        generated_at: Optional[str] = None,
    ):
        self.briefing_type = briefing_type
        self.items = items
        self.spoken_script = spoken_script
        self.generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, any]:
        return {
            "briefing_type": self.briefing_type,
            "items": [item.to_dict() for item in self.items],
            "spoken_script": self.spoken_script,
            "generated_at": self.generated_at,
        }

class TechBriefingsEngine:
    """Generates real-time daily, category-specific, and personalized technology briefings."""

    async def generate_briefing(
        self,
        briefing_type: str = "daily",
        selected_domains: Optional[List[str]] = None,
    ) -> TechBriefing:
        cache_key = f"briefing:{briefing_type}:{','.join(sorted(selected_domains or []))}"
        cached = await tech_cache.get("briefing", cache_key)
        if cached:
            return TechBriefing(
                briefing_type=cached["briefing_type"],
                items=[
                    BriefingItem(
                        domain=TechDomain(i["domain"]),
                        headline=i["headline"],
                        summary=i["summary"],
                        source=SearchResult(**i["source"]) if i.get("source") else None,
                        importance=i.get("importance", "high"),
                    )
                    for i in cached["items"]
                ],
                spoken_script=cached["spoken_script"],
                generated_at=cached["generated_at"],
            )

        now_year = datetime.now(timezone.utc).year
        target_domains: List[TechDomain] = []

        if selected_domains:
            for d in selected_domains:
                try:
                    target_domains.append(TechDomain(d.lower()))
                except ValueError:
                    pass

        if not target_domains:
            if briefing_type == "ai":
                target_domains = [TechDomain.AI_ML]
            elif briefing_type == "developer":
                target_domains = [TechDomain.SOFTWARE_DEV]
            elif briefing_type == "cybersecurity":
                target_domains = [TechDomain.CYBERSECURITY]
            elif briefing_type == "hardware":
                target_domains = [TechDomain.HARDWARE]
            elif briefing_type == "startups":
                target_domains = [TechDomain.STARTUPS_BUSINESS]
            else:
                # Comprehensive daily briefing covering key active domains
                target_domains = [
                    TechDomain.AI_ML,
                    TechDomain.CYBERSECURITY,
                    TechDomain.SOFTWARE_DEV,
                    TechDomain.HARDWARE,
                ]

        # Gather real search data for each domain in parallel
        domain_queries = {
            TechDomain.AI_ML: f"top AI machine learning developments announcements {now_year}",
            TechDomain.SOFTWARE_DEV: f"software developer tooling releases updates {now_year}",
            TechDomain.CYBERSECURITY: f"cybersecurity advisories vulnerabilities breaches {now_year}",
            TechDomain.HARDWARE: f"semiconductor GPU processor hardware announcements {now_year}",
            TechDomain.STARTUPS_BUSINESS: f"tech startups venture capital acquisitions {now_year}",
            TechDomain.EMERGING_TECH: f"quantum computing robotics breakthrough {now_year}",
        }

        tasks = [
            tech_search_engine.search(domain_queries[d], max_results=2, time_range="today")
            for d in target_domains
        ]
        results_per_domain = await asyncio.gather(*tasks, return_exceptions=True)

        items: List[BriefingItem] = []
        for d, res in zip(target_domains, results_per_domain):
            if isinstance(res, list) and res:
                clean_h = clean_news_headline(top_hit.title)
                clean_s = clean_news_snippet(top_hit.snippet, clean_h) or clean_h
                items.append(
                    BriefingItem(
                        domain=d,
                        headline=clean_h,
                        summary=clean_s,
                        source=top_hit,
                    )
                )

        # Build natural voice-first conversational script
        spoken_script = self._compose_spoken_briefing(briefing_type, items)

        briefing = TechBriefing(
            briefing_type=briefing_type,
            items=items,
            spoken_script=spoken_script,
        )

        # Cache briefing for 30 minutes
        await tech_cache.set("briefing", cache_key, briefing.to_dict(), ttl_seconds=1800)
        return briefing

    def _compose_spoken_briefing(self, briefing_type: str, items: List[BriefingItem]) -> str:
        if not items:
            return "Here is your technology briefing: Systems are currently quiet, with no breaking alerts detected in the last few hours."

        count = len(items)
        intro = f"Here is your technology briefing. {count} key developments are leading today."
        if briefing_type == "ai":
            intro = "Here is today's AI intelligence briefing."
        elif briefing_type == "cybersecurity":
            intro = "Here is today's cybersecurity threat and advisory briefing."
        elif briefing_type == "developer":
            intro = "Here is the latest briefing for developers."

        body_parts = []
        for i, item in enumerate(items, 1):
            domain_label = DOMAIN_LABELS.get(item.domain, "Technology")
            clean_head = clean_news_headline(item.headline)
            clean_sum = clean_news_snippet(item.summary, clean_head)
            if clean_sum:
                point = f"In {domain_label}: {clean_head}. {clean_sum}."
            else:
                point = f"In {domain_label}: {clean_head}."
            body_parts.append(point)

        return f"{intro} " + " ".join(body_parts)

tech_briefings = TechBriefingsEngine()
