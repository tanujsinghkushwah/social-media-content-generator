"""AI service using OpenRouter API for text generation."""

from typing import Dict, List, Optional

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class AIService:
    """OpenRouter AI service for text generation."""

    def __init__(self, api_key: str, model_name: str):
        """Initialize with OpenRouter API key and model."""
        self.api_key = api_key
        self.model_name = model_name
        self.conversation_history: Dict[str, List[Dict[str, str]]] = {}

    def generate_response(
        self, prompt: str, conversation_id: Optional[str] = None
    ) -> Optional[str]:
        """Generate AI response using OpenRouter API."""
        messages = []
        if conversation_id and conversation_id in self.conversation_history:
            messages = list(self.conversation_history[conversation_id])

        current_messages = messages + [{"role": "user", "content": prompt}]

        try:
            print(f"Generating response using OpenRouter ({self.model_name})...")
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "messages": current_messages,
                    "max_tokens": 600,
                    "stream": False,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            response_text = data["choices"][0]["message"]["content"]

            if conversation_id:
                current_messages.append({"role": "assistant", "content": response_text})
                self.conversation_history[conversation_id] = current_messages

            return response_text
        except Exception as e:
            print(f"Error generating AI response with OpenRouter: {e}")
            return None

    def generate_image_prompt(
        self, topic: str, tweet_content: Optional[str] = None
    ) -> Optional[str]:
        """Generate a detailed image creation prompt from topic and tweet content."""
        if tweet_content:
            prompt = f"""
            Create a visually captivating tech image for this software engineering tweet: "{tweet_content}". Topic: '{topic}'.

            Craft a highly detailed prompt (100+ words) for a 16:9 landscape image:

            - Directly visualize tweet's core hook/insight (e.g., shattered chain for "LLM chains", glowing diagram for system design) with metaphorical drama
            - Modern cyberpunk aesthetic: neon blues/greens on dark backgrounds, high contrast glows, particle effects, floating holographic code snippets or neural connections
            - Dynamic composition: asymmetric, rule-of-thirds, central focal break (exploding myth, unlocking door, speed lines)
            - Cinematic lighting: volumetric god rays, rim lighting on tech elements, lens flares for energy
            - Vibrant accents (electric cyan, fiery orange), professional polish, ultra-detailed 4K
            - NO text/words/typography anywhere
            - Single paragraph output, ready for AI image gen

            Make it thumb-stopping for devs scrolling X.
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

            Make it thumb-stopping for devs scrolling X.
            """

        response_text = self.generate_response(prompt)

        if not response_text:
            return None

        image_prompt = response_text.strip()[:500]
        print(f"Generated image prompt: {image_prompt}")
        return image_prompt
