import re
from typing import Dict, Optional

from app.services.tech_intelligence.taxonomy import ExplanationLevel

class DeveloperIntelligenceEngine:
    """Provides calibrated technical explanations across 4 skill levels and developer documentation insight."""

    def format_explanation(
        self,
        topic: str,
        base_explanation: str,
        level: ExplanationLevel,
    ) -> str:
        """Adjust tone, vocabulary, and depth to match requested skill level."""
        if level == ExplanationLevel.BEGINNER:
            return (
                f"In simple terms, think of {topic} like a well-organized service: "
                f"it handles complex underlying tasks behind the scenes so you can focus on what you need done. "
                f"{self._simplify_text(base_explanation)}"
            )

        if level == ExplanationLevel.ADVANCED:
            return (
                f"From an engineering and systems design perspective, {topic} centers on modularity, "
                f"interface decoupling, and state management. "
                f"{base_explanation} "
                f"Architecturally, this ensures scalable throughput, fault isolation, and predictable execution cycles."
            )

        if level == ExplanationLevel.EXPERT:
            return (
                f"At the systems level, {base_explanation} "
                f"Critical constraints involve memory alignment, concurrency primitives, latency characteristics, "
                f"and cache line efficiency under heavy distributed load."
            )

        # Default: Intermediate
        return base_explanation

    def _simplify_text(self, text: str) -> str:
        # Strip out dense jargon for beginner mode
        cleaned = re.sub(r"\b(asynchronous|polymorphism|determinism|concurrency|microservices|distributed)\b", "organized", text, flags=re.IGNORECASE)
        sentences = [s.strip() for s in cleaned.split(".") if s.strip()]
        return ". ".join(sentences[:2]) + "." if sentences else cleaned

tech_developer_engine = DeveloperIntelligenceEngine()
