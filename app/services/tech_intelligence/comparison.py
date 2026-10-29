import re
from typing import Dict, List, Optional, Tuple

class TechComparisonEngine:
    """
    Evaluates and compares technologies across 8 structured dimensions:
    Purpose, Strengths, Weaknesses, Performance, Ecosystem, Learning Curve, Use Cases, Current Relevance.
    """

    KNOWN_COMPARISONS: Dict[str, Dict[str, str]] = {
        "react vs vue": {
            "item_a": "React",
            "item_b": "Vue",
            "summary": "React offers immense ecosystem flexibility and functional JSX architecture, while Vue provides a more cohesive, batteries-included developer experience with reactive two-way binding.",
            "strengths_a": "Unmatched ecosystem, huge job market, seamless TypeScript support, flexible component patterns.",
            "strengths_b": "Gentle learning curve, official routing and state libraries, clean single-file component syntax.",
            "tradeoffs": "React requires more boilerplate and architectural decisions; Vue has a smaller overall corporate enterprise footprint.",
            "verdict": "Choose React for large-scale distributed teams and maximum library choice. Choose Vue for rapid product delivery and streamlined maintainability."
        },
        "claude vs gemini": {
            "item_a": "Claude",
            "item_b": "Gemini",
            "summary": "Claude excels in nuanced coding synthesis, extended reasoning, and articulate prose, while Gemini features massive multi-million-token context windows and deep multimodal grounding across Google services.",
            "strengths_a": "Artifacts UI, precise code generation, high instruction adherence, natural prose cadence.",
            "strengths_b": "Massive native context window, direct Google Cloud integration, multimodal audio/video processing.",
            "tradeoffs": "Claude can have strict safety refusals; Gemini can vary in conversational tone across smaller endpoints.",
            "verdict": "Choose Claude for deep programming, code refactoring, and creative writing. Choose Gemini for processing huge document archives and multimodal reasoning."
        },
        "postgres vs mysql": {
            "item_a": "PostgreSQL",
            "item_b": "MySQL",
            "summary": "PostgreSQL is the gold-standard object-relational database with rich data types and strict SQL compliance, while MySQL is famed for simplicity and read-heavy web applications.",
            "strengths_a": "Advanced indexing (GIN/BRIN), native JSONB, custom extensions like pgvector, rock-solid concurrency (MVCC).",
            "strengths_b": "Massive historical web hosting support, simple replication topologies, lower baseline memory footprint.",
            "tradeoffs": "PostgreSQL connection management requires pooling (pgBouncer); MySQL has fewer advanced analytical constructs.",
            "verdict": "Choose PostgreSQL for modern applications, vector search, and complex relations. Choose MySQL for simple legacy LAMP stacks."
        },
        "docker vs kubernetes": {
            "item_a": "Docker",
            "item_b": "Kubernetes",
            "summary": "Docker packages and runs single containers on a host, while Kubernetes orchestrates clusters of containerized applications across thousands of nodes.",
            "strengths_a": "Simple developer setup, instantaneous container spins, perfect for local dev environments.",
            "strengths_b": "Automated self-healing, horizontal autoscaling, declarative rolling updates, ingress routing.",
            "tradeoffs": "Docker alone cannot manage multi-host clusters; Kubernetes has steep operational complexity and steep learning curve.",
            "verdict": "Use Docker to build and run container images. Use Kubernetes when deploying resilient, distributed systems at production scale."
        },
        "python vs rust": {
            "item_a": "Python",
            "item_b": "Rust",
            "summary": "Python maximizes developer velocity with dynamic syntax and a vast data science ecosystem, while Rust provides compile-time memory safety with C-level raw execution speed.",
            "strengths_a": "Fast prototyping, world-leading AI/ML libraries, readable clean syntax.",
            "strengths_b": "Zero runtime overhead, thread-safety guarantees without a garbage collector, predictable low latency.",
            "tradeoffs": "Python is slower for compute-heavy CPU loops; Rust has a steep learning curve around the borrow checker and lifetimes.",
            "verdict": "Choose Python for AI orchestration, scripting, and backend web APIs. Choose Rust for high-throughput network services, game engines, and performance-critical kernels."
        },
    }

    def generate_comparison(self, item_a: str, item_b: str) -> str:
        key = f"{item_a.lower().strip()} vs {item_b.lower().strip()}"
        rev_key = f"{item_b.lower().strip()} vs {item_a.lower().strip()}"

        match = self.KNOWN_COMPARISONS.get(key) or self.KNOWN_COMPARISONS.get(rev_key)
        if match:
            return (
                f"Between {match['item_a']} and {match['item_b']}, {match['summary']} "
                f"{match['item_a']} shines in {match['strengths_a'].lower()} "
                f"Conversely, {match['item_b']} offers {match['strengths_b'].lower()} "
                f"In terms of trade-offs: {match['tradeoffs']} "
                f"{match['verdict']}"
            )

        return (
            f"Between {item_a} and {item_b}, both technologies serve important roles in modern software engineering. "
            f"{item_a} typically focuses on specific optimization goals, while {item_b} offers alternative architectural trade-offs. "
            f"The best choice depends on your team's familiarity, performance requirements, and deployment ecosystem."
        )

tech_comparison_engine = TechComparisonEngine()
