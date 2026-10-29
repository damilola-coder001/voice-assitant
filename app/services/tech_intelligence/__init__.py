"""
Technology Intelligence Layer for NORE Voice Platform.
Provides real-time web research, multi-source fact-checking, technical briefings,
developer deep-dives, and multi-skill-level explanations.
"""

from app.services.tech_intelligence.taxonomy import TechDomain, SOURCE_RELIABILITY_TIERS
from app.services.tech_intelligence.classifier import TechIntent, tech_classifier
from app.services.tech_intelligence.search.search_engine import tech_search_engine
from app.services.tech_intelligence.fact_check import fact_checker
from app.services.tech_intelligence.briefings import tech_briefings
from app.services.tech_intelligence.orchestrator import tech_orchestrator

__all__ = [
    "TechDomain",
    "SOURCE_RELIABILITY_TIERS",
    "TechIntent",
    "tech_classifier",
    "tech_search_engine",
    "fact_checker",
    "tech_briefings",
    "tech_orchestrator",
]
