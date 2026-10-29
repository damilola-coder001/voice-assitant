"""Tests for TechBriefingsEngine: BriefingItem model, spoken script generation."""
import pytest
from app.services.tech_intelligence.briefings import (
    BriefingItem,
    TechBriefing,
    TechBriefingsEngine,
)
from app.services.tech_intelligence.search.base import SearchResult
from app.services.tech_intelligence.taxonomy import TechDomain, DOMAIN_LABELS, DOMAIN_EMOJIS


def test_briefing_item_to_dict():
    item = BriefingItem(
        domain=TechDomain.AI_ML,
        headline="OpenAI launches GPT-5 Turbo",
        summary="The latest model offers 2x throughput.",
        importance="critical",
    )
    d = item.to_dict()
    assert d["domain"] == "ai_ml"
    assert d["domain_label"] == DOMAIN_LABELS[TechDomain.AI_ML]
    assert d["domain_emoji"] == DOMAIN_EMOJIS[TechDomain.AI_ML]
    assert d["headline"] == "OpenAI launches GPT-5 Turbo"
    assert d["importance"] == "critical"


def test_briefing_item_with_source():
    source = SearchResult(title="Source Article", url="https://openai.com/news", snippet="Details")
    item = BriefingItem(
        domain=TechDomain.SOFTWARE_DEV,
        headline="Python 3.14 released",
        summary="New features in Python 3.14.",
        source=source,
    )
    d = item.to_dict()
    assert d["source"] is not None
    assert d["source"]["url"] == "https://openai.com/news"


def test_tech_briefing_to_dict():
    items = [
        BriefingItem(domain=TechDomain.AI_ML, headline="AI News", summary="Top story"),
        BriefingItem(domain=TechDomain.CYBERSECURITY, headline="CVE Alert", summary="Critical patch"),
    ]
    briefing = TechBriefing(
        briefing_type="daily",
        items=items,
        spoken_script="Here is your daily briefing.",
    )
    d = briefing.to_dict()
    assert d["briefing_type"] == "daily"
    assert len(d["items"]) == 2
    assert d["spoken_script"] == "Here is your daily briefing."
    assert "generated_at" in d


def test_spoken_briefing_composition():
    engine = TechBriefingsEngine()

    items = [
        BriefingItem(
            domain=TechDomain.AI_ML,
            headline="GPT-5 announcement",
            summary="New model.",
            source=SearchResult(title="T", url="https://openai.com/x", snippet="S"),
        ),
        BriefingItem(
            domain=TechDomain.CYBERSECURITY,
            headline="Critical CVE advisory",
            summary="Patch now.",
            source=SearchResult(title="T", url="https://cisa.gov/x", snippet="S"),
        ),
    ]
    script = engine._compose_spoken_briefing("daily", items)
    assert "briefing" in script.lower()
    assert "AI" in script
    assert "Cybersecurity" in script


def test_empty_briefing_spoken_script():
    engine = TechBriefingsEngine()
    script = engine._compose_spoken_briefing("daily", [])
    assert "quiet" in script.lower() or "briefing" in script.lower()


def test_ai_briefing_type_intro():
    engine = TechBriefingsEngine()
    items = [
        BriefingItem(
            domain=TechDomain.AI_ML,
            headline="Test",
            summary="Summary",
            source=SearchResult(title="T", url="https://x.com/y", snippet="S"),
        ),
    ]
    script = engine._compose_spoken_briefing("ai", items)
    assert "ai" in script.lower()


def test_cybersecurity_briefing_type_intro():
    engine = TechBriefingsEngine()
    items = [
        BriefingItem(
            domain=TechDomain.CYBERSECURITY,
            headline="Test",
            summary="Summary",
            source=SearchResult(title="T", url="https://x.com/y", snippet="S"),
        ),
    ]
    script = engine._compose_spoken_briefing("cybersecurity", items)
    assert "cybersecurity" in script.lower()


