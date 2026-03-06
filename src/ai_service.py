"""AI service using LiteLLM for unified text generation."""

from typing import Optional

import litellm


class AIService:
    """LiteLLM-based AI service for text generation."""

    def __init__(self, api_key: str, model_name: str):
        """Initialize with API key and model name."""
        self.api_key = api_key
        self.model_name = f"openrouter/{model_name}"

    def generate_response(self, prompt: str) -> Optional[str]:
        """Generate AI response using LiteLLM."""
        try:
            print(f"Generating response using LiteLLM ({self.model_name})...")
            response = litellm.completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                api_key=self.api_key,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating AI response: {e}", exc_info=True)
            return None

    def generate_image_prompt(
        self, topic: str, post_content: Optional[str] = None
    ) -> Optional[str]:
        """Generate a detailed image creation prompt from topic and post content."""
        if post_content:
            prompt = f"""
            Create a visually captivating tech image for this software engineering post: "{post_content}". Topic: '{topic}'.

            Craft a highly detailed prompt (100+ words) for a 16:9 landscape image:

            - Directly visualize post's core hook/insight (e.g., shattered chain for "LLM chains", glowing diagram for system design) with metaphorical drama
            - Modern cyberpunk aesthetic: neon blues/greens on dark backgrounds, high contrast glows, particle effects, floating holographic code snippets or neural connections
            - Dynamic composition: asymmetric, rule-of-thirds, central focal break (exploding myth, unlocking door, speed lines)
            - Cinematic lighting: volumetric god rays, rim lighting on tech elements, lens flares for energy
            - Vibrant accents (electric cyan, fiery orange), professional polish, ultra-detailed 4K
            - NO text/words/typography anywhere
            - Single paragraph output, ready for AI image gen

            Make it thumb-stopping for devs scrolling social media.
            """
        else:
            prompt = f"""
            Create a visually captivating tech image for this software engineering topic: '{topic}'.

            Craft a highly detailed prompt (100+ words) for a 16:9 landscape image:

            - Directly visualize topic's core essence with metaphorical drama
            - Modern cyberpunk aesthetic: neon blues/greens on dark backgrounds, high contrast glows, particle effects, floating holographic code snippets or neural connections
            - Dynamic composition: asymmetric, rule-of-thirds, central focal break
            - Cinematic lighting: volumetric god rays, rim lighting on tech elements, lens flares for energy
            - Vibrant accents (electric cyan, fiery orange), professional polish, ultra-detailed 4K
            - NO text/words/typography anywhere
            - Single paragraph output, ready for AI image gen

            Make it thumb-stopping for devs scrolling social media.
            """

        response_text = self.generate_response(prompt)
        if not response_text:
            return None

        image_prompt = response_text.strip()[:500]
        print(f"Generated image prompt: {image_prompt}")
        return image_prompt
