"""Generate and append a single post row to the spreadsheet for testing.

Usage (from project root):
    python scripts/test_single_post.py
    python scripts/test_single_post.py --topic "Tech layoffs 2025"
    python scripts/test_single_post.py --topic "FAANG interview tips" --no-image
"""

import argparse
import sys
import os
from typing import Optional

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.pipeline import ContentPipeline
from src.trend_fetcher import TrendFetcher, TrendItem


def run_single_post(topic: Optional[str] = None, skip_image: bool = False):
    config = load_config()
    pipeline = ContentPipeline(config)

    if topic:
        trend = TrendItem(
            title=topic,
            body=f"User-supplied test topic: {topic}",
            url="",
            source="Manual",
        )
        print(f"Using manual topic: {topic}")
    else:
        print("Fetching one live trending topic...")
        trends = TrendFetcher().fetch_trending_topics(post_count=1)
        if not trends:
            print("ERROR: Could not fetch any trending topic. Use --topic to supply one manually.")
            sys.exit(1)
        trend = trends[0]
        print(f"Fetched topic: {trend.title} ({trend.source})")

    print("\n--- Generating multi-platform content ---")
    result = pipeline._generate_multi_platform_content(trend)
    if not result:
        print("ERROR: Content generation failed.")
        sys.exit(1)

    print(f"\nX Post ({len(result['x_post'])} chars):\n{result['x_post']}")
    print(f"\nInstagram Post ({len(result['instagram_post'])} chars):\n{result['instagram_post']}")
    if result["linkedin_post"]:
        print(f"\nLinkedIn Post ({len(result['linkedin_post'])} chars):\n{result['linkedin_post']}")
    else:
        print("\nLinkedIn Post: <empty — will be skipped>")

    image_url = None
    if not skip_image:
        print("\n--- Generating and uploading image ---")
        pipeline._delay()
        image_url = pipeline._generate_and_upload_image(trend, result["instagram_post"])
        if image_url:
            print(f"Image URL: {image_url}")
        else:
            print("WARNING: Image generation failed — row will be appended without image.")

    keywords_col = f"{trend.title[:50]}" + (f" | {trend.url}" if trend.url else "")
    status_instagram = "PENDING" if image_url else ("NO IMAGE" if not skip_image else "PENDING")
    status_linkedin = "PENDING" if result["linkedin_post"] else "SKIPPED"
    pipeline.gsheet_client.append_row(
        keywords_col,
        result["x_post"],
        result["instagram_post"],
        result["linkedin_post"],
        image_url,
        status_x="PENDING",
        status_instagram=status_instagram,
        status_linkedin=status_linkedin,
    )
    print("\nRow appended to spreadsheet.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a single test post and append it to the sheet.")
    parser.add_argument("--topic", type=str, default=None, help="Custom topic text (skips live trend fetch)")
    parser.add_argument("--no-image", action="store_true", help="Skip image generation (faster test)")
    args = parser.parse_args()

    run_single_post(topic=args.topic, skip_image=args.no_image)
