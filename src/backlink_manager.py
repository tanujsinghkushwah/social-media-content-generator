"""Platform-aware backlink injection using a Firebase RTDB counter.

Counter path: social_gen/backlink_counter/{platform} (integer)
Bucket sizes: X→7 (~15%), LinkedIn→4 (~25%), Instagram→never in caption.

On each call, the counter is atomically incremented. When counter % bucket_size == 0
the function returns the appropriate URL for that pillar/topic; otherwise None.
"""

import re
from typing import Optional

from firebase_admin import db

_COUNTER_PATH = "social_gen/backlink_counter"

# Pillar-to-URL map — real pages from interviewgenie.net sitemap
PILLAR_TO_URL: dict[str, str] = {
    "anti_grind_contrarian":       "https://interviewgenie.net/question-bank.html",
    "behavioral_round_save":       "https://interviewgenie.net/tutorials.html",
    "system_design_demystified":   "https://interviewgenie.net/question-bank/backend.html",
    "hiring_market_reality":       "https://interviewgenie.net/",
    "interview_horror_recovery":   "https://interviewgenie.net/tutorials.html",
    "salary_negotiation":          "https://interviewgenie.net/",
    "interview_day_tactics":       "https://interviewgenie.net/tutorials.html",
    "tool_reveal":                 "https://interviewgenie.net/",
}

# Trend-keyword overrides — if the trend title matches, use a specialty page instead
_TOPIC_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bfrontend\b|\breact\b|\bvue\b|\bnext\.?js\b", re.I),
     "https://interviewgenie.net/question-bank/frontend.html"),
    (re.compile(r"\bbackend\b|\bnode\b|\bspring\b|\bdjango\b|\bapi\b", re.I),
     "https://interviewgenie.net/question-bank/backend.html"),
    (re.compile(r"\bdevops\b|\bkubernetes\b|\bdocker\b|\bci.?cd\b|\bterraform\b", re.I),
     "https://interviewgenie.net/question-bank/devops.html"),
    (re.compile(r"\bmachine.?learning\b|\b\bml\b|\bai model\b|\bdeep.?learning\b|\bllm\b", re.I),
     "https://interviewgenie.net/question-bank/machine-learning.html"),
]

# Posts-per-link bucket sizes per platform (deterministic ~rate control)
_BUCKET: dict[str, int] = {
    "x":        7,   # ~15% of posts get a link
    "linkedin": 4,   # ~25% of posts get a link
}


class BacklinkManager:
    """Manages deterministic backlink injection rates via RTDB counters."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.enabled = bool(db_url)
        if not self.enabled:
            print("BacklinkManager: no DB URL — backlinks disabled.")

    def _ref(self, path: str):
        return db.reference(path, url=self.db_url)

    def _increment_and_get(self, platform: str) -> int:
        """Atomically increment the counter and return the new value."""
        result = {"value": 1}

        def _txn(current):
            new_val = (current or 0) + 1
            result["value"] = new_val
            return new_val

        self._ref(f"{_COUNTER_PATH}/{platform}").transaction(_txn)
        return result["value"]

    def _resolve_url(self, pillar: str, trend_title: str) -> str:
        """Return the best URL for this pillar + trend combination."""
        for pattern, url in _TOPIC_KEYWORDS:
            if pattern.search(trend_title):
                return url
        return PILLAR_TO_URL.get(pillar, "https://interviewgenie.net/")

    def should_include_backlink(
        self, platform: str, pillar: str, trend_title: str
    ) -> Optional[str]:
        """Return a URL if this post should carry a backlink, else None.

        Instagram always returns None — links aren't clickable in IG captions.
        """
        if platform == "instagram":
            return None
        if platform not in _BUCKET:
            return None
        if not self.enabled:
            return None
        try:
            count = self._increment_and_get(platform)
            if count % _BUCKET[platform] == 0:
                return self._resolve_url(pillar, trend_title)
            return None
        except Exception as e:
            print(f"BacklinkManager.should_include_backlink failed (non-fatal): {e}")
            return None
