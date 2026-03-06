"""Fetch trending tech news using DuckDuckGo news search."""

import random
import re
from dataclasses import dataclass
from typing import List, Optional

from duckduckgo_search import DDGS

from src.constants import KEYWORDS

NEWS_QUERIES = [
    "software engineering AI tools launch",
    "developer tools framework release",
    "tech company engineering announcement",
    "machine learning research breakthrough",
    "cloud computing platform update",
    "open source project release",
    "programming language update release",
    "data engineering analytics news",
    "startup funding tech company",
    "software developer productivity tools",
]


@dataclass
class TrendItem:
    """A trending news item with full context."""
    title: str
    body: str
    url: str
    source: str

    def __str__(self) -> str:
        return f"{self.title} ({self.source})"


class TrendFetcher:
    """Fetch trending tech news from DuckDuckGo news search."""

    def __init__(self):
        """Initialize the trend fetcher."""
        self.ddgs = DDGS()

    def _normalize_title(self, title: str) -> str:
        """Normalize title for deduplication."""
        title = title.lower()
        title = re.sub(r"[^\w\s]", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        return title

    def _is_duplicate(self, new_title: str, existing_titles: List[str]) -> bool:
        """Check if a title is a near-duplicate of existing titles."""
        normalized_new = self._normalize_title(new_title)
        for existing in existing_titles:
            normalized_existing = self._normalize_title(existing)
            if normalized_new in normalized_existing or normalized_existing in normalized_new:
                return True
            words_new = set(normalized_new.split())
            words_existing = set(normalized_existing.split())
            if len(words_new) > 3 and len(words_existing) > 3:
                overlap = len(words_new & words_existing) / min(len(words_new), len(words_existing))
                if overlap > 0.6:
                    return True
        return False

    def fetch_trending_topics(self, post_count: int) -> List[TrendItem]:
        """Fetch trending tech news from DuckDuckGo news search."""
        all_items: List[TrendItem] = []
        seen_titles: List[str] = []

        queries = random.sample(NEWS_QUERIES, min(len(NEWS_QUERIES), 5))

        for query in queries:
            try:
                print(f"Searching news: {query}")
                results = self.ddgs.news(query, max_results=5, timelimit="w")
                for result in results:
                    title = result.get("title", "").strip()
                    body = result.get("body", "").strip()
                    url = result.get("url", "")
                    source = result.get("source", "Unknown")

                    if not title or not body:
                        continue
                    if len(title) < 10:
                        continue
                    if self._is_duplicate(title, seen_titles):
                        continue

                    seen_titles.append(title)
                    all_items.append(TrendItem(
                        title=title,
                        body=body[:300],
                        url=url,
                        source=source,
                    ))
            except Exception as e:
                print(f"Error fetching news for '{query}': {e}")
                continue

        if len(all_items) < post_count:
            print(f"Only found {len(all_items)} news items, adding fallback keywords...")
            fallback_keywords = random.sample(KEYWORDS, min(len(KEYWORDS), post_count - len(all_items)))
            for kw in fallback_keywords:
                if len(all_items) >= post_count:
                    break
                all_items.append(TrendItem(
                    title=kw,
                    body=f"Trending topic in tech: {kw}. This is a popular discussion area for software engineers and tech professionals.",
                    url="",
                    source="Fallback",
                ))

        selected = all_items[:post_count]
        print(f"Selected {len(selected)} topics:")
        for item in selected:
            print(f"  - {item.title} ({item.source})")
        return selected
