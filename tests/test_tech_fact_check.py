"""Tests for FactChecker: claim extraction, evidence evaluation, verdict matrix."""
import pytest
from app.services.tech_intelligence.fact_check import FactChecker, FactCheckResult
from app.services.tech_intelligence.search.base import SearchResult
from app.services.tech_intelligence.taxonomy import VerificationVerdict


@pytest.fixture
def checker():
    return FactChecker()


def test_extract_clean_claim(checker):
    assert checker._extract_clean_claim("Is it confirmed that OpenAI released GPT-5?") == "OpenAI released GPT-5"
    assert checker._extract_clean_claim("fact check NVIDIA Blackwell Ultra chip") == "NVIDIA Blackwell Ultra chip"
    assert checker._extract_clean_claim("verify that Python 4.0 was announced") == "Python 4.0 was announced"
    # Passthrough for clean input
    assert checker._extract_clean_claim("NVIDIA launched new GPU") == "NVIDIA launched new GPU"


def test_evaluate_confirmed_verdict(checker):
    """Primary source + confirmation markers = CONFIRMED."""
    sources = [
        SearchResult(
            title="NVIDIA officially announces Blackwell Ultra",
            url="https://nvidia.com/news/blackwell",
            snippet="NVIDIA confirmed and officially announced the new Blackwell Ultra chip today.",
        ),
        SearchResult(
            title="NVIDIA confirms Blackwell Ultra launch",
            url="https://arstechnica.com/nvidia-blackwell",
            snippet="NVIDIA press release confirmed the announcement and official launch.",
        ),
    ]
    verdict, confidence, explanation, has_primary, contradictions = checker._evaluate_evidence(
        "NVIDIA announced Blackwell Ultra", sources
    )
    assert verdict == VerificationVerdict.CONFIRMED
    assert confidence >= 0.9
    assert has_primary is True
    assert contradictions is False


def test_evaluate_false_verdict(checker):
    """Multiple refutation markers without confirmation = FALSE."""
    sources = [
        SearchResult(
            title="GPT-5 hoax debunked",
            url="https://theverge.com/debunk",
            snippet="This has been debunked and is false. It was called fake.",
        ),
        SearchResult(
            title="No evidence of GPT-5 at all",
            url="https://arstechnica.com/false-gpt5",
            snippet="It is untrue and refuted by multiple outlets.",
        ),
    ]
    verdict, confidence, _, _, _ = checker._evaluate_evidence("OpenAI released GPT-5", sources)
    assert verdict == VerificationVerdict.FALSE
    assert confidence >= 0.8


def test_evaluate_disputed_verdict(checker):
    """Contradictory evidence (confirmation + refutation) = DISPUTED."""
    sources = [
        SearchResult(
            title="Apple confirms foldable iPhone",
            url="https://apple.com/newsroom",
            snippet="Apple officially confirmed the new foldable iPhone announced today.",
        ),
        SearchResult(
            title="Apple foldable reportedly fake",
            url="https://theverge.com/fake-iphone",
            snippet="This claim is false, debunked by industry analysts.",
        ),
    ]
    verdict, confidence, _, _, contradictions = checker._evaluate_evidence("Apple released foldable iPhone", sources)
    assert verdict == VerificationVerdict.DISPUTED
    assert contradictions is True


def test_evaluate_unverified_verdict(checker):
    """Rumor markers or sparse evidence = UNVERIFIED."""
    sources = [
        SearchResult(
            title="Reportedly anonymous sources say Google is working on AGI",
            url="https://medium.com/rumor",
            snippet="Allegedly unconfirmed speculation from anonymous sources claims Google AGI is near.",
        ),
    ]
    verdict, confidence, _, _, _ = checker._evaluate_evidence("Google achieved AGI", sources)
    assert verdict == VerificationVerdict.UNVERIFIED
    assert confidence <= 0.5


def test_spoken_summary_generation(checker):
    """Spoken summary adapts to each verdict type."""
    assert "confirmed" in checker._generate_spoken_summary("X", VerificationVerdict.CONFIRMED, "Confirmed.", True).lower()
    assert "disputed" in checker._generate_spoken_summary("X", VerificationVerdict.DISPUTED, "Mixed.", True).lower()
    assert "not accurate" in checker._generate_spoken_summary("X", VerificationVerdict.FALSE, "Refuted.", False).lower()
    assert "unverified" in checker._generate_spoken_summary("X", VerificationVerdict.UNVERIFIED, "Unknown.", False).lower()


def test_fact_check_result_to_dict():
    result = FactCheckResult(
        claim="Test claim",
        verdict=VerificationVerdict.LIKELY_TRUE,
        confidence=0.78,
        explanation="Multiple sources confirm.",
        sources=[],
        spoken_summary="Test summary.",
    )
    d = result.to_dict()
    assert d["claim"] == "Test claim"
    assert d["verdict"] == "LIKELY TRUE"
    assert d["confidence"] == 0.78
    assert isinstance(d["sources"], list)
