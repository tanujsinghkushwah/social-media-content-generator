"""Image hosting client using imgBB (free, no card required)."""

import base64
from datetime import datetime
from typing import Optional

import requests

IMGBB_API_URL = "https://api.imgbb.com/1/upload"


class StorageClient:
    """Upload images to imgBB and get public URLs."""

    def __init__(self, api_key: str):
        """Initialize with imgBB API key."""
        self.api_key = api_key

    def upload_image(self, image_bytes: bytes, filename: Optional[str] = None) -> Optional[str]:
        """Upload image bytes to imgBB and return public URL."""
        if not self.api_key:
            print("Error: IMGBB_API_KEY not set")
            return None

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"post_image_{timestamp}"

        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            response = requests.post(
                IMGBB_API_URL,
                data={
                    "key": self.api_key,
                    "image": image_b64,
                    "name": filename,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                public_url = data["data"]["url"]
                print(f"Uploaded image to imgBB: {public_url}")
                return public_url
            else:
                print(f"imgBB upload failed: {data}")
                return None
        except Exception as e:
            print(f"Error uploading image to imgBB: {e}")
            return None
