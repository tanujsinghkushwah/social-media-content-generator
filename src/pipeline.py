"""Content generation pipeline orchestrating the full workflow."""

import time
from typing import Optional

from src.ai_service import AIService
from src.gsheet_client import GSheetClient
from src.image_generator import ImageGenerator
from src.storage_client import StorageClient
from src.trend_fetcher import TrendFetcher


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

    def _generate_post_content(self, topic: str) -> Optional[str]:
        """Generate post text content for a given topic."""
        prompt = f"""
        You're a tech thought leader posting daily on social media about software engineering life.

        Craft a viral post on '{topic}' that hooks all software engineers (frontend, backend, full-stack, etc.):

        - Open with bold/contrarian hook on a universal dev pain (e.g., "Everyone chases X, but...")
        - Drop 1 unexpected insight from real SDE experience (keep <5 sentences, simple words)
        - End with reply bait: question like "What's your take?" or polarizing takeaway
        - STRICTLY UNDER 280 characters
        - Short, punchy sentences.
        - No hashtags, no AI mentions, no *emphasis*
        """
        return self.ai_service.generate_response(prompt)

    def _generate_and_upload_image(self, topic: str, post_content: str) -> Optional[str]:
        """Generate image for the post and upload to imgBB, return public URL."""
        image_prompt = self.ai_service.generate_image_prompt(topic, post_content=post_content)
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

        topics = self.trend_fetcher.fetch_trending_topics(post_count)
        if not topics:
            print("No topics found, aborting pipeline")
            return

        for i, topic in enumerate(topics):
            print(f"\n--- Generating post {i + 1}/{post_count} for topic: {topic} ---")

            post_content = self._generate_post_content(topic)
            if not post_content:
                print(f"Failed to generate content for topic: {topic}")
                self.gsheet_client.append_row(topic, "", None, status="FAILED")
                continue

            post_content = post_content.strip().strip('"\'')
            print(f"Generated post content: {post_content[:100]}...")

            self._delay()

            image_url = self._generate_and_upload_image(topic, post_content)

            status = "PENDING" if image_url else "FAILED"
            self.gsheet_client.append_row(topic, post_content, image_url, status=status)

            if i < len(topics) - 1:
                self._delay()

        print(f"\nPipeline complete. Generated {post_count} posts.")
