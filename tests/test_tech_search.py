"""Tests for the TechSearchEngine: SearchResult model, deduplication, credibility scoring, and ranking."""
import pytest
from app.services.tech_intelligence.search.base import SearchResult
from app.services.tech_intelligence.search.search_engine import TechSearchEngine


def test_search_result_credibility_from_authoritative_domain():
    """Authoritative domains auto-detect credibility tier and publisher."""
    r = SearchResult(
        title="OpenAI announces o3",
        url="https://openai.com/blog/o3",
        snippet="New reasoning model.",
    )
    assert r.credibility_tier == 1
    assert r.is_primary_source is True
    assert r.publisher == "OpenAI Official"


def test_search_result_credibility_from_unknown_domain():
    """Unknown domains retain default tier and publisher."""
    r = SearchResult(
        title="Random Blog Post",
        url="https://random-blog.com/post",
        snippet="Stuff happened",
    )
    assert r.credibility_tier == 4
    assert r.is_primary_source is False


def test_search_result_to_dict():
    r = SearchResult(
        title="Test Article",
        url="https://theverge.com/test",
        snippet="A tech review.",
    )
    d = r.to_dict()
    assert d["title"] == "Test Article"
    assert d["url"] == "https://theverge.com/test"
    assert "publisher" in d
    assert "credibility_tier" in d
    assert "is_primary_source" in d


def test_deduplication_by_url():
    """Duplicate URLs are removed during processing."""
    engine = TechSearchEngine()
    results = [
        SearchResult(title="Article One", url="https://example.com/a", snippet="First"),
        SearchResult(title="Article One Copy", url="https://example.com/a", snippet="Duplicate"),
        SearchResult(title="Article Two", url="https://example.com/b", snippet="Second"),
    ]
    processed = engine._process_results(results, max_results=10)
    assert len(processed) == 2
    titles = [r.title for r in processed]
    assert "Article One" in titles
    assert "Article Two" in titles


def test_deduplication_by_title():
    """Duplicate titles are removed even if URLs differ."""
    engine = TechSearchEngine()
    results = [
        SearchResult(title="Same Headline", url="https://a.com/1", snippet="First"),
        SearchResult(title="Same Headline", url="https://b.com/2", snippet="Copy"),
    ]
    processed = engine._process_results(results, max_results=10)
    assert len(processed) == 1


def test_credibility_ranking_order():
    """Results are ranked by credibility tier (lower number = higher)."""
    engine = TechSearchEngine()
    results = [
        SearchResult(title="Community Blog", url="https://dev.to/post", snippet="Dev community", credibility_tier=4),
        SearchResult(title="Official NVIDIA", url="https://nvidia.com/news", snippet="Official announcement"),
        SearchResult(title="Wired Article", url="https://wired.com/tech", snippet="Wired coverage"),
    ]
    processed = engine._process_results(results, max_results=10)
    # Tier 1 (nvidia) should come first
    assert processed[0].url == "https://nvidia.com/news"


def test_max_results_limit():
    engine = TechSearchEngine()
    results = [
        SearchResult(title=f"Article {i}", url=f"https://ex.com/{i}", snippet=f"Snippet {i}")
        for i in range(20)
    ]
    processed = engine._process_results(results, max_results=5)
    assert len(processed) == 5


def test_telemetry_structure():
    engine = TechSearchEngine()
    telem = engine.get_telemetry()
    assert "total_searches" in telem
    assert "successful_searches" in telem
    assert "failed_searches" in telem
    assert "success_rate" in telem
    assert "average_latency_ms" in telem
    assert "provider_usage" in telem
    assert "configured_providers" in telem
