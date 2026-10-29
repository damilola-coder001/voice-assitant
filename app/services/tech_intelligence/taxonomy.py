import enum
from typing import Dict, List, Set

class TechDomain(str, enum.Enum):
    AI_ML = "ai_ml"
    SOFTWARE_DEV = "software_dev"
    CYBERSECURITY = "cybersecurity"
    HARDWARE = "hardware"
    STARTUPS_BUSINESS = "startups_business"
    EMERGING_TECH = "emerging_tech"

DOMAIN_LABELS: Dict[TechDomain, str] = {
    TechDomain.AI_ML: "AI & Machine Learning",
    TechDomain.SOFTWARE_DEV: "Software & Development",
    TechDomain.CYBERSECURITY: "Cybersecurity",
    TechDomain.HARDWARE: "Hardware & Semiconductors",
    TechDomain.STARTUPS_BUSINESS: "Startups & Tech Business",
    TechDomain.EMERGING_TECH: "Emerging Technologies",
}

DOMAIN_EMOJIS: Dict[TechDomain, str] = {
    TechDomain.AI_ML: "",
    TechDomain.SOFTWARE_DEV: "",
    TechDomain.CYBERSECURITY: "",
    TechDomain.HARDWARE: "",
    TechDomain.STARTUPS_BUSINESS: "",
    TechDomain.EMERGING_TECH: "",
}

class ExplanationLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

class TechIntent(str, enum.Enum):
    CURRENT_NEWS = "CURRENT_NEWS"
    REALTIME_NEWS = "CURRENT_NEWS"
    TECH_EXPLANATION = "TECH_EXPLANATION"
    PRODUCT_RESEARCH = "PRODUCT_RESEARCH"
    COMPANY_RESEARCH = "COMPANY_RESEARCH"
    DEVELOPER_RESEARCH = "DEVELOPER_RESEARCH"
    SECURITY_RESEARCH = "SECURITY_RESEARCH"
    COMPARISON = "COMPARISON"
    TUTORIAL = "TUTORIAL"
    TECH_BRIEFING = "TECH_BRIEFING"
    TREND_ANALYSIS = "TREND_ANALYSIS"
    FACT_CHECK = "FACT_CHECK"
    GENERAL_TECH = "GENERAL_TECH"

QueryIntent = TechIntent


