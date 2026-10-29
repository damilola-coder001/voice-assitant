import logging
import re
from typing import Any

# Regex patterns for sensitive credentials
PATTERNS = [
    (re.compile(r"sk_[a-zA-Z0-9_-]{8,}", re.IGNORECASE), "sk_***"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9._-]+", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"(password['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1***\2"),
    (re.compile(r"(authorization['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1***\2"),
    (re.compile(r"(access_token['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1***\2"),
    (re.compile(r"(refresh_token['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1***\2"),
    (re.compile(r"(postgres(?:ql)?://[^:]+:)[^@]+(@)", re.IGNORECASE), r"\1***\2"),
    (re.compile(r"(redis(?:s)?://[^:]+:)[^@]+(@)", re.IGNORECASE), r"\1***\2"),
]

def sanitize_string(text: str) -> str:
    """Scrub sensitive keys, passwords, and tokens from log messages."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern, replacement in PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized

class SensitiveDataFilter(logging.Filter):
    """
    Defensive logging filter ensuring secrets, authorization headers,
    passwords, and API keys are never written to log files or standard output.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_string(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: sanitize_string(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(sanitize_string(v) if isinstance(v, str) else v for v in record.args)

        return True
