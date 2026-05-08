"""Content generation pipeline orchestrating the full workflow."""

import time
from typing import Optional

from src.ai_service import AIService
from src.gsheet_client import GSheetClient
from src.image_generator import ImageGenerator
from src.personas import pick_hook, pick_persona, pick_pillar
from src.storage_client import StorageClient
from src.trend_fetcher import TrendFetcher, TrendItem


class ContentPipeline:
    """Pipeline for generating dual-platform social media content and logging to Google Sheets."""

    def __init__(self, config: dict):
        self.config = config
        self.delay_seconds = config.get("LLM_CALL_DELAY_SECONDS", 15)

        content_models = [
            m.strip()
            for m in str(config.get("CONTENT_MODEL", "z-ai/glm-4.5-air:free")).split(",")
            if m.strip()
        ]
        self.ai_service = AIService(
            api_key=str(config.get("OPENROUTER_API", "")),
            models=content_models,
        )
        self.image_generator = ImageGenerator(
            cloudflare_account_id=config.get("CLOUDFLARE_ACCOUNT_ID"),
            cloudflare_api_token=config.get("CLOUDFLARE_API_TOKEN"),
            model_name=config.get("IMAGE_MODEL"),
        )
        self.trend_fetcher = TrendFetcher()
        self.storage_client = StorageClient(
            imgbb_api_key=config.get("IMGBB_API_KEY", ""),
        )
        self.gsheet_client = GSheetClient(
            service_account_file="serviceAccountKey.json",
            spreadsheet_id=config.get("GSHEET_ID", ""),
        )

    def _delay(self):
        print(f"Waiting {self.delay_seconds}s to respect rate limits...")
        time.sleep(self.delay_seconds)

    def _build_prompt(self, trend: TrendItem) -> tuple[str, str]:
        """Build the dual-platform prompt. Returns (prompt, pillar_name)."""
        persona = pick_persona()
        pillar = pick_pillar()
        hook = pick_hook()
        is_tool_reveal = pillar["name"] == "tool_reveal"

        print(f"Persona: {persona['name']} | Pillar: {pillar['name']}")

        instagram_cta = (
            "End with: 'Link in bio if you want the unfair advantage.'"
            if is_tool_reveal
            else "End with: 'Save this if your next interview is within 30 days.'"
        )

        prompt = f"""Do not show reasoning or chain-of-thought. Output ONLY the final JSON.

You are {persona['name']}: {persona['voice_description']}

Your go-to phrases (use 1-2 naturally, don't force all): {", ".join(persona['pet_phrases'])}
Never do this: {persona['taboos']}

CONTENT ANGLE: {pillar['description']}

HOOK STYLE TO USE: "{hook}"
Weave this hook into your opening naturally — adapt it to fit the topic. Don't use it verbatim if it doesn't fit.

NEWS / TOPIC:
  Title: {trend.title}
  Context: {trend.body}
  Source: {trend.source}

YOUR READER: A software engineer right now in an active job search — anxious, grinding interviews,
scrolling at midnight. They want to feel seen, then get one tactical edge they didn't have before.

---

Generate THREE posts about the same core insight. The same image will be used for all three.

X POST RULES:
- MAXIMUM 260 characters — count every character including spaces and punctuation
- Hook in the first 8 words. No warm-up sentences.
- Conversational, contractions OK, line breaks welcome
- Zero hashtags. Zero emojis. No "As an AI". No asterisks for bold.
- End with a sharp question, punchline, or cliffhanger — never a flat statement.

INSTAGRAM POST RULES:
- 700–1100 characters in the body (not counting hashtags)
- Story arc: bold hook line → tension or relatable pain → insight/reveal → 2-3 tactical bullets → CTA
- Use blank lines between sections (Instagram eats walls of text)
- 1-2 emojis max, only if they earn their spot
- {instagram_cta}
- On a new line after the body, add 6-8 hashtags from this set (pick the most relevant):
  #techinterview #leetcode #faang #softwareengineer #codinginterview #systemdesign
  #techjobs #careeradvice #interviewprep #h1b #layoffrecovery #newgrad #swe #jobsearch

LINKEDIN POST RULES:
- 400–700 characters total — short and punchy, not a long story
- Lead with a sharp insight or contrarian observation in line 1
- 1 short anecdote OR 1 tactical bullet — pick one, not both
- Conversational professional tone; first person OK; minimal emojis (0–1)
- End with a one-line takeaway or pointed question
- On a new line after the body, add 2–3 hashtags from this set (pick the most relevant):
  #softwareengineering #techcareers #interviewprep #faang #leetcode #careeradvice #h1b

OUTPUT FORMAT — return only valid JSON, no markdown fences, no explanation:
{{"x_post": "<x text here>", "instagram_post": "<instagram text here>", "linkedin_post": "<linkedin text here>"}}"""

        return prompt, pillar["name"]

    def _generate_multi_platform_content(self, trend: TrendItem) -> Optional[dict]:
        """Generate X, Instagram, and LinkedIn post content for a trending topic."""
        prompt, _ = self._build_prompt(trend)
        result = self.ai_service.generate_multi_platform_content(prompt)
        if not result:
            return None

        x_post = result.get("x_post", "").strip().strip('"\'')
        ig_post = result.get("instagram_post", "").strip().strip('"\'')
        li_post = result.get("linkedin_post", "").strip().strip('"\'')

        if not x_post or not ig_post:
            print("Model returned empty x_post or instagram_post")
            return None

        # Hard-trim X post to 280 chars at a sentence boundary if over limit
        if len(x_post) > 280:
            trimmed = x_post[:277]
            last_sentence = max(trimmed.rfind(". "), trimmed.rfind("? "), trimmed.rfind("! "))
            x_post = (trimmed[:last_sentence + 1] if last_sentence > 100 else trimmed).rstrip() + "..."

        print(f"X post ({len(x_post)} chars): {x_post[:80]}...")
        print(f"Instagram post ({len(ig_post)} chars): {ig_post[:80]}...")
        if li_post:
            print(f"LinkedIn post ({len(li_post)} chars): {li_post[:80]}...")
        else:
            print("LinkedIn post empty — channel will be skipped for this row")
        return {"x_post": x_post, "instagram_post": ig_post, "linkedin_post": li_post}

    def _generate_and_upload_image(self, trend: TrendItem, post_content: str) -> Optional[str]:
        """Generate image for the post and upload it, returning the public URL."""
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

            result = self._generate_multi_platform_content(trend)
            if not result:
                print(f"Failed to generate content for topic: {trend.title}")
                self.gsheet_client.append_row(
                    trend.title,
                    "",
                    "",
                    "",
                    None,
                    status_x="FAILED",
                    status_instagram="FAILED",
                    status_linkedin="FAILED",
                )
                continue

            self._delay()

            # Use the richer Instagram post as context for the image prompt
            image_url = self._generate_and_upload_image(trend, result["instagram_post"])

            keywords_col = f"{trend.title[:50]}" + (f" | {trend.url}" if trend.url else "")
            # Instagram hard-requires an image; X and LinkedIn can post without one.
            status_instagram = "PENDING" if image_url else "NO IMAGE"
            status_linkedin = "PENDING" if result["linkedin_post"] else "SKIPPED"
            self.gsheet_client.append_row(
                keywords_col,
                result["x_post"],
                result["instagram_post"],
                result["linkedin_post"],
                image_url,
                status_x="PENDING",
                status_instagram=status_instagram,
                status_linkedin=status_linkedin,
            )

            if i < len(trends) - 1:
                self._delay()

        print(f"\nPipeline complete. Generated {post_count} posts.")
