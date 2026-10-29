import enum
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from app.services.tech_intelligence.taxonomy import (
    DOMAIN_KEYWORDS,
    ExplanationLevel,
    TechDomain,
    TechIntent,
    QueryIntent,
)


class QueryClassification:
    def __init__(
        self,
        intent: TechIntent = TechIntent.GENERAL_TECH,
        primary_domain: TechDomain = TechDomain.AI_ML,
        all_domains: Optional[List[TechDomain]] = None,
        requires_search: bool = False,
        explanation_level: ExplanationLevel = ExplanationLevel.INTERMEDIATE,
        time_frame: Optional[str] = None,
        search_query: Optional[str] = None,
        is_comparison: bool = False,
        is_fact_check: bool = False,
        entities: Optional[List[str]] = None,
        confidence: float = 1.0,
    ):
        self.intent = intent
        self.primary_domain = primary_domain
        self.all_domains = all_domains if all_domains is not None else [primary_domain]
        self.requires_search = requires_search
        self.explanation_level = explanation_level
        self.time_frame = time_frame
        self.search_query = search_query
        self.is_comparison = is_comparison
        self.is_fact_check = is_fact_check
        self.entities = entities or []
        self.confidence = confidence

    def to_dict(self) -> Dict[str, any]:
        return {
            "intent": self.intent.value,
            "primary_domain": self.primary_domain.value,
            "all_domains": [d.value for d in self.all_domains],
            "requires_search": self.requires_search,
            "explanation_level": self.explanation_level.value,
            "time_frame": self.time_frame,
            "search_query": self.search_query,
            "is_comparison": self.is_comparison,
            "is_fact_check": self.is_fact_check,
            "entities": self.entities,
            "confidence": self.confidence,
        }

