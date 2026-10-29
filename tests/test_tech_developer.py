"""Tests for TechComparisonEngine and DeveloperIntelligenceEngine."""
import pytest
from app.services.tech_intelligence.comparison import TechComparisonEngine
from app.services.tech_intelligence.developer import DeveloperIntelligenceEngine
from app.services.tech_intelligence.taxonomy import ExplanationLevel


@pytest.fixture
def comparison_engine():
    return TechComparisonEngine()


@pytest.fixture
def developer_engine():
    return DeveloperIntelligenceEngine()


# --- Comparison Engine ---

def test_known_comparison_react_vs_vue(comparison_engine):
    result = comparison_engine.generate_comparison("React", "Vue")
    assert "React" in result
    assert "Vue" in result
    assert "ecosystem" in result.lower() or "component" in result.lower()


def test_known_comparison_claude_vs_gemini(comparison_engine):
    result = comparison_engine.generate_comparison("Claude", "Gemini")
    assert "Claude" in result
    assert "Gemini" in result
    assert "context" in result.lower() or "code" in result.lower() or "multimodal" in result.lower()


def test_known_comparison_postgres_vs_mysql(comparison_engine):
    result = comparison_engine.generate_comparison("Postgres", "MySQL")
    assert "PostgreSQL" in result or "Postgres" in result
    assert "MySQL" in result


def test_known_comparison_docker_vs_kubernetes(comparison_engine):
    result = comparison_engine.generate_comparison("Docker", "Kubernetes")
    assert "Docker" in result
    assert "Kubernetes" in result
    assert "container" in result.lower() or "orchestrat" in result.lower()


def test_known_comparison_python_vs_rust(comparison_engine):
    result = comparison_engine.generate_comparison("Python", "Rust")
    assert "Python" in result
    assert "Rust" in result


def test_reverse_order_comparison(comparison_engine):
    """Comparison should work regardless of argument order."""
    result = comparison_engine.generate_comparison("Vue", "React")
    assert "React" in result
    assert "Vue" in result


def test_unknown_comparison_fallback(comparison_engine):
    """Unknown comparisons produce a generic but useful fallback."""
    result = comparison_engine.generate_comparison("Elixir", "Haskell")
    assert "Elixir" in result
    assert "Haskell" in result
    assert len(result) > 50


# --- Developer Intelligence Engine ---

def test_beginner_explanation(developer_engine):
    result = developer_engine.format_explanation(
        "API", "An API defines interfaces for software communication.", ExplanationLevel.BEGINNER
    )
    assert "simple terms" in result.lower() or "think of" in result.lower()


def test_intermediate_explanation_passthrough(developer_engine):
    base = "An API defines interfaces for software communication."
    result = developer_engine.format_explanation("API", base, ExplanationLevel.INTERMEDIATE)
    assert result == base


def test_advanced_explanation(developer_engine):
    result = developer_engine.format_explanation(
        "API", "APIs provide abstraction layers.", ExplanationLevel.ADVANCED
    )
    assert "engineering" in result.lower() or "architecture" in result.lower() or "systems" in result.lower()


def test_expert_explanation(developer_engine):
    result = developer_engine.format_explanation(
        "API", "APIs abstract communication.", ExplanationLevel.EXPERT
    )
    assert "memory" in result.lower() or "concurrency" in result.lower() or "systems" in result.lower()


def test_simplify_text_strips_jargon(developer_engine):
    raw = "Asynchronous microservices handle distributed polymorphism determinism concurrency."
    simplified = developer_engine._simplify_text(raw)
    assert "asynchronous" not in simplified.lower()
    assert "polymorphism" not in simplified.lower()
