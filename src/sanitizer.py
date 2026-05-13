"""Post-generation sanitizers for social content.

- Strip markdown that doesn't render on IG/X (bold asterisks, emoji-bullet headers).
- Validate hashtags against a whitelist to catch LLM-hallucinated typos and casing drift.
"""

import re
from typing import Iterable

# 14 platform-approved hashtags + branded tag. Lowercase, single canonical casing.
HASHTAG_WHITELIST = {
    "#techinterview", "#leetcode", "#faang", "#softwareengineer",
    "#codinginterview", "#systemdesign", "#techjobs", "#careeradvice",
    "#interviewprep", "#h1b", "#layoffrecovery", "#newgrad", "#swe",
    "#jobsearch",
    "#softwareengineering", "#techcareers",
    "#interviewgenie",  # branded
}

_BOLD_PAT = re.compile(r"\*\*(.+?)\*\*")
_EMOJI_BULLET_HEADER_PAT = re.compile(
    r"^[\s]*[🔹🔑▶️💡🔥⚡✨🎯•▪►‣◆◇][\s]*\*?\*?([A-Z][^:\n]{0,40}):\*?\*?",
    re.MULTILINE,
)
_BARE_LABEL_PAT = re.compile(
    r"^(?:🔑\s*|💡\s*|▶️\s*|🔥\s*)?(Insight|Tactical steps?|Key insight|Pro tip|Key takeaway)\s*:\s*",
    re.MULTILINE | re.IGNORECASE,
)
_HASHTAG_PAT = re.compile(r"#[A-Za-z0-9_]+")


def strip_markdown(text: str) -> str:
    """Strip markdown bold and AI-formulaic emoji-headers that render as literal characters on IG/X."""
    if not text:
        return text
    # Unwrap **bold** → bold
    text = _BOLD_PAT.sub(r"\1", text)
    # Drop "🔑 Insight:" / "💡 Tactical steps:" style labels at start of lines
    text = _BARE_LABEL_PAT.sub("", text)
    # Strip emoji + capitalized-header + colon at line start (e.g. "🔹 Header:")
    text = _EMOJI_BULLET_HEADER_PAT.sub(r"\1 —", text)
    return text


def validate_hashtags(text: str, whitelist: Iterable[str] = HASHTAG_WHITELIST) -> str:
    """Drop hashtags that aren't in the whitelist. Normalize casing.

    LLM occasionally emits `#careeradvic` (typo) or `#CareerAdvice` (case drift) —
    both break discoverability. We replace each tag with its whitelist-canonical
    form if present, else drop it.
    """
    if not text:
        return text
    canonical = {tag.lower(): tag for tag in whitelist}

    def _replace(match):
        raw = match.group(0)
        if raw.lower() in canonical:
            return canonical[raw.lower()]
        return ""  # drop unknown tag

    cleaned = _HASHTAG_PAT.sub(_replace, text)
    # Collapse any double-spaces introduced by drops
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    # Trim trailing space on each line
    cleaned = re.sub(r"[ \t]+$", "", cleaned, flags=re.MULTILINE)
    return cleaned


def sanitize_for_platform(text: str, platform: str) -> str:
    """Full sanitize pipeline by platform."""
    if not text:
        return text
    cleaned = strip_markdown(text)
    if platform in ("instagram", "linkedin"):
        cleaned = validate_hashtags(cleaned)
    elif platform == "x":
        # X posts shouldn't have hashtags at all (per existing prompt rule)
        cleaned = _HASHTAG_PAT.sub("", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned.strip()
