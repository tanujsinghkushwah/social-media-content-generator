"""Firebase RTDB-backed history of generated posts for dedup and in-context negatives.

Gracefully no-ops if the RTDB URL is not configured or the DB is unreachable,
so the pipeline never crashes on a fresh deployment that hasn't enabled RTDB yet.
"""

import re
import time
from datetime import datetime, timezone
from typing import List, Optional

from firebase_admin import db

POSTS_PATH = "social_gen/posts"
PERSONA_USAGE_PATH = "social_gen/persona_usage"


def _normalize(text: str) -> List[str]:
    """Lowercase, strip punctuation, return list of word tokens."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [w for w in text.split() if w]


def _shingles(tokens: List[str], n: int = 5) -> set:
    """Return set of n-gram word shingles."""
    if len(tokens) < n:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(a: str, b: str, n: int = 5) -> float:
    """Word-n-gram Jaccard similarity between two strings."""
    sa = _shingles(_normalize(a), n)
    sb = _shingles(_normalize(b), n)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class PostHistory:
    """RTDB-backed history. All methods tolerate DB failure and degrade safely."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.enabled = bool(db_url)
        if not self.enabled:
            print("PostHistory: no DB URL — history will not be persisted.")

    def _ref(self, path: str):
        return db.reference(path, url=self.db_url)

    def record_post(self, posts: dict, topic: str, pillar: str, persona: str) -> None:
        """Persist a generated post. posts = {x_post, instagram_post, linkedin_post}."""
        if not self.enabled:
            return
        try:
            key = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            entry = {
                "ts": int(time.time()),
                "topic": topic,
                "pillar": pillar,
                "persona": persona,
                "x_post": posts.get("x_post", ""),
                "instagram_post": posts.get("instagram_post", ""),
                "linkedin_post": posts.get("linkedin_post", ""),
            }
            self._ref(f"{POSTS_PATH}/{key}").set(entry)
            self._ref(f"{PERSONA_USAGE_PATH}/{persona}").transaction(
                lambda v: (v or 0) + 1
            )
        except Exception as e:
            print(f"PostHistory.record_post failed (non-fatal): {e}")

    def recent_posts(self, days: int = 30) -> List[dict]:
        """Return list of post entries from the last N days, oldest first."""
        if not self.enabled:
            return []
        try:
            cutoff = int(time.time()) - days * 86400
            raw = self._ref(POSTS_PATH).get()
            all_posts: dict = raw if isinstance(raw, dict) else {}
            entries = [v for v in all_posts.values() if isinstance(v, dict) and v.get("ts", 0) >= cutoff]
            return sorted(entries, key=lambda e: e.get("ts", 0))
        except Exception as e:
            print(f"PostHistory.recent_posts failed (non-fatal): {e}")
            return []

    def recent_openings(self, count: int = 8, days: int = 14) -> List[str]:
        """Return first 80 chars of the {count} most recent IG posts (proxy for opening)."""
        recent = self.recent_posts(days=days)
        openings = []
        for entry in reversed(recent):  # most recent first
            ig = entry.get("instagram_post", "")
            if ig:
                openings.append(ig[:80].strip())
            if len(openings) >= count:
                break
        return openings

    def is_too_similar(self, new_text: str, threshold: float = 0.7, days: int = 30) -> Optional[dict]:
        """Return the offending past entry if any post in last {days} exceeds Jaccard {threshold}.

        Compares against the Instagram column (longest text, best signal).
        """
        if not self.enabled or not new_text:
            return None
        for entry in self.recent_posts(days=days):
            past_ig = entry.get("instagram_post", "")
            if past_ig and jaccard(new_text, past_ig) >= threshold:
                return entry
        return None

    def persona_usage(self) -> dict:
        """Return {persona_name: count} of historical usage. Empty dict on failure."""
        if not self.enabled:
            return {}
        try:
            raw = self._ref(PERSONA_USAGE_PATH).get()
            return raw if isinstance(raw, dict) else {}
        except Exception as e:
            print(f"PostHistory.persona_usage failed (non-fatal): {e}")
            return {}
