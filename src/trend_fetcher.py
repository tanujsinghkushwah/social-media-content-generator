"""Fetch trending topics relevant to tech interview/job seekers from multiple sources."""

import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote_plus

import requests
from duckduckgo_search import DDGS

from src.constants import KEYWORDS

# Interview/hiring-relevant DDG news queries
NEWS_QUERIES = [
    "tech layoffs hiring 2025",
    "software engineer job market hiring",
    "FAANG big tech hiring freeze or expansion",
    "software engineer salary trends compensation",
    "tech company layoffs job cuts",
    "remote work software developer jobs",
    "coding interview process changes",
    "tech recruiter insights hiring tips",
    "system design interview trends",
    "software engineer career advice",
]

# Keywords that indicate interview/hiring relevance for HackerNews + Reddit filtering
RELEVANCE_KEYWORDS = re.compile(
    r"hiring|layoff|laid off|interview|offer|faang|career|resume|job market|"
    r"compensation|salary|h1b|opt|onsite|recruiter|job hunt|job search|"
    r"rejected|rejection|negotiat|new grad|bootcamp|internship|l[3-7]|swe|"
    r"software engineer|tech job|fired|rto|return to office",
    re.IGNORECASE,
)


@dataclass
class TrendItem:
    """A trending news item or discussion with full context."""
    title: str
    body: str
    url: str
    source: str

    def __str__(self) -> str:
        return f"{self.title} ({self.source})"


