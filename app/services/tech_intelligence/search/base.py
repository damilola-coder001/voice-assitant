from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.services.tech_intelligence.taxonomy import (
    AUTHORITATIVE_DOMAINS,
    SOURCE_RELIABILITY_TIERS,
)

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    publisher: str = "Web Source"
    published_date: Optional[str] = None
    domain: str = ""
    credibility_tier: int = 4
    is_primary_source: bool = False
    metadata: Dict[str, any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.domain and self.url:
            try:
                parsed = urlparse(self.url)
                self.domain = parsed.netloc.lower().lstrip("www.")
            except Exception:
                self.domain = "web"

        # Auto-detect credibility tier and publisher from known authoritative domains
        if self.domain in AUTHORITATIVE_DOMAINS:
            entry = AUTHORITATIVE_DOMAINS[self.domain]
            self.credibility_tier = entry.get("tier", self.credibility_tier)
            if self.publisher == "Web Source" or not self.publisher:
                self.publisher = entry.get("name", self.domain)
            if self.credibility_tier <= 2:
                self.is_primary_source = True

        if not self.published_date:
            self.published_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def to_dict(self) -> Dict[str, any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "publisher": self.publisher,
            "published_date": self.published_date,
            "domain": self.domain,
            "credibility_tier": self.credibility_tier,
            "is_primary_source": self.is_primary_source,
        }

class BaseSearchProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the search provider."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: Optional[str] = None,
    ) -> List[SearchResult]:
        """Execute web search and return normalized search results."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is configured and available."""
        pass