class VerificationVerdict(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY_TRUE = "LIKELY TRUE"
    PARTIALLY_TRUE = "PARTIALLY TRUE"
    UNVERIFIED = "UNVERIFIED"
    DISPUTED = "DISPUTED"
    FALSE = "FALSE"

# Source Reliability Tiers per Master PDR Section 12 & 13
# 1 = Highest (Official announcements, docs), 7 = Lowest (Social media)
SOURCE_RELIABILITY_TIERS = {
    "official_docs": 1,
    "security_advisories": 1,
    "academic_research": 2,
    "established_tech_media": 3,
    "reputable_journalism": 3,
    "developer_community": 4,
    "community_forums": 5,
    "social_media": 6,
    "unverified": 7,
}

# Domain authority mapping for automated credibility scoring
AUTHORITATIVE_DOMAINS: Dict[str, Dict[str, any]] = {
    # Official / Documentation
    "openai.com": {"tier": 1, "type": "official_docs", "name": "OpenAI Official"},
    "anthropic.com": {"tier": 1, "type": "official_docs", "name": "Anthropic Official"},
    "deepmind.google": {"tier": 1, "type": "official_docs", "name": "Google DeepMind"},
    "blog.google": {"tier": 1, "type": "official_docs", "name": "Google Official"},
    "ai.meta.com": {"tier": 1, "type": "official_docs", "name": "Meta AI"},
    "microsoft.com": {"tier": 1, "type": "official_docs", "name": "Microsoft Official"},
    "blogs.microsoft.com": {"tier": 1, "type": "official_docs", "name": "Microsoft Blog"},
    "nvidia.com": {"tier": 1, "type": "official_docs", "name": "NVIDIA Official"},
    "nvidianews.nvidia.com": {"tier": 1, "type": "official_docs", "name": "NVIDIA Newsroom"},
    "apple.com": {"tier": 1, "type": "official_docs", "name": "Apple Newsroom"},
    "github.com": {"tier": 1, "type": "official_docs", "name": "GitHub Releases & Docs"},
    "docs.python.org": {"tier": 1, "type": "official_docs", "name": "Python Software Foundation"},
    "python.org": {"tier": 1, "type": "official_docs", "name": "Python Foundation"},
    "fastapi.tiangolo.com": {"tier": 1, "type": "official_docs", "name": "FastAPI Documentation"},
    "rust-lang.org": {"tier": 1, "type": "official_docs", "name": "Rust Language Official"},
    "go.dev": {"tier": 1, "type": "official_docs", "name": "Go Dev Official"},
    "nodejs.org": {"tier": 1, "type": "official_docs", "name": "Node.js Official"},
    "react.dev": {"tier": 1, "type": "official_docs", "name": "React Official Docs"},
    "nextjs.org": {"tier": 1, "type": "official_docs", "name": "Next.js Official"},

    # Security Advisories & Government
    "cisa.gov": {"tier": 1, "type": "security_advisories", "name": "CISA Cybersecurity Advisories"},
    "nvd.nist.gov": {"tier": 1, "type": "security_advisories", "name": "NIST National Vulnerability Database"},
    "cve.org": {"tier": 1, "type": "security_advisories", "name": "CVE Organization"},
    "krebsonsecurity.com": {"tier": 2, "type": "reputable_journalism", "name": "Krebs on Security"},
    "bleepingcomputer.com": {"tier": 2, "type": "established_tech_media", "name": "BleepingComputer"},
    "thehackernews.com": {"tier": 2, "type": "established_tech_media", "name": "The Hacker News"},
    "darkreading.com": {"tier": 2, "type": "established_tech_media", "name": "Dark Reading"},

    # Academic & Research
    "arxiv.org": {"tier": 2, "type": "academic_research", "name": "arXiv Preprints"},
    "paperswithcode.com": {"tier": 2, "type": "academic_research", "name": "Papers with Code"},
    "nature.com": {"tier": 2, "type": "academic_research", "name": "Nature"},
    "science.org": {"tier": 2, "type": "academic_research", "name": "Science"},

    # Established Tech Journalism
    "arstechnica.com": {"tier": 3, "type": "established_tech_media", "name": "Ars Technica"},
    "theverge.com": {"tier": 3, "type": "established_tech_media", "name": "The Verge"},
    "techcrunch.com": {"tier": 3, "type": "established_tech_media", "name": "TechCrunch"},
    "wired.com": {"tier": 3, "type": "established_tech_media", "name": "Wired"},
    "anandtech.com": {"tier": 3, "type": "established_tech_media", "name": "AnandTech"},
    "tomshardware.com": {"tier": 3, "type": "established_tech_media", "name": "Tom's Hardware"},
    "semianalysis.com": {"tier": 3, "type": "established_tech_media", "name": "SemiAnalysis"},
    "venturebeat.com": {"tier": 3, "type": "established_tech_media", "name": "VentureBeat"},
    "zdnet.com": {"tier": 3, "type": "established_tech_media", "name": "ZDNet"},
    "theregister.com": {"tier": 3, "type": "established_tech_media", "name": "The Register"},
    "reuters.com": {"tier": 3, "type": "reputable_journalism", "name": "Reuters Tech"},
    "bloomberg.com": {"tier": 3, "type": "reputable_journalism", "name": "Bloomberg Technology"},
    "wsj.com": {"tier": 3, "type": "reputable_journalism", "name": "Wall Street Journal Tech"},

    # Developer Community
    "news.ycombinator.com": {"tier": 4, "type": "developer_community", "name": "Hacker News"},
    "stackoverflow.com": {"tier": 4, "type": "developer_community", "name": "Stack Overflow"},
    "dev.to": {"tier": 4, "type": "developer_community", "name": "DEV Community"},
    "medium.com": {"tier": 5, "type": "community_forums", "name": "Medium Tech"},
    "reddit.com": {"tier": 5, "type": "community_forums", "name": "Reddit Discussion"},
    "twitter.com": {"tier": 6, "type": "social_media", "name": "X / Twitter"},
    "x.com": {"tier": 6, "type": "social_media", "name": "X (formerly Twitter)"},
}

# Domain keyword markers for intent and taxonomy mapping
DOMAIN_KEYWORDS: Dict[TechDomain, Set[str]] = {
    TechDomain.AI_ML: {
        "ai", "artificial intelligence", "machine learning", "deep learning", "llm", "large language model",
        "generative ai", "gpt", "claude", "gemini", "openai", "anthropic", "mistral", "deepmind",
        "llama", "transformer", "diffusion", "rag", "fine-tuning", "weights", "neural network",
        "agent", "ai agent", "autonomous agent", "copilot", "chatgpt", "perplexity", "reasoning model",
        "synthetic data", "embeddings", "vector database", "hugging face", "benchmark", "mmu",
    },
    TechDomain.SOFTWARE_DEV: {
        "software", "software engineering", "programming", "coding", "developer", "development",
        "best practices", "clean code", "design patterns", "architecture", "software architecture",
        "python", "javascript", "typescript", "rust", "golang", "go language", "c++", "c#", "java", "php",
        "react", "next.js", "vue", "angular", "fastapi", "django", "laravel", "node.js", "express",
        "api", "rest api", "graphql", "grpc", "git", "github", "gitlab", "docker", "kubernetes", "k8s",
        "ci/cd", "devops", "linux", "cloud", "aws", "azure", "gcp", "database", "postgres", "postgresql",
        "mysql", "sqlite", "redis", "mongodb", "open source", "compiler", "framework", "library",
        "backend", "frontend", "fullstack", "microservices", "refactoring", "syntax", "sdk",
    },
    TechDomain.CYBERSECURITY: {
        "cybersecurity", "security", "vulnerability", "cve", "zero-day", "0-day", "exploit", "breach",
        "data breach", "malware", "ransomware", "phishing", "ddos", "firewall", "encryption",
        "cisa", "advisory", "patch", "payload", "penetration testing", "red team", "blue team",
        "infosec", "soc", "authentication", "oauth", "jwt", "mfa", "zero trust", "supply chain attack",
        "backdoor", "trojan", "spyware", "threat actor", "apt", "botnet",
    },
    TechDomain.HARDWARE: {
        "hardware", "cpu", "gpu", "chip", "semiconductor", "processor", "nvidia", "amd", "intel",
        "qualcomm", "apple silicon", "m3", "m4", "blackwell", "h100", "b200", "rtx", "ryzen",
        "tsmc", "fab", "wafer", "nanometer", "smartphone", "laptop", "server", "data center",
        "networking", "ram", "ddr5", "ssd", "nvme", "pcie", "arm", "risc-v", "silicon",
    },
    TechDomain.STARTUPS_BUSINESS: {
        "startup", "startups", "funding", "seed round", "series a", "series b", "series c", "venture capital",
        "vc", "acquisition", "acquired", "merger", "ipo", "valuation", "unicorn", "y combinator",
        "tech business", "revenue", "layoffs", "hiring", "antitrust", "ftc", "sec", "regulation",
        "ceo", "founder", "strategy", "monetization", "saas",
    },
    TechDomain.EMERGING_TECH: {
        "quantum computing", "quantum", "qubit", "robotics", "humanoid robot", "autonomous vehicle",
        "self-driving", "waymo", "tesla fsd", "ar", "augmented reality", "vr", "virtual reality",
        "spatial computing", "vision pro", "biotech", "synthetic biology", "crispr", "brain-computer interface",
        "neuralink", "fusion energy", "advanced computing", "iot", "smart grid", "edge computing",
    },
}