class TechClassifier:
    """Classifies user queries into technical domains, search intents, and freshness requirements."""

    TIME_SENSITIVE_TRIGGERS = [
        "today", "yesterday", "this week", "this month", "latest", "recent", "recently",
        "newest", "current", "currently", "now", "happening", "announced", "release",
        "released", "launched", "update", "updated", "what's new", "what is new",
        "breaking", "price", "pricing", "rumor", "leak", "confirmed", "patch", "advisory",
        "cve", "breach", "funding", "just", "2026", "2025"
    ]

    STABLE_KNOWLEDGE_PATTERNS = [
        r"^what is (an?|the)?\s*([a-z0-9_-]+(?:\s+[a-z0-9_-]+){0,2})\??$",
        r"^how does ([a-z0-9_-]+(?:\s+[a-z0-9_-]+){0,2}) work\??$",
        r"^what does ([a-z0-9_-]+(?:\s+[a-z0-9_-]+){0,2}) mean\??$",
        r"^explain ([a-z0-9_-]+(?:\s+[a-z0-9_-]+){0,2})\??$",
        r"^define ([a-z0-9_-]+(?:\s+[a-z0-9_-]+){0,2})\??$",
    ]

    BRIEFING_TRIGGERS = [
        "briefing", "roundup", "round-up", "digest", "tech news", "catch me up",
        "what happened today", "what's happening today", "biggest stories", "top stories",
        "what should i know today", "what is important today"
    ]

    FACT_CHECK_TRIGGERS = [
        "is this true", "is it true", "is that true", "is it confirmed", "is that confirmed",
        "actually confirmed", "fact check", "check this claim", "verify", "is there proof",
        "did they really", "has it been confirmed", "debunk", "is it a rumor", "rumor or fact"
    ]

    COMPARISON_TRIGGERS = [
        "compare", "versus", " vs ", " vs. ", "difference between", "better than",
        "should i use", "or should i", "which one is better"
    ]

    def classify(
        self,
        query: str,
        user_level_pref: Optional[str] = None,
    ) -> QueryClassification:
        clean = query.strip()
        lower = clean.lower()

        # 1. Determine Explanation Level
        level = self._detect_explanation_level(lower, user_level_pref)

        # 2. Detect Domains
        primary_domain, all_domains, entities = self._detect_domains(lower)

        # 3. Detect Time Sensitivity & Search Requirement
        requires_search, time_frame = self._detect_time_sensitivity(clean, lower)

        # 4. Detect Intent
        intent, is_comparison, is_fact_check = self._detect_intent(
            clean, lower, primary_domain, requires_search
        )

        # Build clean search query for downstream web engine
        search_query = self._build_search_query(clean, lower, intent, primary_domain, time_frame)

        return QueryClassification(
            intent=intent,
            primary_domain=primary_domain,
            all_domains=all_domains,
            requires_search=requires_search,
            explanation_level=level,
            time_frame=time_frame,
            search_query=search_query,
            is_comparison=is_comparison,
            is_fact_check=is_fact_check,
            entities=entities,
        )

    def _detect_explanation_level(self, lower: str, user_pref: Optional[str]) -> ExplanationLevel:
        if any(w in lower for w in ["like a beginner", "explain simply", "simple terms", "like i'm five", "eli5", "for kids", "basic explanation"]):
            return ExplanationLevel.BEGINNER
        if any(w in lower for w in ["expert level", "kernel", "assembly", "compiler internals", "low level", "deepest details"]):
            return ExplanationLevel.EXPERT
        if any(w in lower for w in ["like a developer", "like a software engineer", "technical version", "go deeper", "architectural", "in detail"]):
            return ExplanationLevel.ADVANCED

        if user_pref and user_pref.lower() in [e.value for e in ExplanationLevel]:
            return ExplanationLevel(user_pref.lower())

        return ExplanationLevel.INTERMEDIATE

    def _detect_domains(self, lower: str) -> Tuple[TechDomain, List[TechDomain], List[str]]:
        scores: Dict[TechDomain, int] = {domain: 0 for domain in TechDomain}
        matched_entities: List[str] = []

        for domain, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                    scores[domain] += (3 if len(kw.split()) > 1 else 1)
                    if kw not in matched_entities:
                        matched_entities.append(kw)

        sorted_domains = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if sorted_domains[0][1] > 0:
            primary = sorted_domains[0][0]
            all_active = [d for d, s in sorted_domains if s > 0]
        else:
            primary = TechDomain.AI_ML  # Default domain
            all_active = [TechDomain.AI_ML]

        return primary, all_active, matched_entities

    def _detect_time_sensitivity(self, clean: str, lower: str) -> Tuple[bool, Optional[str]]:
        # Detect explicit time frame
        time_frame = None
        if "today" in lower:
            time_frame = "today"
        elif "this week" in lower:
            time_frame = "this_week"
        elif "this month" in lower:
            time_frame = "this_month"
        elif "latest" in lower or "recent" in lower or "recently" in lower:
            time_frame = "recent"

        # Explicit search request
        if any(w in lower for w in ["search the web", "look up", "google this", "find out what happened", "check the web"]):
            return True, time_frame or "recent"

        # Time sensitive markers
        has_time_marker = any(re.search(r"\b" + re.escape(marker) + r"\b", lower) for marker in self.TIME_SENSITIVE_TRIGGERS)

        # Check if stable query
        is_stable = False
        for pat in self.STABLE_KNOWLEDGE_PATTERNS:
            if re.match(pat, lower):
                is_stable = True
                break

        if is_stable and not has_time_marker:
            return False, None

        if has_time_marker:
            return True, time_frame or "recent"

        # Briefing or current news
        if any(t in lower for t in self.BRIEFING_TRIGGERS):
            return True, "today"

        # Fact checking
        if any(t in lower for t in self.FACT_CHECK_TRIGGERS):
            return True, "recent"

        # Questions about versions, releases, companies, revenue, roadmaps
        if any(w in lower for w in ["version", "release", "patch", "cve", "announcement", "working on", "revenue", "valuation", "earnings", "roadmap", "plans"]):
            return True, "recent"

        return False, None

    def _detect_intent(
        self,
        clean: str,
        lower: str,
        domain: TechDomain,
        requires_search: bool,
    ) -> Tuple[TechIntent, bool, bool]:
        # 1. Briefing
        if any(t in lower for t in self.BRIEFING_TRIGGERS):
            return TechIntent.TECH_BRIEFING, False, False

        # 2. Fact Check
        if any(t in lower for t in self.FACT_CHECK_TRIGGERS):
            return TechIntent.FACT_CHECK, False, True

        # 3. Comparison
        if any(t in lower for t in self.COMPARISON_TRIGGERS) or ("difference" in lower and "between" in lower):
            return TechIntent.COMPARISON, True, False

        # 4. Trend Analysis
        if any(w in lower for w in ["trending", "trend", "trends", "what are developers using", "popular now", "hype"]):
            return TechIntent.TREND_ANALYSIS, False, False

        # 5. Security Research
        if domain == TechDomain.CYBERSECURITY or any(w in lower for w in ["cve-", "vulnerability", "breach", "zero-day", "exploit", "cisa"]):
            return TechIntent.SECURITY_RESEARCH, False, False

        # 6. Developer Research / Tutorial
        if any(w in lower for w in ["how to", "tutorial", "walkthrough", "guide", "step by step", "example code", "code snippet"]):
            return TechIntent.TUTORIAL, False, False

        if domain == TechDomain.SOFTWARE_DEV and ("version" in lower or "changelog" in lower or "breaking change" in lower or "docs" in lower or "syntax" in lower):
            return TechIntent.DEVELOPER_RESEARCH, False, False

        # 7. Product & Company Research
        if any(w in lower for w in ["chip", "gpu", "cpu", "iphone", "pixel", "laptop", "server", "spec", "specs", "benchmark"]):
            return TechIntent.PRODUCT_RESEARCH, False, False

        if any(w in lower for w in ["openai", "anthropic", "nvidia", "google", "meta", "microsoft", "apple", "startup", "acquisition", "funding", "revenue", "valuation", "working on"]):
            return TechIntent.COMPANY_RESEARCH, False, False

        # 8. Current News vs Explanation
        if requires_search:
            return TechIntent.CURRENT_NEWS, False, False

        return TechIntent.TECH_EXPLANATION, False, False

    def _build_search_query(
        self,
        clean: str,
        lower: str,
        intent: TechIntent,
        domain: TechDomain,
        time_frame: Optional[str],
    ) -> str:
        # Strip conversational prefix
        stripped = re.sub(
            r"^(search the web and find out|search the web for|find out|tell me|give me|what is|what are|explain|can you tell me|what's happening with|what's happening in|what happened in|is it confirmed that|is this true that|verify if)\s*",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip().rstrip("?").strip()

        now_year = datetime.now(timezone.utc).year

        if intent == TechIntent.TECH_BRIEFING:
            if domain == TechDomain.AI_ML:
                return f"AI machine learning developments news {now_year}"
            if domain == TechDomain.CYBERSECURITY:
                return f"cybersecurity advisories vulnerabilities breaches {now_year}"
            if domain == TechDomain.SOFTWARE_DEV:
                return f"software developer tools releases updates {now_year}"
            return f"technology news announcements developments {now_year}"

        if intent == TechIntent.FACT_CHECK:
            return f"{stripped} official announcement confirmation news"

        if time_frame == "today":
            return f"{stripped} {now_year} news"

        return f"{stripped} {now_year}"

tech_classifier = TechClassifier()
