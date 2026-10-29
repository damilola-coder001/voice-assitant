import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.tech_intelligence.briefings import TechBriefing, tech_briefings
from app.services.tech_intelligence.cache import tech_cache
from app.services.tech_intelligence.classifier import (
    QueryClassification,
    TechIntent,
    tech_classifier,
)
from app.services.tech_intelligence.cleaner import (
    clean_news_headline,
    clean_news_snippet,
)
from app.services.tech_intelligence.comparison import tech_comparison_engine
from app.services.tech_intelligence.developer import tech_developer_engine
from app.services.tech_intelligence.fact_check import FactCheckResult, fact_checker
from app.services.tech_intelligence.search.base import SearchResult
from app.services.tech_intelligence.search.search_engine import tech_search_engine
from app.services.tech_intelligence.taxonomy import (
    DOMAIN_LABELS,
    ExplanationLevel,
    TechDomain,
)

logger = logging.getLogger(__name__)

class TechIntelligenceResponse:
    def __init__(
        self,
        spoken_response: str,
        sources: List[SearchResult],
        classification: QueryClassification,
        briefing: Optional[TechBriefing] = None,
        fact_check: Optional[FactCheckResult] = None,
    ):
        self.spoken_response = spoken_response
        self.sources = sources
        self.classification = classification
        self.briefing = briefing
        self.fact_check = fact_check

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spoken_response": self.spoken_response,
            "sources": [s.to_dict() for s in self.sources],
            "classification": self.classification.to_dict(),
            "briefing": self.briefing.to_dict() if self.briefing else None,
            "fact_check": self.fact_check.to_dict() if self.fact_check else None,
        }

