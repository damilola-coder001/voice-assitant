import logging
import re
from typing import Dict, List, Optional, Tuple

from app.services.tech_intelligence.search.base import SearchResult
from app.services.tech_intelligence.search.search_engine import tech_search_engine
from app.services.tech_intelligence.taxonomy import (
    AUTHORITATIVE_DOMAINS,
    VerificationVerdict,
)

logger = logging.getLogger(__name__)

class FactCheckResult:
    def __init__(
        self,
        claim: str,
        verdict: VerificationVerdict,
        confidence: float,
        explanation: str,
        sources: List[SearchResult],
        has_primary_source: bool = False,
        contradictions_found: bool = False,
        spoken_summary: str = "",
    ):
        self.claim = claim
        self.verdict = verdict
        self.confidence = confidence
        self.explanation = explanation
        self.sources = sources
        self.has_primary_source = has_primary_source
        self.contradictions_found = contradictions_found
        self.spoken_summary = spoken_summary

    def to_dict(self) -> Dict[str, any]:
        return {
            "claim": self.claim,
            "verdict": self.verdict.value,
            "confidence": round(self.confidence, 2),
            "explanation": self.explanation,
            "has_primary_source": self.has_primary_source,
            "contradictions_found": self.contradictions_found,
            "spoken_summary": self.spoken_summary,
            "sources": [s.to_dict() for s in self.sources],
        }

class FactChecker:
    """Multi-source fact-checking and claim verification matrix."""

    REFUTATION_MARKERS = [
        "fake", "false", "hoax", "debunked", "untrue", "denied", "refuted", "unfounded",
        "no evidence", "not true", "incorrect", "misleading", "scam"
    ]

    CONFIRMATION_MARKERS = [
        "official", "confirmed", "announced", "launched", "verified", "statement",
        "press release", "introduced", "advisory", "published"
    ]

    RUMOR_MARKERS = [
        "rumor", "speculation", "leak", "alleged", "reportedly", "unconfirmed",
        "claims", "purported", "anonymous sources"
    ]

    async def verify_claim(self, claim_query: str) -> FactCheckResult:
        clean_claim = self._extract_clean_claim(claim_query)
        logger.info(f"Fact-checking claim: '{clean_claim}'")

        # 1. Search primary sources and reputable journalism
        search_results = await tech_search_engine.search(
            query=f"{clean_claim} official announcement confirmation news",
            max_results=6,
            time_range="recent",
        )

        if not search_results:
            # Fallback search with broader terms
            search_results = await tech_search_engine.search(
                query=f"{clean_claim}",
                max_results=5,
            )

        if not search_results:
            return FactCheckResult(
                claim=clean_claim,
                verdict=VerificationVerdict.UNVERIFIED,
                confidence=0.2,
                explanation="No public records or reliable technology reporting could be found regarding this claim.",
                sources=[],
                spoken_summary=f"There are currently no official records or confirmed announcements verifying whether {clean_claim}.",
            )

        # 2. Analyze sources and evidence
        verdict, confidence, explanation, has_primary, has_contradiction = self._evaluate_evidence(
            clean_claim, search_results
        )

        # 3. Generate spoken summary
        spoken_summary = self._generate_spoken_summary(clean_claim, verdict, explanation, has_primary)

        return FactCheckResult(
            claim=clean_claim,
            verdict=verdict,
            confidence=confidence,
            explanation=explanation,
            sources=search_results,
            has_primary_source=has_primary,
            contradictions_found=has_contradiction,
            spoken_summary=spoken_summary,
        )

    def _extract_clean_claim(self, query: str) -> str:
        # Strip fact check prefix
        cleaned = re.sub(
            r"^(is it true that|is that true that|is this true that|is it confirmed that|is that confirmed that|"
            r"is it confirmed|is that confirmed|fact check|verify that|verify if|can you verify|check this claim:?)\s*",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip().rstrip("?").strip()
        return cleaned or query

    def _evaluate_evidence(
        self, claim: str, sources: List[SearchResult]
    ) -> Tuple[VerificationVerdict, float, str, bool, bool]:
        primary_sources = [s for s in sources if s.is_primary_source or s.credibility_tier <= 2]
        has_primary = len(primary_sources) > 0

        combined_text = " ".join(f"{s.title} {s.snippet}".lower() for s in sources)

        # Check refutations
        refutation_count = sum(1 for m in self.REFUTATION_MARKERS if m in combined_text)
        confirmation_count = sum(1 for m in self.CONFIRMATION_MARKERS if m in combined_text)
        rumor_count = sum(1 for m in self.RUMOR_MARKERS if m in combined_text)

        has_contradiction = refutation_count > 0 and confirmation_count > 0

        # Primary source confirms
        if has_primary and confirmation_count >= 2 and refutation_count == 0:
            top_primary = primary_sources[0]
            return (
                VerificationVerdict.CONFIRMED,
                0.95,
                f"Confirmed by primary documentation from {top_primary.publisher}.",
                True,
                False,
            )

        # Refuted / False
        if refutation_count >= 2 and confirmation_count == 0:
            return (
                VerificationVerdict.FALSE,
                0.90,
                "Independent reporting explicitly refutes this claim as untrue or a hoax.",
                has_primary,
                False,
            )

        # Disputed / Contradictory
        if has_contradiction:
            return (
                VerificationVerdict.DISPUTED,
                0.60,
                "Available sources disagree: some outlets report confirmation while others dispute or deny it.",
                has_primary,
                True,
            )

        # Likely true (reported across multiple reputable tech outlets)
        high_tier_sources = [s for s in sources if s.credibility_tier <= 3]
        if len(high_tier_sources) >= 2 and rumor_count == 0:
            publishers = ", ".join(s.publisher for s in high_tier_sources[:2])
            return (
                VerificationVerdict.LIKELY_TRUE,
                0.80,
                f"Reported by reputable technology publications including {publishers}, though waiting on primary documentation.",
                has_primary,
                False,
            )

        # Rumors / Speculation
        if rumor_count >= 1 or len(sources) < 2:
            return (
                VerificationVerdict.UNVERIFIED,
                0.40,
                "This appears to be an unconfirmed report, industry rumor, or speculation without primary source verification.",
                has_primary,
                False,
            )

        return (
            VerificationVerdict.PARTIALLY_TRUE,
            0.65,
            "The claim contains elements of truth, but details or timelines appear unconfirmed.",
            has_primary,
            False,
        )

    def _generate_spoken_summary(
        self, claim: str, verdict: VerificationVerdict, explanation: str, has_primary: bool
    ) -> str:
        if verdict == VerificationVerdict.CONFIRMED:
            return f"Yes, this is confirmed. {explanation}"
        if verdict == VerificationVerdict.LIKELY_TRUE:
            return f"This appears to be accurate based on multiple reputable technology reports, though we are awaiting direct official documentation. {explanation}"
        if verdict == VerificationVerdict.DISPUTED:
            return f"This is currently disputed. Available technology sources report conflicting information. {explanation}"
        if verdict == VerificationVerdict.FALSE:
            return f"That is not accurate. Independent reports and official sources refute this claim. {explanation}"
        if verdict == VerificationVerdict.UNVERIFIED:
            return f"There is currently no official confirmation. It remains an unverified report or industry rumor."
        return f"Regarding whether {claim}: {explanation}"

fact_checker = FactChecker()
