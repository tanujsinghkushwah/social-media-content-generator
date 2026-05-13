"""Content generation pipeline orchestrating the full workflow."""

import random
import time
from typing import Optional

from src.ai_service import AIService
from src.backlink_manager import BacklinkManager
from src.gsheet_client import GSheetClient
from src.image_generator import ImageGenerator
from src.personas import HOOK_TEMPLATES, WRITER_PERSONAS, pick_cta, pick_hook, pick_pillar
from src.post_history import PostHistory
from src.sanitizer import sanitize_for_platform
from src.storage_client import StorageClient
from src.trend_fetcher import TrendFetcher, TrendItem

_IG_HASHTAG_POOL = [
    "#techinterview", "#leetcode", "#faang", "#softwareengineer", "#codinginterview",
    "#systemdesign", "#techjobs", "#careeradvice", "#interviewprep", "#h1b",
    "#layoffrecovery", "#newgrad", "#swe", "#jobsearch", "#softwareengineering",
    "#techcareers", "#interviewgenie",
]

_LI_HASHTAG_POOL = [
    "#softwareengineering", "#techcareers", "#interviewprep", "#faang",
    "#leetcode", "#careeradvice", "#h1b", "#interviewgenie",
]


def _shares_5_consecutive_words(a: str, b: str) -> bool:
    """Return True if string a contains any 5-word sequence from string b."""
    a_words = a.lower().split()
    b_words = b.lower().split()
    if len(b_words) < 5:
        return False
    for i in range(len(b_words) - 4):
        seq = " ".join(b_words[i:i + 5])
        if seq in " ".join(a_words):
            return True
    return False


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
        self.post_history = PostHistory(config.get("FIREBASE_DB_URL", ""))
        self.backlink_manager = BacklinkManager(config.get("FIREBASE_DB_URL", ""))

    def _pick_persona_balanced(self) -> dict:
        """Pick a persona, giving extra weight to under-used ones (P5.6)."""
        usage = self.post_history.persona_usage()
        if not usage:
            return random.choice(WRITER_PERSONAS)
        avg = sum(usage.values()) / len(usage)
        weights = [1 if usage.get(p["name"], 0) >= avg else 2 for p in WRITER_PERSONAS]
        return random.choices(WRITER_PERSONAS, weights=weights, k=1)[0]

    def _delay(self):
        print(f"Waiting {self.delay_seconds}s to respect rate limits...")
        time.sleep(self.delay_seconds)

    def _build_prompt(self, trend: TrendItem, persona: Optional[dict] = None, pillar: Optional[dict] = None) -> tuple[str, str]:
        """Build the dual-platform prompt. Returns (prompt, pillar_name)."""
        if persona is None:
            persona = self._pick_persona_balanced()
        if pillar is None:
            pillar = pick_pillar()
        hook = pick_hook()
        is_tool_reveal = pillar["name"] == "tool_reveal"

        print(f"Persona: {persona['name']} | Pillar: {pillar['name']}")

        # Rotating CTA — never the same hardcoded phrase every post (P5.4)
        instagram_cta = (
            "End with: 'Link in bio if you want the unfair advantage.'"
            if is_tool_reveal
            else f"End with this call to action (verbatim): '{pick_cta()}'"
        )

        # Shuffled hashtag pools so each post gets a different priority subset (P5.5)
        ig_pool = _IG_HASHTAG_POOL[:]
        random.shuffle(ig_pool)
        ig_priority = " ".join(ig_pool[:5])
        ig_full = " ".join(ig_pool)

        li_pool = _LI_HASHTAG_POOL[:]
        random.shuffle(li_pool)
        li_tags = " ".join(li_pool[:4])

        # In-context negatives — recent post openings the model must not echo (P5.2/P3)
        recent_openings = self.post_history.recent_openings(count=8, days=14)
        openings_block = ""
        if recent_openings:
            listing = "\n".join(f'  - "{o}"' for o in recent_openings)
            openings_block = f"""
RECENT OPENINGS YOU HAVE USED — your new opening must NOT echo or rephrase any of these:
{listing}
"""

        # Brand mention rule (P5.8) — soft, all pillars except tool_reveal (already has explicit CTA)
        brand_rule = (
            "" if is_tool_reveal
            else "If it fits naturally, mention 'Interview Genie' once by name on Instagram or LinkedIn. Don't force it. Never be salesy."
        )

        # Phase 2 — platform-aware backlink injection
        pillar_name_for_backlink = pillar["name"]
        x_link = self.backlink_manager.should_include_backlink("x", pillar_name_for_backlink, trend.title)
        li_link = self.backlink_manager.should_include_backlink("linkedin", pillar_name_for_backlink, trend.title)

        x_link_rule = (
            f"- Include this link as the final line: {x_link}"
            if x_link else "- No URLs in this post."
        )
        li_link_rule = (
            f"- Include this link as the final line after the CTA: {li_link}"
            if li_link else "- No URLs in this post."
        )

        prompt = f"""Do not show reasoning or chain-of-thought. Output ONLY the final JSON.

You are {persona['name']}: {persona['voice_description']}

Your go-to phrases (use 1-2 naturally, don't force all): {", ".join(persona['pet_phrases'])}
Never do this: {persona['taboos']}

SENTENCE RHYTHM for this persona: {persona.get('rhythm_cue', '')}

CONTENT ANGLE: {pillar['description']}

HOOK STYLE TO USE: "{hook}"
REWRITE this hook in your own words to fit the specific topic. Do NOT copy more than 4 consecutive words from the template.
Example: if the hook is "I bombed 7 interviews before I figured this out," you might write "Three rejections in a row before this finally clicked."
{openings_block}
NEWS / TOPIC:
  Title: {trend.title}
  Context: {trend.body}
  Source: {trend.source}

YOUR READER: A software engineer right now in an active job search — anxious, grinding interviews,
scrolling at midnight. They want to feel seen, then get one tactical edge they didn't have before.

{brand_rule}

---

Generate THREE posts about the same core insight. The same image will be used for all three.

X POST RULES:
- MAXIMUM 260 characters — count every character including spaces and punctuation
- Hook in the first 8 words. No warm-up sentences.
- Conversational, contractions OK, line breaks welcome
- Zero hashtags. Zero emojis. No "As an AI". No asterisks or markdown bold.
- End with a sharp question, punchline, or cliffhanger — never a flat statement.
{x_link_rule}

INSTAGRAM POST RULES:
- 700–1100 characters in the body (not counting hashtags)
- Story arc: bold hook line → tension or relatable pain → insight/reveal → 2-3 tactical bullets → CTA
- Use blank lines between sections (Instagram eats walls of text)
- 1-2 emojis max, only if they earn their spot
- No markdown — no **asterisks**, no #Header:, no "🔑 Insight:" style labels
- {instagram_cta}
- On a new line after the body, add exactly 7 hashtags.
  You MUST include at least 3 from this priority set: {ig_priority}
  Full pool to choose from: {ig_full}

LINKEDIN POST RULES:
- 400–700 characters total — short and punchy, not a long story
- Lead with a sharp insight or contrarian observation in line 1
- 1 short anecdote OR 1 tactical bullet — pick one, not both
- Conversational professional tone; first person OK; minimal emojis (0–1)
- End with a one-line takeaway or pointed question
- On a new line after the body, add 2–3 hashtags from: {li_tags}
{li_link_rule}

OUTPUT FORMAT — return only valid JSON, no markdown fences, no explanation:
{{"x_post": "<x text here>", "instagram_post": "<instagram text here>", "linkedin_post": "<linkedin text here>"}}"""

        return prompt, pillar["name"]

    def _generate_multi_platform_content(self, trend: TrendItem) -> Optional[dict]:
        """Generate X, Instagram, and LinkedIn post content for a trending topic.

        Retries up to 2× with a fresh persona+pillar if:
        - The IG opening echoes a hook template or recent post opening (P5.2).
        - The IG post is too similar to a recent post in RTDB (Phase 3 Jaccard check).
        """
        persona = self._pick_persona_balanced()
        pillar = pick_pillar()

        for attempt in range(3):
            prompt, pillar_name = self._build_prompt(trend, persona=persona, pillar=pillar)
            result = self.ai_service.generate_multi_platform_content(prompt)
            if not result:
                return None

            x_post = result.get("x_post", "").strip().strip('"\'')
            ig_post = result.get("instagram_post", "").strip().strip('"\'')
            li_post = result.get("linkedin_post", "").strip().strip('"\'')

            if not x_post or not ig_post:
                print("Model returned empty x_post or instagram_post")
                return None

            # P5.3 — strip markdown and validate hashtags
            x_post = sanitize_for_platform(x_post, "x")
            ig_post = sanitize_for_platform(ig_post, "instagram")
            li_post = sanitize_for_platform(li_post, "linkedin")

            # P5.2 — check if IG opening echoes a hook template or recent history
            ig_opening = ig_post[:80].lower()
            hook_echo = any(
                _shares_5_consecutive_words(ig_opening, tmpl.lower())
                for tmpl in HOOK_TEMPLATES
            )
            recent_openings = self.post_history.recent_openings(count=8, days=14)
            opening_echo = any(
                _shares_5_consecutive_words(ig_opening, prev.lower())
                for prev in recent_openings
            )

            # Phase 3 — Jaccard dedup check against last 30 days
            similar_entry = self.post_history.is_too_similar(ig_post, threshold=0.7, days=30)

            if (hook_echo or opening_echo or similar_entry) and attempt < 2:
                reason = (
                    "hook template echo" if hook_echo
                    else "opening echo" if opening_echo
                    else f"near-duplicate of post from {similar_entry.get('ts', '?')}"
                )
                print(f"  [retry {attempt + 1}/2] {reason} — regenerating with fresh persona+pillar")
                persona = self._pick_persona_balanced()
                pillar = pick_pillar()
                continue

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

            posts = {"x_post": x_post, "instagram_post": ig_post, "linkedin_post": li_post}
            self.post_history.record_post(
                posts=posts,
                topic=trend.title,
                pillar=pillar_name,
                persona=persona["name"],
            )
            return posts

        print("All 3 attempts produced flagged content — using last result anyway")
        posts = {"x_post": x_post, "instagram_post": ig_post, "linkedin_post": li_post}
        self.post_history.record_post(
            posts=posts,
            topic=trend.title,
            pillar=pillar_name,
            persona=persona["name"],
        )
        return posts

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