class TechIntelligenceOrchestrator:
    """Master technology intelligence layer coordinating research, verification, and voice synthesis."""

    def __init__(self):
        # Multi-turn conversation state memory (keyed by session_id)
        self._session_memory: Dict[int, Dict[str, Any]] = {}

    async def process_query(
        self,
        user_message: str,
        session_id: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None,
        user_tech_pref: Optional[Dict[str, Any]] = None,
    ) -> TechIntelligenceResponse:
        clean_msg = user_message.strip()
        lower_msg = clean_msg.lower()

        # Check for context follow-up (e.g. "explain the second one", "where did you get that?", "verify that")
        session_context = self._session_memory.get(session_id, {}) if session_id else {}
        if self._is_follow_up(lower_msg) and session_context:
            return await self._handle_follow_up(clean_msg, lower_msg, session_context)

        # Check conversational queries (greetings, math, identity, time/date)
        from app.services.conversational import conversational_engine
        math_ans = conversational_engine._solve_arithmetic(clean_msg, lower_msg)
        if math_ans:
            return TechIntelligenceResponse(
                spoken_response=math_ans,
                sources=[],
                classification=QueryClassification(
                    intent=TechIntent.GENERAL_TECH,
                    primary_domain=TechDomain.SOFTWARE_DEV,
                    all_domains=[TechDomain.SOFTWARE_DEV],
                    requires_search=False,
                    explanation_level=ExplanationLevel.INTERMEDIATE,
                ),
            )

        if any(greet in lower_msg for greet in ["hello", "hi there", "hey", "good morning", "good evening"]):
            return TechIntelligenceResponse(
                spoken_response="Hello! I am NORE, your technology intelligence voice assistant. What can I research or explain for you today?",
                sources=[],
                classification=QueryClassification(
                    intent=TechIntent.GENERAL_TECH,
                    primary_domain=TechDomain.SOFTWARE_DEV,
                    all_domains=[TechDomain.SOFTWARE_DEV],
                    requires_search=False,
                    explanation_level=ExplanationLevel.INTERMEDIATE,
                ),
            )

        if any(w in lower_msg for w in ["who are you", "what are you", "what is nore"]):
            return TechIntelligenceResponse(
                spoken_response="I am NORE, your real-time technology intelligence assistant. I research current tech developments, verify claims, compare technologies, and deliver live briefings.",
                sources=[],
                classification=QueryClassification(
                    intent=TechIntent.GENERAL_TECH,
                    primary_domain=TechDomain.SOFTWARE_DEV,
                    all_domains=[TechDomain.SOFTWARE_DEV],
                    requires_search=False,
                    explanation_level=ExplanationLevel.INTERMEDIATE,
                ),
            )

        if "time" in lower_msg and any(w in lower_msg for w in ["what", "current", "tell me"]):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC")
            return TechIntelligenceResponse(
                spoken_response=f"The current time is {now}.",
                sources=[],
                classification=QueryClassification(
                    intent=TechIntent.GENERAL_TECH,
                    primary_domain=TechDomain.SOFTWARE_DEV,
                    all_domains=[TechDomain.SOFTWARE_DEV],
                    requires_search=False,
                    explanation_level=ExplanationLevel.INTERMEDIATE,
                ),
            )

        if "date" in lower_msg and any(w in lower_msg for w in ["what", "current", "today"]) and not any(w in lower_msg for w in ["briefing", "news", "happened"]):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
            return TechIntelligenceResponse(
                spoken_response=f"Today is {now}.",
                sources=[],
                classification=QueryClassification(
                    intent=TechIntent.GENERAL_TECH,
                    primary_domain=TechDomain.SOFTWARE_DEV,
                    all_domains=[TechDomain.SOFTWARE_DEV],
                    requires_search=False,
                    explanation_level=ExplanationLevel.INTERMEDIATE,
                ),
            )

        # 1. Classify intent, domain, time-sensitivity, and skill level
        user_level = user_tech_pref.get("tech_explanation_level") if user_tech_pref else None
        classification = tech_classifier.classify(clean_msg, user_level_pref=user_level)

        sources: List[SearchResult] = []
        fact_check_result: Optional[FactCheckResult] = None
        briefing_result: Optional[TechBriefing] = None
        spoken_text = ""

        # 2. Handle Dedicated Briefings
        if classification.intent == TechIntent.TECH_BRIEFING:
            b_type = "daily"
            if classification.primary_domain == TechDomain.AI_ML:
                b_type = "ai"
            elif classification.primary_domain == TechDomain.CYBERSECURITY:
                b_type = "cybersecurity"
            elif classification.primary_domain == TechDomain.SOFTWARE_DEV:
                b_type = "developer"
            elif classification.primary_domain == TechDomain.HARDWARE:
                b_type = "hardware"
            elif classification.primary_domain == TechDomain.STARTUPS_BUSINESS:
                b_type = "startups"

            selected_interests = user_tech_pref.get("tech_interests") if user_tech_pref else None
            user_domains = [d.strip() for d in selected_interests.split(",") if d.strip()] if isinstance(selected_interests, str) else None

            briefing_result = await tech_briefings.generate_briefing(
                briefing_type=b_type, selected_domains=user_domains
            )
            spoken_text = briefing_result.spoken_script
            sources = [item.source for item in briefing_result.items if item.source]

        # 3. Handle Fact Checking
        elif classification.intent == TechIntent.FACT_CHECK or classification.is_fact_check:
            fact_check_result = await fact_checker.verify_claim(clean_msg)
            spoken_text = fact_check_result.spoken_summary
            sources = fact_check_result.sources

        # 4. Handle Comparisons
        elif classification.intent == TechIntent.COMPARISON:
            match = re.search(r"compare\s+([a-zA-Z0-9\.\s_-]+)\s+(and|to|vs|with)\s+([a-zA-Z0-9\.\s_-]+)", lower_msg)
            if not match:
                match = re.search(r"([a-zA-Z0-9\.\s_-]+)\s+vs\.?\s+([a-zA-Z0-9\.\s_-]+)", lower_msg)

            if match:
                item_a = match.group(1).strip()
                item_b = match.group(3).strip() if len(match.groups()) >= 3 else match.group(2).strip()
                spoken_text = tech_comparison_engine.generate_comparison(item_a, item_b)
            else:
                # General comparison research
                spoken_text = tech_comparison_engine.generate_comparison(clean_msg, "")

            # If time-sensitive or search requested, fetch real sources
            if classification.requires_search:
                sources = await tech_search_engine.search(clean_msg, max_results=4)

        # 5. Handle Live Web Research Queries (Current events, releases, company news, security)
        elif classification.requires_search:
            cache_key = f"query:{classification.search_query or clean_msg}"
            cached_ans = await tech_cache.get("search", cache_key)
            if cached_ans:
                spoken_text = cached_ans["spoken_text"]
                sources = [SearchResult(**s) for s in cached_ans.get("sources", [])]
            else:
                sources = await tech_search_engine.search(
                    query=classification.search_query or clean_msg,
                    max_results=5,
                    time_range=classification.time_frame or "recent",
                )
                if sources:
                    spoken_text = self._synthesize_research_answer(clean_msg, sources, classification)
                    await tech_cache.set(
                        "search",
                        cache_key,
                        {"spoken_text": spoken_text, "sources": [s.to_dict() for s in sources]},
                        ttl_seconds=600,
                    )
                else:
                    spoken_text = ""

        # 6. Handle Stable Technical Knowledge (zero unnecessary search per Section 10)
        else:
            base_explanation = self._explain_stable_concept(clean_msg, classification.primary_domain)
            if base_explanation:
                spoken_text = tech_developer_engine.format_explanation(
                    topic=clean_msg,
                    base_explanation=base_explanation,
                    level=classification.explanation_level,
                )
            else:
                spoken_text = ""

        # Store in session memory for follow-up turns
        if session_id:
            self._session_memory[session_id] = {
                "last_query": clean_msg,
                "last_classification": classification,
                "last_sources": sources,
                "last_response": spoken_text,
                "last_briefing": briefing_result,
            }

        return TechIntelligenceResponse(
            spoken_response=spoken_text,
            sources=sources,
            classification=classification,
            briefing=briefing_result,
            fact_check=fact_check_result,
        )

    def _is_follow_up(self, lower: str) -> bool:
        follow_up_patterns = [
            r"\b(second|first|third|last|previous)\b.*\b(one|announcement|point|story)\b",
            r"\bwhere did you get that\b",
            r"\bshow me the source\b",
            r"\bwhat source\b",
            r"\bverify that\b",
            r"\bis that available yet\b",
            r"\bgo deeper\b",
            r"\bexplain more\b",
        ]
        return any(re.search(pat, lower) for pat in follow_up_patterns)

    async def _handle_follow_up(
        self, clean_msg: str, lower_msg: str, session_context: Dict[str, Any]
    ) -> TechIntelligenceResponse:
        last_sources = session_context.get("last_sources", [])
        last_briefing = session_context.get("last_briefing")

        # Handle "where did you get that" or "show me the source"
        if "source" in lower_msg or "where did you get" in lower_msg:
            if last_sources:
                publishers = ", ".join(dict.fromkeys(s.publisher for s in last_sources[:3]))
                top_url = last_sources[0].url
                spoken = f"This information comes directly from {publishers}. The full source links and citations have been updated in your studio view."
                return TechIntelligenceResponse(
                    spoken_response=spoken,
                    sources=last_sources,
                    classification=session_context.get("last_classification", tech_classifier.classify(clean_msg)),
                )
            return TechIntelligenceResponse(
                spoken_response="This was synthesized from general software architectural documentation.",
                sources=[],
                classification=tech_classifier.classify(clean_msg),
            )

        # Handle "explain the second one" / "first one" / "third one"
        if last_briefing and last_briefing.items:
            idx = 0
            if "second" in lower_msg:
                idx = 1
            elif "third" in lower_msg:
                idx = 2
            elif "fourth" in lower_msg:
                idx = 3

            if idx < len(last_briefing.items):
                item = last_briefing.items[idx]
                clean_h = clean_news_headline(item.headline)
                detail = clean_news_snippet(item.summary, clean_h) or clean_h
                spoken = (
                    f"Regarding {clean_h}: {detail}. "
                    f"This development has key implications for {DOMAIN_LABELS.get(item.domain, 'the industry')}."
                )
                item_sources = [item.source] if item.source else []
                return TechIntelligenceResponse(
                    spoken_response=spoken,
                    sources=item_sources,
                    classification=session_context.get("last_classification", tech_classifier.classify(clean_msg)),
                )

        # Default fallback to standard re-query
        classification = tech_classifier.classify(clean_msg)
        return TechIntelligenceResponse(
            spoken_response="Continuing with that context: the primary considerations center on implementation stability and deployment availability.",
            sources=last_sources,
            classification=classification,
        )

    def _synthesize_research_answer(
        self, query: str, sources: List[SearchResult], classification: QueryClassification
    ) -> str:
        """Compose a direct, conversational, human response delivering the facts without robotic meta-attributions."""
        if not sources:
            return (
                f"There are no recent announcements or confirmed reports regarding {query}."
            )

        # Filter out empty or duplicate titles and clean all text
        unique_sources: List[SearchResult] = []
        seen_titles = set()
        for s in sources:
            clean_t = clean_news_headline(s.title)
            if not clean_t:
                continue
            norm_title = re.sub(r"[^a-zA-Z0-9]", "", clean_t.lower())
            if norm_title not in seen_titles:
                seen_titles.add(norm_title)
                s.title = clean_t
                unique_sources.append(s)

        if not unique_sources:
            return (
                f"There are no recent announcements or confirmed reports regarding {query}."
            )

        top_hit = unique_sources[0]
        top_title = top_hit.title.rstrip(".")
        top_snippet = clean_news_snippet(top_hit.snippet, top_title).rstrip(".")

        # Direct, natural human speech - no "According to reports from XYZ" or "reported by ABC"
        if len(unique_sources) > 1:
            second_hit = unique_sources[1]
            second_title = second_hit.title.rstrip(".")
            second_snippet = clean_news_snippet(second_hit.snippet, second_title).rstrip(".")

            if top_snippet:
                first_part = f"{top_title}: {top_snippet}."
            else:
                first_part = f"{top_title}."

            if second_snippet:
                second_part = f"Additionally, {second_title}: {second_snippet}."
            else:
                second_part = f"Additionally, {second_title}."

            spoken = f"{first_part} {second_part}"
        else:
            # Single source
            if top_snippet:
                spoken = f"{top_title}: {top_snippet}."
            else:
                spoken = f"{top_title}."

        # Adjust for skill level if requested
        return tech_developer_engine.format_explanation(
            topic=query,
            base_explanation=spoken,
            level=classification.explanation_level,
        )

    def _explain_stable_concept(self, query: str, domain: TechDomain) -> str:
        """Provide authoritative explanation for stable concepts without wasting web search."""
        lower = query.lower()
        try:
            from app.services.conversational import KNOWLEDGE_BASE
            for keyword, explanation in KNOWLEDGE_BASE.items():
                if keyword in lower:
                    return explanation
        except Exception:
            pass

        if "api" in lower:
            return (
                "An Application Programming Interface standardizes how software components communicate, "
                "defining contracts, serialization formats, and authentication protocols so systems can exchange data reliably."
            )
        if "python" in lower:
            return (
                "Python is a high-level, dynamic language optimized for readability, boasting an unmatched ecosystem "
                "for artificial intelligence, data engineering, and backend microservices."
            )
        if "recursion" in lower:
            return (
                "Recursion is a programming technique where a function solves a problem by calling itself with smaller inputs "
                "until reaching an explicit base condition, unwinding through the call stack."
            )
        if "database" in lower:
            return (
                "A database manages structured data persistence. Relational databases enforce ACID guarantees with SQL schemas, "
                "while distributed NoSQL and vector databases optimize for horizontal scale and high-dimensional search."
            )

        return ""

tech_orchestrator = TechIntelligenceOrchestrator()
