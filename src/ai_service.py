"""AI service using LiteLLM for unified text generation."""

import json
import re
from typing import List, Optional

import litellm


class AIService:
    """LiteLLM-based AI service with sequential model fallback."""

    def __init__(self, api_key: str, models: List[str]):
        """Initialize with API key and an ordered list of model names to try.

        Each model is tried in sequence; the next is used only if the previous
        fails (HTTP error, empty response, or unparseable JSON for dual-platform calls).
        """
        self.api_key = api_key
        self.models = [f"openrouter/{m.strip()}" for m in models]

    def _call_model(self, model: str, prompt: str, max_tokens: int) -> Optional[str]:
        """Make a single LiteLLM completion call. Raises on HTTP/API errors."""
        print(f"Trying model: {model}...")
        
        system_prompt = (
            "You are a strict JSON data generator. You MUST output ONLY valid JSON. "
            "Do not include any conversational text, explanations, or reasoning. "
            "If you need to think, you must do it silently or strictly inside <think>...</think> tags."
        )
        
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            api_key=self.api_key,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            print(f"Model returned empty content (finish_reason={response.choices[0].finish_reason})")
        return content

    def generate_response(self, prompt: str, max_tokens: int = 600) -> Optional[str]:
        """Try each model in order; return the first non-empty response."""
        for model in self.models:
            try:
                result = self._call_model(model, prompt, max_tokens)
                if result:
                    return result
                print(f"{model}: empty response, trying next...")
            except Exception as e:
                print(f"{model}: error — {e}. Trying next...")
        print("All models failed for generate_response.")
        return None

    def _parse_multi_platform_json(self, raw: str) -> Optional[dict]:
        """Extract {x_post, instagram_post, linkedin_post?} from a model response.

        Requires x_post and instagram_post; linkedin_post is optional and
        defaults to "" if absent (caller will skip the LinkedIn channel).
        Tolerates chain-of-thought wrappers and markdown fences.
        """
        # Strip <think>...</think> blocks emitted by reasoning models
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        
        # Try to extract exact JSON block from markdown fences first
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
        else:
            # Fallback: strip markdown fences if they are at the edges
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()

        def _normalize(data: dict) -> Optional[dict]:
            if "x_post" in data and "instagram_post" in data:
                return {
                    "x_post": data["x_post"],
                    "instagram_post": data["instagram_post"],
                    "linkedin_post": data.get("linkedin_post", ""),
                }
            return None

        # Try whole response as JSON
        try:
            normalized = _normalize(json.loads(cleaned))
            if normalized:
                return normalized
        except json.JSONDecodeError:
            pass

        # Balanced-brace scan: find every top-level {...} object containing
        # "x_post" and try parsing from last to first (reasoning models put the
        # final answer at the end).
        candidates = []
        depth = 0
        start = -1
        for i, ch in enumerate(cleaned):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    block = cleaned[start : i + 1]
                    if '"x_post"' in block:
                        candidates.append(block)
                    start = -1

        for block in reversed(candidates):
            try:
                normalized = _normalize(json.loads(block))
                if normalized:
                    return normalized
            except json.JSONDecodeError:
                continue

        return None

    def _force_json_extraction(self, model: str, raw_text: str) -> Optional[dict]:
        """Fallback: Ask the model to parse its own messy output into strict JSON."""
        print(f"Attempting to force JSON extraction from messy output using {model}...")
        prompt = f"""
        You are a strict data extraction tool. Extract the final X post, Instagram post, and LinkedIn post from the following messy text.
        Return ONLY a single valid JSON object inside a ```json block with the keys:
        - "x_post"
        - "instagram_post"
        - "linkedin_post"
        
        Do NOT include any reasoning, <think> tags, or conversational text.
        
        MESSY TEXT TO PARSE:
        {raw_text}
        """
        
        system_prompt = "You are a strict JSON data extractor. Output ONLY valid JSON. No conversational text."
        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "```json\n{\n"}
                ],
                max_tokens=1500,
                api_key=self.api_key,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            print(f"DEBUG: Force extraction returned:\n{content}\n---")
            if content:
                # If the prefill was consumed and the response starts directly with keys, prepend the brace
                if not content.strip().startswith("{") and not content.strip().startswith("```"):
                    content = "{\n" + content
                
                # Recursively try to parse the new output
                return self._parse_multi_platform_json(content)
        except Exception as e:
            print(f"Force extraction failed: {e}")
            
        return None

    def generate_multi_platform_content(self, prompt: str) -> Optional[dict]:
        """Try each model in order until one returns parseable platform JSON."""
        for model in self.models:
            try:
                raw = self._call_model(model, prompt, max_tokens=2500)
                if not raw:
                    print(f"{model}: empty response, trying next...")
                    continue
                result = self._parse_multi_platform_json(raw)
                if result:
                    return result
                    
                # If first parse fails, try forcing extraction
                print(f"{model}: unparseable JSON (tail: {raw[-150:]!r}), attempting force-extract...")
                extracted = self._force_json_extraction(model, raw)
                if extracted:
                    return extracted
                    
                print(f"{model}: force extraction failed, trying next...")
            except Exception as e:
                print(f"{model}: error — {e}. Trying next...")
        print("All models failed for generate_multi_platform_content.")
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
        print(f"Generated image prompt: {image_prompt[:100]}...")
        return image_prompt