class TrendFetcher:
    """Fetch interview/job-seeker relevant trends from HackerNews, Reddit, and DuckDuckGo."""

    def __init__(self):
        self.ddgs = DDGS()

    def _normalize_title(self, title: str) -> str:
        title = title.lower()
        title = re.sub(r"[^\w\s]", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        return title

    def _is_duplicate(self, new_title: str, existing_titles: List[str]) -> bool:
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

    def _fetch_hackernews(self, limit: int = 15) -> List[TrendItem]:
        """Fetch top HackerNews stories relevant to hiring/interviews."""
        try:
            resp = requests.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=10,
            )
            resp.raise_for_status()
            story_ids = resp.json()[:50]

            items: List[TrendItem] = []
            for story_id in story_ids:
                if len(items) >= limit:
                    break
                try:
                    story_resp = requests.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                        timeout=5,
                    )
                    story_resp.raise_for_status()
                    story = story_resp.json()
                    title = story.get("title", "")
                    url = story.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                    text = story.get("text", "")

                    if not title:
                        continue
                    if not RELEVANCE_KEYWORDS.search(title + " " + text):
                        continue

                    score = story.get("score", 0)
                    descendants = story.get("descendants", 0)
                    body = (
                        f"{text[:250].strip() if text else ''} "
                        f"[{score} points, {descendants} comments on HackerNews]"
                    ).strip()

                    items.append(TrendItem(
                        title=title,
                        body=body or f"Trending on HackerNews with {score} upvotes.",
                        url=url,
                        source="HackerNews",
                    ))
                    time.sleep(0.1)
                except Exception:
                    continue

            print(f"HackerNews: fetched {len(items)} relevant stories")
            return items
        except Exception as e:
            print(f"HackerNews fetch error: {e}")
            return []

    def _fetch_reddit_cscareerquestions(self, limit: int = 15) -> List[TrendItem]:
        """Fetch top posts from r/cscareerquestions this week."""
        try:
            headers = {"User-Agent": "InterviewGenieBot/1.0 (social content generator)"}
            resp = requests.get(
                "https://www.reddit.com/r/cscareerquestions/top.json?t=week&limit=25",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 403:
                print("Reddit: blocked (datacenter IP) — skipping")
                return []
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])

            items: List[TrendItem] = []
            for post in posts:
                if len(items) >= limit:
                    break
                data = post.get("data", {})
                title = data.get("title", "").strip()
                selftext = data.get("selftext", "").strip()
                score = data.get("score", 0)
                url = data.get("url", "")
                permalink = data.get("permalink", "")

                if not title or score < 100:
                    continue

                body = selftext[:250] if selftext else f"Top post with {score} upvotes on r/cscareerquestions."
                full_url = f"https://reddit.com{permalink}" if permalink else url

                items.append(TrendItem(
                    title=title,
                    body=body,
                    url=full_url,
                    source="Reddit/cscareerquestions",
                ))

            print(f"Reddit r/cscareerquestions: fetched {len(items)} posts")
            return items
        except Exception as e:
            print(f"Reddit fetch error: {e}")
            return []

    def _fetch_google_news_rss(self, limit: int = 15) -> List[TrendItem]:
        """Fetch interview/hiring-relevant articles via Google News RSS — no auth, CI-safe."""
        queries = [
            "tech layoffs job cuts 2025",
            "software engineer interview tips",
            "FAANG hiring freeze or expansion",
            "tech salary negotiation offer",
            "software engineer job market",
        ]
        items: List[TrendItem] = []
        for query in random.sample(queries, min(3, len(queries))):
            try:
                url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:5]:
                    title = (item.findtext("title") or "").strip()
                    desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    source_el = item.find("source")
                    source = source_el.text if source_el is not None else "Google News"
                    if title and len(title) > 10:
                        items.append(TrendItem(title=title, body=desc[:300], url=link, source=source))
                if len(items) >= limit:
                    break
            except Exception as e:
                print(f"Google News RSS error for '{query}': {e}")
                continue
        print(f"Google News RSS: fetched {len(items)} articles")
        return items[:limit]

    def _fetch_devto(self, limit: int = 10) -> List[TrendItem]:
        """Fetch trending tech/career articles from Dev.to — free, no auth, CI-safe."""
        items: List[TrendItem] = []
        tags = ["career", "interviews", "jobsearch", "codenewbie", "productivity"]
        for tag in random.sample(tags, min(2, len(tags))):
            try:
                resp = requests.get(
                    f"https://dev.to/api/articles?top=7&tag={tag}&per_page=10",
                    timeout=10,
                    headers={"User-Agent": "InterviewGenieBot/1.0"},
                )
                resp.raise_for_status()
                for art in resp.json():
                    title = art.get("title", "").strip()
                    desc = art.get("description", "").strip()
                    url = art.get("url", "")
                    if title and len(title) > 10:
                        items.append(TrendItem(
                            title=title,
                            body=desc[:300] or f"Trending on Dev.to: {title}",
                            url=url,
                            source="Dev.to",
                        ))
                if len(items) >= limit:
                    break
            except Exception as e:
                print(f"Dev.to error for tag '{tag}': {e}")
                continue
        print(f"Dev.to: fetched {len(items)} articles")
        return items[:limit]

    def _fetch_duckduckgo(self, post_count: int) -> List[TrendItem]:
        """Fetch interview/hiring relevant news from DuckDuckGo."""
        items: List[TrendItem] = []
        queries = random.sample(NEWS_QUERIES, min(len(NEWS_QUERIES), 5))

        for query in queries:
            try:
                print(f"DDG news search: {query}")
                results = self.ddgs.news(query, max_results=5, timelimit="w")
                for result in results:
                    title = result.get("title", "").strip()
                    body = result.get("body", "").strip()
                    url = result.get("url", "")
                    source = result.get("source", "Unknown")

                    if not title or not body or len(title) < 10:
                        continue

                    items.append(TrendItem(
                        title=title,
                        body=body[:300],
                        url=url,
                        source=source,
                    ))
            except Exception as e:
                err = str(e)
                if "429" in err or "Ratelimit" in err:
                    print(f"DDG: rate-limited on '{query}' — skipping")
                else:
                    print(f"DDG error for '{query}': {e}")
                continue

        print(f"DuckDuckGo: fetched {len(items)} articles")
        return items

    def fetch_trending_topics(self, post_count: int) -> List[TrendItem]:
        """Fetch and merge trending topics from HackerNews, Reddit, and DuckDuckGo."""
        all_items: List[TrendItem] = []
        seen_titles: List[str] = []

        # Priority order: HN > Google News > Dev.to > Reddit > DDG
        # Google News and Dev.to are CI-safe (no IP blocks); Reddit and DDG may fail in CI
        sources = [
            self._fetch_hackernews(limit=post_count + 5),
            self._fetch_google_news_rss(limit=post_count + 5),
            self._fetch_devto(limit=post_count + 5),
            self._fetch_reddit_cscareerquestions(limit=post_count + 5),
            self._fetch_duckduckgo(post_count),
        ]
        for source_items in sources:
            for item in source_items:
                if not self._is_duplicate(item.title, seen_titles):
                    seen_titles.append(item.title)
                    all_items.append(item)

        # Fallback to curated interview keywords if sources ran dry
        if len(all_items) < post_count:
            print(f"Only {len(all_items)} items found, adding fallback keywords...")
            fallback_keywords = random.sample(KEYWORDS, min(len(KEYWORDS), post_count - len(all_items)))
            for kw in fallback_keywords:
                if len(all_items) >= post_count:
                    break
                all_items.append(TrendItem(
                    title=kw,
                    body=f"A key topic for software engineers navigating interviews and job hunting: {kw}.",
                    url="",
                    source="Fallback",
                ))

        # Shuffle for variety across sources, then take what we need
        random.shuffle(all_items)
        selected = all_items[:post_count]

        print(f"Selected {len(selected)} topics:")
        for item in selected:
            print(f"  - {item.title} ({item.source})")
        return selected
