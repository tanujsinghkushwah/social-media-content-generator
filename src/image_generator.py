"""Image generation services."""

import io
import random
from typing import Optional

import requests
import base64
from PIL import Image, ImageDraw, ImageFont
import textwrap

CLOUDFLARE_DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"


class ImageGenerator:
    """Image generation using Cloudflare Workers AI with Pillow fallback."""

    def __init__(
        self,
        cloudflare_account_id: Optional[str] = None,
        cloudflare_api_token: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize with Cloudflare credentials."""
        self.cloudflare_account_id = cloudflare_account_id
        self.cloudflare_api_token = cloudflare_api_token
        self.model = model_name or CLOUDFLARE_DEFAULT_MODEL

    def _generate_with_cloudflare(self, prompt: str, steps: int = 4) -> Optional[bytes]:
        """Generate image via Cloudflare Workers AI REST API. Returns None on failure."""
        if not self.cloudflare_account_id or not self.cloudflare_api_token:
            return None
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}"
            f"/ai/run/{self.model}"
        )
        headers = {"Authorization": f"Bearer {self.cloudflare_api_token}"}
        payload = {"prompt": prompt[:2048], "steps": min(max(steps, 1), 8)}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if not response.ok:
                return None
            data = response.json()
            if not data.get("success"):
                return None
            image_b64 = (data.get("result") or {}).get("image")
            if not image_b64:
                return None
            return base64.b64decode(image_b64)
        except Exception:
            return None
    
    def create_tech_themed_image(self, topic: str, title: str) -> bytes:
        """Generate a tech-themed image locally using Pillow (fallback)."""
        try:
            print(f"Creating local tech-themed image for: {topic}")
            width, height = 1200, 630
            image = Image.new('RGB', (width, height), (255, 255, 255))  # type: ignore[arg-type]
            draw = ImageDraw.Draw(image)

            for y in range(height):
                r = int(20 + (50 * (1 - y / height)))
                g = int(40 + (80 * (y / height)))
                b = int(80 + (120 * (y / height)))
                for x in range(width):
                    r_mod = r + int(20 * (x / width))
                    g_mod = g + int(10 * (x / width))
                    draw.point((x, y), fill=(r_mod, g_mod, b))

            nodes = []
            for _ in range(20):
                x = random.randint(50, width-50)
                y = random.randint(50, height-50)
                size = random.randint(5, 15)
                nodes.append((x, y, size))

            for i in range(len(nodes)):
                for j in range(i+1, min(i+4, len(nodes))):
                    x1, y1, _ = nodes[i]
                    x2, y2, _ = nodes[j]
                    dist = ((x2-x1)**2 + (y2-y1)**2)**0.5
                    if dist < 300:
                        draw.line((x1, y1, x2, y2), fill=(180, 220, 255, 128), width=1)

            for x, y, size in nodes:
                draw.ellipse((x-size, y-size, x+size, y+size), 
                             fill=(220, 240, 255), 
                             outline=(255, 255, 255))

            for _ in range(8):
                x = random.randint(0, width)
                y = random.randint(0, height)
                size = random.randint(50, 150)
                for s in range(size, 0, -10):
                    opacity = int(100 * (s/size))
                    draw.ellipse((x-s, y-s, x+s, y+s), 
                                outline=(255, 255, 255, opacity),
                                width=2)
            try:
                try:
                    title_font = ImageFont.truetype("arial.ttf", 60)
                    subtitle_font = ImageFont.truetype("arial.ttf", 30)
                except:
                    title_font = ImageFont.load_default()
                    subtitle_font = ImageFont.load_default()

                overlay = Image.new('RGBA', (width, 200), (0, 0, 0, 150))  # type: ignore[arg-type]
                image.paste(overlay, (0, height-200), overlay)
                title_wrapped = textwrap.fill(title, width=30)

                draw.text((width//2, height-120), title_wrapped, 
                         fill=(255, 255, 255), 
                         font=title_font, 
                         anchor="mm", 
                         align="center")

                draw.text((width//2, height-40), "interviewgenie.net",
                         fill=(200, 200, 255),
                         font=subtitle_font,
                         anchor="mm")
                
            except Exception as e:
                print(f"Error adding text to image: {e}")

            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=95)
            return img_buffer.getvalue()
            
        except Exception as e:
            print(f"Error creating local image: {e}")
            image = Image.new('RGB', (800, 500), (20, 40, 80))  # type: ignore[arg-type]
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG')
            return img_buffer.getvalue()
    
    def _add_watermark(self, image_bytes: bytes) -> bytes:
        """Stamp 'interviewgenie.net' in the bottom-right corner of the image."""
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            w, h = img.size
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # type: ignore[arg-type]
            draw = ImageDraw.Draw(overlay)
            font_size = max(14, h // 40)
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                try:
                    font = ImageFont.load_default(size=font_size)  # type: ignore[call-arg]
                except TypeError:
                    font = ImageFont.load_default()
            text = "interviewgenie.net"
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            margin = max(10, h // 60)
            x, y = w - tw - margin, h - th - margin
            # Semi-transparent dark background pill for legibility
            draw.rectangle((x - 4, y - 2, x + tw + 4, y + th + 2), fill=(0, 0, 0, 120))
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 200))
            combined = Image.alpha_composite(img, overlay).convert("RGB")
            buf = io.BytesIO()
            combined.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
        except Exception as e:
            print(f"Watermark failed (non-fatal): {e}")
            return image_bytes

    def generate_image(self, prompt: str, fallback_generator=None) -> Optional[bytes]:
        """Generate image via Cloudflare Workers AI, with Pillow fallback on failure."""
        image_bytes = self._generate_with_cloudflare(prompt)
        if image_bytes is not None:
            print(f"Image generated with Cloudflare Workers AI ({self.model}).")
            return self._add_watermark(image_bytes)

        print("Falling back to local image generation...")
        result = fallback_generator(prompt, prompt[:30]) if fallback_generator else self.create_tech_themed_image(prompt, prompt[:30])
        return self._add_watermark(result) if result else result
