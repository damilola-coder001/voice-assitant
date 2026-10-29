import html
import re
from typing import Optional


def clean_news_headline(text: Optional[str]) -> str:
    """
    Cleans headlines so they sound conversational, direct, and human.
    Strips robotic media metadata, trailing outlet tags, and wire ticker artifacts.

    Examples:
      - "OpenAI proposes global standards, RSI — reported by CNBC" -> "OpenAI proposes global standards"
      - "Calls to slow AI spark new frontier - Al Jazeera" -> "Calls to slow AI spark new frontier"
      - "money.usnews.com: Tech Stocks Rally" -> "Tech Stocks Rally"
    """
    if not text:
        return ""

    cleaned = html.unescape(str(text)).strip()
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)

    # Normalize typographical curly quotes, apostrophes, and non-breaking spaces
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"[\u2018\u2019\u201a\u201b`´]", "'", cleaned)
    cleaned = re.sub(r"[\u201c\u201d\u201e\u201f«»]", '"', cleaned)

    # Repair Unicode replacement character (\ufffd) and corrupt apostrophes/quotes
    cleaned = re.sub(r"(\w)\ufffd(\w)", r"\1'\2", cleaned)
    cleaned = re.sub(r"\ufffd([a-zA-Z0-9])", r"'\1", cleaned)
    cleaned = re.sub(r"([a-zA-Z0-9])\ufffd", r"\1'", cleaned)
    cleaned = cleaned.replace("\ufffd", "")

    # Strip issue/show prefixes like "This week on Tom's Hardware...: " or "Today on TechCrunch: "
    cleaned = re.sub(r"(?i)^(this\s+week\s+on|today\s+on|latest\s+from)\s+[^:–—]+[:–—]\s*", "", cleaned)

    # Strip phrases like "According to reports from XYZ, " or "According to CNBC, "
    cleaned = re.sub(r"(?i)\baccording\s+to\s+(reports\s+from\s+)?[a-zA-Z0-9\s\.\-&]+,\s*", "", cleaned)

    # Strip inline or trailing 'reported by ...'
    cleaned = re.sub(r"(?i)\s*[—–-]\s*reported\s+by\s+.*$", "", cleaned)
    cleaned = re.sub(r"(?i)\s*,\s*reported\s+by\s+.*$", "", cleaned)
    cleaned = re.sub(r"(?i)\s*\(reported\s+by\s+.*?\)", "", cleaned)

    # Strip trailing publisher dashes like " - CNBC", " — Reuters", " | TechCrunch", " - Al Jazeera"
    cleaned = re.sub(r"\s*[—–|\-]\s*[A-Z][A-Za-z0-9\s\.,&]+$", "", cleaned)

    # Strip news agency tickers/tags like ", RSI", ", AP", "(Reuters) - ", "UPDATE 1-", "BREAKING:"
    cleaned = re.sub(r"(?i)^(breaking[:\s]+|update\s*\d*[-:]\s*|exclusive[-:]\s*)", "", cleaned)
    cleaned = re.sub(r"(?i)\s*,\s*(rsi|ap|reuters|afp|bloomberg)\b", "", cleaned)
    cleaned = re.sub(r"(?i)^\([a-z\s]+\)\s*[-—]\s*", "", cleaned)

    # Strip raw web domain mentions like "money.usnews.com", "nytimes.com", etc.
    cleaned = re.sub(r"\b[a-zA-Z0-9\-\.]+\.(com|org|net|edu|gov|io|co|ai)\b", "", cleaned)

    # Normalize punctuation and whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.rstrip(",;:-— ")
    return cleaned


def clean_news_snippet(snippet: Optional[str], title: str = "") -> str:
    """
    Cleans snippets to extract informative sentences without repetitive titles
    or outlet citations.
    """
    if not snippet:
        return ""

    cleaned = html.unescape(str(snippet)).strip()
    cleaned = re.sub(r"<[^>]+>", "", cleaned)

    # Normalize typographical curly quotes, apostrophes, and non-breaking spaces
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"[\u2018\u2019\u201a\u201b`´]", "'", cleaned)
    cleaned = re.sub(r"[\u201c\u201d\u201e\u201f«»]", '"', cleaned)

    # Repair Unicode replacement character (\ufffd) and corrupt apostrophes/quotes
    cleaned = re.sub(r"(\w)\ufffd(\w)", r"\1'\2", cleaned)
    cleaned = re.sub(r"\ufffd([a-zA-Z0-9])", r"'\1", cleaned)
    cleaned = re.sub(r"([a-zA-Z0-9])\ufffd", r"\1'", cleaned)
    cleaned = cleaned.replace("\ufffd", "")

    # Strip meta citation filler
    cleaned = re.sub(r"(?i)\baccording\s+to\s+(reports\s+from\s+)?[a-zA-Z0-9\s\.\-&]+,\s*", "", cleaned)
    cleaned = re.sub(r"(?i)\s*[—–-]\s*reported\s+by\s+.*$", "", cleaned)
    cleaned = re.sub(r"(?i)\s*,\s*reported\s+by\s+.*$", "", cleaned)
    cleaned = re.sub(r"(?i)^latest\s+coverage\s+from\s+.*?on\s+", "", cleaned)
    cleaned = re.sub(r"(?i)^hacker\s+news\s+discussion\s*\(.*?\):\s*", "", cleaned)
    cleaned = re.sub(r"\b[a-zA-Z0-9\-\.]+\.(com|org|net|edu|gov|io|co|ai)\b", "", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # If the snippet is empty, merely repeats the title, or is too brief, return empty
    if title:
        norm_snip = re.sub(r"[^a-zA-Z0-9]", "", cleaned.lower())
        norm_title = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
        if (
            norm_snip == norm_title
            or (len(norm_title) > 20 and norm_snip.startswith(norm_title[:25]))
            or len(cleaned) < 15
        ):
            return ""

    return cleaned
