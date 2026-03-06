"""Fetch trending tech topics using DuckDuckGo search."""

import random
from datetime import datetime
from typing import List

from duckduckgo_search import DDGS

from src.constants import KEYWORDS

SEARCH_QUERIES = [
    "trending tech topics software engineering {year}",
    "LinkedIn trending developer topics {year}",
    "viral programming topics X Twitter {year}",
    "latest software engineering trends {year}",
    "hot topics for developers {year}",
]


class TrendFetcher:
    """Fetch trending tech topics from web search."""

    def __init__(self):
        """Initialize the trend fetcher."""
        self.ddgs = DDGS()

    def _extract_topic_from_result(self, result: dict) -> str:
        """Extract a concise topic from a search result."""
        title = result.get("title", "")
        if ":" in title:
            title = title.split(":")[0]
        if "-" in title:
            title = title.split("-")[0]
        if "|" in title:
            title = title.split("|")[0]
        return title.strip()[:50]

    def fetch_trending_topics(self, post_count: int) -> List[str]:
        """Fetch trending tech topics from web search."""
        current_year = datetime.now().year
        all_topics = []

        for query_template in SEARCH_QUERIES:
            query = query_template.format(year=current_year)
            try:
                print(f"Searching: {query}")
                results = self.ddgs.text(query, max_results=5)
                for result in results:
                    topic = self._extract_topic_from_result(result)
                    if topic and len(topic) > 3:
                        all_topics.append(topic)
            except Exception as e:
                print(f"Error fetching results for '{query}': {e}")
                continue

        unique_topics = list(dict.fromkeys(all_topics))

        if len(unique_topics) < post_count:
            print(f"Only found {len(unique_topics)} unique topics, adding fallback keywords...")
            fallback = [kw for kw in KEYWORDS if kw not in unique_topics]
            random.shuffle(fallback)
            unique_topics.extend(fallback)

        selected = unique_topics[:post_count]
        print(f"Selected {len(selected)} topics: {selected}")
        return selected
