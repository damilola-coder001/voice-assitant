import pytest
from app.services.tech_intelligence.classifier import TechClassifier, TechIntent
from app.services.tech_intelligence.taxonomy import TechDomain, ExplanationLevel

@pytest.fixture
def classifier():
    return TechClassifier()

def test_classify_all_intents(classifier):
    # 1. CURRENT_NEWS
    res = classifier.classify("What are the latest breaking tech news stories today?")
    assert res.intent in [TechIntent.CURRENT_NEWS, TechIntent.TECH_BRIEFING]
    assert res.requires_search is True

    # 2. TECH_EXPLANATION
    res = classifier.classify("What is an API?")
    assert res.intent == TechIntent.TECH_EXPLANATION
    assert res.requires_search is False

    # 3. PRODUCT_RESEARCH
    res = classifier.classify("What are the technical specs and benchmark performance of the M4 Max chip?")
    assert res.intent in [TechIntent.PRODUCT_RESEARCH, TechIntent.CURRENT_NEWS, TechIntent.DEVELOPER_RESEARCH]

    # 4. COMPANY_RESEARCH
    res = classifier.classify("What is Anthropic working on and what are their revenue figures?")
    assert res.intent in [TechIntent.COMPANY_RESEARCH, TechIntent.CURRENT_NEWS]

    # 5. DEVELOPER_RESEARCH
    res = classifier.classify("What is the difference in async syntax between Python 3.12 and 3.13?")
    assert res.intent in [TechIntent.DEVELOPER_RESEARCH, TechIntent.COMPARISON, TechIntent.TECH_EXPLANATION]

    # 6. SECURITY_RESEARCH
    res = classifier.classify("Is there a new zero day vulnerability or CVE advisory reported today?")
    assert res.intent in [TechIntent.SECURITY_RESEARCH, TechIntent.CURRENT_NEWS]
    assert res.primary_domain == TechDomain.CYBERSECURITY

    # 7. COMPARISON
    res = classifier.classify("Compare React vs Vue for building high performance dashboards")
    assert res.is_comparison is True
    assert res.intent == TechIntent.COMPARISON

    # 8. TUTORIAL
    res = classifier.classify("How to deploy a FastAPI service with Docker container step by step")
    assert res.intent in [TechIntent.TUTORIAL, TechIntent.DEVELOPER_RESEARCH]

    # 9. TECH_BRIEFING
    res = classifier.classify("Give me today's technology briefing")
    assert res.intent == TechIntent.TECH_BRIEFING
    assert res.requires_search is True

    # 10. TREND_ANALYSIS
    res = classifier.classify("What are the market adoption trends for humanoid robotics and embodied AI?")
    assert res.intent in [TechIntent.TREND_ANALYSIS, TechIntent.CURRENT_NEWS]

    # 11. FACT_CHECK
    res = classifier.classify("Is it confirmed that OpenAI released GPT-5 yesterday?")
    assert res.is_fact_check is True
    assert res.intent == TechIntent.FACT_CHECK

    # 12. GENERAL_TECH
    res = classifier.classify("Tell me about software engineering best practices")
    assert res.primary_domain == TechDomain.SOFTWARE_DEV

def test_time_sensitivity_detection(classifier):
    # Stable knowledge -> requires_search False
    res_stable = classifier.classify("What is a binary search tree?")
    assert res_stable.requires_search is False

    res_stable2 = classifier.classify("How does garbage collection work?")
    assert res_stable2.requires_search is False

    # Time-sensitive -> requires_search True
    res_fresh = classifier.classify("What new features were announced in Python recently?")
    assert res_fresh.requires_search is True

    res_fresh2 = classifier.classify("What happened with NVIDIA stock and earnings today?")
    assert res_fresh2.requires_search is True

def test_explanation_level_detection(classifier):
    # Explicit query overrides
    res_beg = classifier.classify("Explain neural networks like I'm five")
    assert res_beg.explanation_level == ExplanationLevel.BEGINNER

    res_adv = classifier.classify("Explain transformer attention like a software engineer")
    assert res_adv.explanation_level == ExplanationLevel.ADVANCED

    res_exp = classifier.classify("Explain memory allocation at expert level kernel internals")
    assert res_exp.explanation_level == ExplanationLevel.EXPERT

    # User preference fallback
    res_pref = classifier.classify("Explain database indexing", user_level_pref="expert")
    assert res_pref.explanation_level == ExplanationLevel.EXPERT

    res_default = classifier.classify("Explain database indexing")
    assert res_default.explanation_level == ExplanationLevel.INTERMEDIATE
