#!/usr/bin/env python3
"""
Automated Secret Scanner
Scans files in the repository for leaked API keys, tokens, passwords, and private keys.
Exits with code 0 if no secrets found, or code 1 if suspicious patterns are detected.
"""

import os
import re
import sys
from pathlib import Path

# Directories and files explicitly excluded from scanning
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "audio_cache",
}

EXCLUDED_FILES = {
    ".env",            # Local server environment (must be gitignored)
    ".env.local",
    "voice_assistant.db",
    "voice_assistant.db-journal",
}

# Regex patterns for sensitive credentials
SECRET_PATTERNS = [
    # Elevenlabs API key pattern (sk_ followed by hex chars)
    (re.compile(r"""(?i)(?:elevenlabs[_-]?api[_-]?key|xi-api-key|elevenlabs[_-]?key)\s*[:=]\s*['"]([a-zA-Z0-9_-]{20,})['"]"""), "ElevenLabs API Key Assignment"),
    (re.compile(r"""\bsk_[0-9a-fA-F]{32,64}\b"""), "ElevenLabs/OpenAI style Secret Key (sk_...)"),
    # Generic API Keys
    (re.compile(r"""(?i)(?:api[_-]?key|secret[_-]?key|auth[_-]?token|bearer[_-]?token)\s*[:=]\s*['"]([a-zA-Z0-9_\-\.]{24,})['"]"""), "Generic Secret/API Key"),
    # Private keys
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "Private Key Header"),
    # AWS Access Key ID & Secret
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS Access Key ID"),
    # GitHub personal access tokens
    (re.compile(r"\bgh[pousr]_[0-9a-zA-Z]{36}\b"), "GitHub Personal Access Token"),
    # Hardcoded passwords in code (excluding dummy example values)
    (re.compile(r"""(?i)(?:password|passwd|pwd)\s*[:=]\s*['"](?!change|dummy|test|example|password|\$)[a-zA-Z0-9!@#$%^&*()_+]{8,}['"]"""), "Hardcoded Password Assignment"),
]

# Patterns that indicate safe placeholder values (allowed in tests/examples)
SAFE_PLACEHOLDERS = [
    "your_elevenlabs_api_key_here",
    "generate_a_secure_random_64_character_hex_key_here_for_production",
    "ChangeThisPasswordInProduction!123",
    "test_secret_key_for_testing_purposes_only_do_not_use_in_production",
    "test_jwt_secret_key_12345678901234567890123456789012",
    "sk_dummy_test_key_for_unit_tests",
    "mock_token",
]

def is_safe_placeholder(text: str) -> bool:
    for placeholder in SAFE_PLACEHOLDERS:
        if placeholder in text:
            return True
    return False

def scan_file(file_path: Path) -> list[tuple[int, str, str]]:
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    # Ignore .env.example if it contains safe templates
    if file_path.name == ".env.example":
        return findings

    lines = content.splitlines()
    for line_num, line in enumerate(lines, start=1):
        if is_safe_placeholder(line):
            continue

        for pattern, label in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                # Extra sanity check: check if it's an env var lookup e.g. os.getenv(...)
                if "os.getenv" in line or "os.environ" in line or "Settings" in line:
                    continue
                # Mask matched string
                matched_str = match.group(0)
                masked = matched_str[:8] + "..." + matched_str[-4:] if len(matched_str) > 12 else "***"
                findings.append((line_num, label, masked))
    return findings

def scan_directory(root_dir: Path) -> int:
    print(f"[*] Scanning directory for leaked secrets: {root_dir}")
    total_findings = 0
    scanned_count = 0

    for root, dirs, files in os.walk(root_dir):
        # Exclude directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

        for file in files:
            if file in EXCLUDED_FILES or file.endswith(".pyc"):
                continue
            file_path = Path(root) / file
            scanned_count += 1
            findings = scan_file(file_path)
            if findings:
                total_findings += len(findings)
                rel_path = file_path.relative_to(root_dir)
                print(f"\n[!] ALERT: Potential secret(s) found in {rel_path}:")
                for line_num, label, snippet in findings:
                    print(f"    Line {line_num}: [{label}] -> {snippet}")

    print(f"\n[+] Scan complete: {scanned_count} files checked.")
    if total_findings > 0:
        print(f"[!] FAILED: {total_findings} potential secret(s) detected! Review above alerts.")
        return 1
    else:
        print("[OK] PASSED: No leaked secrets detected.")
        return 0

if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    sys.exit(scan_directory(target))
