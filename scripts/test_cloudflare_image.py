"""Standalone test: generate an image via Cloudflare Workers AI and save to generated_image.jpg."""

import base64
import os
import sys

from dotenv import load_dotenv
import requests

load_dotenv()

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
MODEL = "@cf/black-forest-labs/flux-1-schnell"
OUTPUT_PATH = "generated_image.jpg"


def main():
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        print("Error: Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in .env")
        sys.exit(1)

    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{MODEL}"
    headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    payload = {
        "prompt": "a futuristic tech workspace with holographic displays",
        "steps": 4,
    }

    print(f"Calling Cloudflare Workers AI ({MODEL})...")
    response = requests.post(url, headers=headers, json=payload, timeout=60)

    if not response.ok:
        print(f"API error: {response.status_code} - {response.text}")
        sys.exit(1)

    data = response.json()
    if not data.get("success"):
        errors = data.get("errors", [])
        print(f"API returned success=false: {errors}")
        sys.exit(1)

    result = data.get("result", {})
    image_b64 = result.get("image")
    if not image_b64:
        print("No image in response")
        sys.exit(1)

    image_data = base64.b64decode(image_b64)
    with open(OUTPUT_PATH, "wb") as f:
        f.write(image_data)

    print(f"Image saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
