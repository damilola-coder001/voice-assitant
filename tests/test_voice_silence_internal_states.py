"""
Tests ensuring the voice assistant NEVER speaks or vocalizes internal processing states.
Validates that:
1. Status/processing text is cleanly sanitized before reaching TTS.
2. Developer engine, fact check, orchestrator, and comparison engines output direct spoken answers.
3. Errors produce natural conversational phrases, never technical/processing status messages.
"""

import pytest
from app.services.conversational import conversational_engine
from app.services.tech_intelligence.developer import tech_developer_engine
from app.services.tech_intelligence.taxonomy import ExplanationLevel, TechDomain
from app.services.tech_intelligence.fact_check import fact_checker, VerificationVerdict
from app.services.tech_intelligence.comparison import tech_comparison_engine
from app.services.tech_intelligence.orchestrator import tech_orchestrator


def test_sanitize_spoken_response_removes_processing_phrases():
    """Verify that processing phrases are stripped cleanly and response starts with actual answer."""
    test_cases = [
        ("Processing... The latest release introduces faster compilation.", "The latest release introduces faster compilation."),
        ("Processing your request: Python 3.14 includes tail call improvements.", "Python 3.14 includes tail call improvements."),
        ("I'm processing that... Here is the detail.", "Here is the detail."),
        ("I am processing your request. The server is running smoothly.", "The server is running smoothly."),
    ]
    for raw, expected in test_cases:
        sanitized = conversational_engine.sanitize_spoken_response(raw)
        assert sanitized == expected, f"Failed for raw: '{raw}', got: '{sanitized}'"


def test_sanitize_spoken_response_removes_thinking_and_reasoning_tags():
    """Verify that internal thinking words and <think> tags are never vocalized."""
    test_cases = [
        ("Let me think... The core concept is modularity.", "The core concept is modularity."),
        ("Thinking... Docker isolates processes using Linux namespaces and cgroups.", "Docker isolates processes using Linux namespaces and cgroups."),
        ("<think>User wants to know about APIs.</think> An API is an Application Programming Interface.", "An API is an Application Programming Interface."),
        ("[thinking] Analyzing algorithms... Sorting algorithms organize data efficiently.", "Sorting algorithms organize data efficiently."),
    ]
    for raw, expected in test_cases:
        sanitized = conversational_engine.sanitize_spoken_response(raw)
        assert sanitized == expected, f"Failed for raw: '{raw}', got: '{sanitized}'"


def test_sanitize_spoken_response_removes_searching_and_analyzing_preambles():
    """Verify that 'Searching...', 'Analyzing...', 'One moment...', 'Here is what I found' are removed."""
    test_cases = [
        ("Searching for that... There are three key updates today.", "There are three key updates today."),
        ("Let me search for that... Cloudflare announced workers AI integration.", "Cloudflare announced workers AI integration."),
        ("Analyzing the information: The architecture relies on event-driven queues.", "The architecture relies on event-driven queues."),
        ("One moment please... Kubernetes coordinates containerized services.", "Kubernetes coordinates containerized services."),
        ("Here is what I found: SQLite is a serverless, zero-configuration database.", "SQLite is a serverless, zero-configuration database."),
        ("Let me check that for you... Redis stores key-value pairs in memory.", "Redis stores key-value pairs in memory."),
    ]
    for raw, expected in test_cases:
        sanitized = conversational_engine.sanitize_spoken_response(raw)
        assert sanitized == expected, f"Failed for raw: '{raw}', got: '{sanitized}'"


def test_sanitize_spoken_response_removes_stacked_filler():
    """Verify that multiple stacked fillers are completely stripped down to the direct answer."""
    raw = "Thinking... Searching for that... Here is what I found: Rust provides memory safety without a garbage collector."
    sanitized = conversational_engine.sanitize_spoken_response(raw)
    assert sanitized == "Rust provides memory safety without a garbage collector."


def test_sanitize_spoken_response_replaces_technical_error_with_natural_phrase():
    """Verify that technical processing error strings are replaced with a natural spoken phrase."""
    error_texts = [
        "An error occurred while processing your request.",
        "An error occurred while processing your request",
        "An error occurred",
    ]
    expected_natural_phrase = "I couldn't get that information right now. Try again."
    for err in error_texts:
        assert conversational_engine.sanitize_spoken_response(err) == expected_natural_phrase


def test_sanitize_spoken_response_empty_or_only_status():
    """Verify that an empty response or one containing only status words falls back gracefully."""
    assert conversational_engine.sanitize_spoken_response("") == "I couldn't get that information right now. Try again."
    assert conversational_engine.sanitize_spoken_response("Thinking...") == "I couldn't get that information right now. Try again."
    assert conversational_engine.sanitize_spoken_response("Processing your request...") == "I couldn't get that information right now. Try again."


def test_developer_expert_explanation_never_vocalizes_analyzing():
    """Ensure expert-level technical explanation does not begin with 'Analyzing {topic}'."""
    formatted = tech_developer_engine.format_explanation(
        topic="PostgreSQL",
        base_explanation="It handles complex concurrency using multiversion concurrency control.",
        level=ExplanationLevel.EXPERT,
    )
    assert not formatted.lower().startswith("analyzing"), f"Should not start with 'Analyzing': {formatted}"
    assert "systems level" in formatted


def test_comparison_engine_never_vocalizes_comparing_preamble():
    """Ensure technology comparison does not begin with 'Comparing X and Y:'."""
    resp = tech_comparison_engine.generate_comparison("docker", "kubernetes")
    assert not resp.lower().startswith("comparing"), f"Should not start with 'Comparing': {resp}"
    assert "between docker and kubernetes" in resp.lower()


def test_fact_check_summary_never_vocalizes_i_searched():
    """Ensure fact check summary does not state 'I searched current technology sources'."""
    unverified_summary = fact_checker._generate_spoken_summary(
        claim="Quantum chips are in all smartphones",
        verdict=VerificationVerdict.UNVERIFIED,
        explanation="No records found.",
        has_primary=False,
    )
    assert "i looked into this" not in unverified_summary.lower()
    assert "i searched" not in unverified_summary.lower()


@pytest.mark.asyncio
async def test_orchestrator_stable_concept_direct_answer():
    """Verify stable technical concept query gives direct answer without filler."""
    resp = await tech_orchestrator.process_query(
        user_message="What is an API?",
        session_id=None,
        history=[],
    )
    sanitized = conversational_engine.sanitize_spoken_response(resp.spoken_response)
    forbidden_prefixes = ["processing", "thinking", "analyzing", "searching", "let me think", "one moment", "here is what i found"]
    for prefix in forbidden_prefixes:
        assert not sanitized.lower().startswith(prefix), f"Spoken response should not start with '{prefix}': {sanitized}"


def test_sanitize_spoken_response_removes_media_citations():
    """Verify that robotic media citation phrases are removed for natural human speech."""
    test_cases = [
        ("According to reports from Shoolini University, money.usnews.com OpenAI launches GPT-5.", "OpenAI launches GPT-5."),
        ("According to reports from Reuters, Anthropic released Claude 3.7.", "Anthropic released Claude 3.7."),
        ("According to official announcements from OpenAI, models will be updated.", "Models will be updated."),
        ("OpenAI proposes global AI standards, RSI — reported by CNBC", "OpenAI proposes global AI standards, RSI"),
    ]
    for raw, expected in test_cases:
        sanitized = conversational_engine.sanitize_spoken_response(raw)
        assert sanitized == expected, f"Failed for raw: '{raw}', got: '{sanitized}'"