def test_research_answer_deduplication_different_publishers():
    from app.services.tech_intelligence.orchestrator import TechIntelligenceOrchestrator
    from app.services.tech_intelligence.classifier import QueryClassification
    from app.services.tech_intelligence.taxonomy import QueryIntent, ExplanationLevel

    orchestrator = TechIntelligenceOrchestrator()
    classification = QueryClassification(
        primary_domain=TechDomain.AI_ML,
        intent=QueryIntent.REALTIME_NEWS,
        explanation_level=ExplanationLevel.INTERMEDIATE,
        requires_search=True,
    )
    headline_1 = "Calls to slow AI spark new frontier"
    headline_2 = "OpenAI proposes global standards"
    sources = [
        SearchResult(
            title=headline_1,
            publisher="Al Jazeera",
            url="https://aljazeera.com/news",
            snippet=f"{headline_1} — reported by Al Jazeera",
        ),
        SearchResult(
            title=headline_2,
            publisher="CNBC",
            url="https://cnbc.com/news",
            snippet=f"{headline_2} — reported by CNBC",
        ),
    ]
    spoken = orchestrator._synthesize_research_answer("What happened in AI today?", sources, classification)
    assert headline_1 in spoken
    # Ensure the first headline is NOT duplicated twice in the output
    assert spoken.count(headline_1) == 1
    assert headline_2 in spoken
    assert spoken.count(headline_2) == 1
    assert "According to reports from" not in spoken
    assert "reported by" not in spoken


def test_research_answer_deduplication_same_publisher():
    from app.services.tech_intelligence.orchestrator import TechIntelligenceOrchestrator
    from app.services.tech_intelligence.classifier import QueryClassification
    from app.services.tech_intelligence.taxonomy import QueryIntent, ExplanationLevel

    orchestrator = TechIntelligenceOrchestrator()
    classification = QueryClassification(
        primary_domain=TechDomain.CYBERSECURITY,
        intent=QueryIntent.REALTIME_NEWS,
        explanation_level=ExplanationLevel.INTERMEDIATE,
        requires_search=True,
    )
    headline_1 = "Critical vulnerability found in Linux kernel"
    headline_2 = "Patch released for zero-day flaw"
    sources = [
        SearchResult(
            title=headline_1,
            publisher="CISA",
            url="https://cisa.gov/1",
            snippet=f"{headline_1} — reported by CISA",
        ),
        SearchResult(
            title=headline_2,
            publisher="CISA",
            url="https://cisa.gov/2",
            snippet=f"{headline_2} — reported by CISA",
        ),
    ]
    spoken = orchestrator._synthesize_research_answer("What cybersecurity alerts are active?", sources, classification)
    assert headline_1 in spoken
    assert spoken.count(headline_1) == 1
    assert headline_2 in spoken
    assert spoken.count(headline_2) == 1
    assert "They also report that" not in spoken
    assert "reported by" not in spoken


def test_research_answer_with_informative_snippet():
    from app.services.tech_intelligence.orchestrator import TechIntelligenceOrchestrator
    from app.services.tech_intelligence.classifier import QueryClassification
    from app.services.tech_intelligence.taxonomy import QueryIntent, ExplanationLevel

    orchestrator = TechIntelligenceOrchestrator()
    classification = QueryClassification(
        primary_domain=TechDomain.CYBERSECURITY,
        intent=QueryIntent.REALTIME_NEWS,
        explanation_level=ExplanationLevel.INTERMEDIATE,
        requires_search=True,
    )
    sources = [
        SearchResult(
            title="CVE-2026-9999 Advisory",
            publisher="NIST NVD",
            url="https://nvd.nist.gov",
            snippet="A remote execution flaw has been patched in version 3.2. Mitigation: upgrade immediately.",
            is_primary_source=True,
        ),
    ]
    spoken = orchestrator._synthesize_research_answer("Tell me about CVE-2026-9999", sources, classification)
    assert "CVE-2026-9999 Advisory" in spoken
    assert spoken.count("CVE-2026-9999 Advisory") == 1
    assert "remote execution flaw has been patched" in spoken
    assert "According to" not in spoken


def test_cleaner_strips_media_citations_and_domains():
    from app.services.tech_intelligence.cleaner import clean_news_headline
    dirty = "OpenAI proposes development of global AI standards to guide alignment, RSI — reported by CNBC"
    cleaned = clean_news_headline(dirty)
    assert cleaned == "OpenAI proposes development of global AI standards to guide alignment"
    assert "reported by" not in cleaned
    assert "CNBC" not in cleaned
    assert "RSI" not in cleaned

