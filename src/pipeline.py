"""Content generation pipeline orchestrating the full workflow."""

import random
import time
from typing import Optional

from src.ai_service import AIService
from src.gsheet_client import GSheetClient
from src.image_generator import ImageGenerator
from src.storage_client import StorageClient
from src.trend_fetcher import TrendFetcher, TrendItem

POST_FORMATS = {
    "hot_take": """
        Write a HOT TAKE post reacting to this news. Take a contrarian or bold stance.
        Start with a strong opinion that challenges conventional wisdom.
        Example opener: "Unpopular opinion:" or "Hot take:" or "Everyone's excited about X, but..."
    """,
    "implication": """
        Write a post explaining what this news ACTUALLY MEANS for developers in their daily work.
        Connect the headline to real, practical impact on coding/engineering workflows.
        Example opener: "What this actually means for your codebase:" or "Here's why devs should care:"
    """,
    "prediction": """
        Write a BOLD PREDICTION post based on this news.
        Project forward what this could mean for the industry in 6-12 months.
        Example opener: "Calling it now:" or "Mark my words:" or "This is the beginning of..."
    """,
    "reaction": """
        Write an AUTHENTIC REACTION post from the perspective of a senior software engineer.
        Share a genuine thought or personal insight triggered by this news.
        Example opener: "As someone who's been building for 10+ years..." or "My honest reaction:"
    """,
    "lesson": """
        Write a LESSON LEARNED post that extracts a timeless principle from this news.
        Connect the current event to a broader truth about software engineering.
        Example opener: "This proves what I've always said:" or "The real lesson here:"
    """,
}


class ContentPipeline:
    """Pipeline for generating social media content and logging to Google Sheets."""

    def __init__(self, config: dict):
        """Initialize pipeline with configuration."""
        self.config = config
        self.delay_seconds = config.get("LLM_CALL_DELAY_SECONDS", 15)

        self.ai_service = AIService(
            api_key=str(config.get("OPENROUTER_API", "")),
            model_name=str(config.get("CONTENT_MODEL", "arcee-ai/trinity-large-preview:free")),
        )
        self.image_generator = ImageGenerator(
            cloudflare_account_id=config.get("CLOUDFLARE_ACCOUNT_ID"),
            cloudflare_api_token=config.get("CLOUDFLARE_API_TOKEN"),
            model_name=config.get("IMAGE_MODEL"),
        )
        self.trend_fetcher = TrendFetcher()
        self.storage_client = StorageClient(
            api_key=config.get("IMGBB_API_KEY", ""),
        )
        self.gsheet_client = GSheetClient(
            service_account_file="serviceAccountKey.json",
            spreadsheet_id=config.get("GSHEET_ID", ""),
        )

    def _delay(self):
        """Sleep to respect rate limits."""
        print(f"Waiting {self.delay_seconds}s to respect rate limits...")
        time.sleep(self.delay_seconds)

    def _generate_post_content(self, trend: TrendItem) -> Optional[str]:
        """Generate post text content based on a trending news item."""
        format_name = random.choice(list(POST_FORMATS.keys()))
        format_instructions = POST_FORMATS[format_name]
        print(f"Using post format: {format_name}")

        prompt = f"""
        You are a tech thought leader with 100K+ followers on LinkedIn/X. Your posts consistently go viral
        because they're insightful, relatable, and spark discussion among software engineers and tech professionals.

        **NEWS TO REACT TO:**
        Headline: {trend.title}
        Summary: {trend.body}
        Source: {trend.source}

        **POST FORMAT:**
        {format_instructions}

        **TARGET AUDIENCE:**
        Software engineers, data engineers, DevOps, ML engineers, tech leads, CTOs, and tech-curious professionals.
        They scroll fast - you have 1 second to hook them.

        **VIRALITY BEST PRACTICES:**
        - First line is EVERYTHING - make it scroll-stopping (bold claim, surprising stat, or relatable pain)
        - Be specific, not generic (name actual technologies, real scenarios)
        - Write like you talk - conversational, not corporate
        - Create tension or curiosity that makes people want to engage
        - End with a question or provocative statement that invites replies
        - Use short sentences. Break up ideas. Like this.

        **CONSTRAINTS:**
        - STRICTLY 200-270 characters (we need room for links)
        - No hashtags
        - No "As an AI" or similar phrases
        - No asterisks for emphasis (*word*)
        - No emojis
        - Output ONLY the post text, nothing else
        """
        return self.ai_service.generate_response(prompt)

    def _generate_and_upload_image(self, trend: TrendItem, post_content: str) -> Optional[str]:
        """Generate image for the post and upload to imgBB, return public URL."""
        image_prompt = self.ai_service.generate_image_prompt(trend.title, post_content=post_content)
        if not image_prompt:
            print("Failed to generate image prompt")
            return None

        self._delay()

        image_bytes = self.image_generator.generate_image(
            image_prompt,
            fallback_generator=self.image_generator.create_tech_themed_image,
        )
        if not image_bytes:
            print("Failed to generate image")
            return None

        return self.storage_client.upload_image(image_bytes)

    def run(self, post_count: int):
        """Run the content generation pipeline for the specified number of posts."""
        print(f"Starting content generation pipeline for {post_count} posts...")

        trends = self.trend_fetcher.fetch_trending_topics(post_count)
        if not trends:
            print("No topics found, aborting pipeline")
            return

        for i, trend in enumerate(trends):
            print(f"\n--- Generating post {i + 1}/{post_count} ---")
            print(f"Topic: {trend.title}")
            print(f"Source: {trend.source}")

            post_content = self._generate_post_content(trend)
            if not post_content:
                print(f"Failed to generate content for topic: {trend.title}")
                self.gsheet_client.append_row(trend.title, "", None, status="FAILED")
                continue

            post_content = post_content.strip().strip('"\'')
            print(f"Generated post content: {post_content[:100]}...")

            self._delay()

            image_url = self._generate_and_upload_image(trend, post_content)

            keywords_col = f"{trend.title[:50]}" + (f" | {trend.url}" if trend.url else "")
            status = "PENDING" if image_url else "FAILED"
            self.gsheet_client.append_row(keywords_col, post_content, image_url, status=status)

            if i < len(trends) - 1:
                self._delay()

        print(f"\nPipeline complete. Generated {post_count} posts.")
