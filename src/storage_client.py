"""Image hosting client supporting Cloudinary (primary) and imgBB (fallback).

Set IMAGE_STORAGE_PROVIDER=cloudinary or imgbb in .env to choose the primary.
Defaults to cloudinary. Falls back to imgbb if the primary upload fails.
"""

import base64
import os
from datetime import datetime
from typing import Optional

import cloudinary
import cloudinary.uploader
import requests

IMGBB_API_URL = "https://api.imgbb.com/1/upload"


class StorageClient:
    """Upload images to Cloudinary or imgBB and return public URLs."""

    def __init__(
        self,
        imgbb_api_key: str = "",
        cloudinary_cloud_name: str = "",
        cloudinary_api_key: str = "",
        cloudinary_api_secret: str = "",
        provider: str = "",
    ):
        self.imgbb_api_key = imgbb_api_key
        self.provider = (provider or os.getenv("IMAGE_STORAGE_PROVIDER", "cloudinary")).lower()

        cloudinary.config(
            cloud_name=cloudinary_cloud_name or os.getenv("CLOUDINARY_CLOUD_NAME", ""),
            api_key=cloudinary_api_key or os.getenv("CLOUDINARY_API_KEY", ""),
            api_secret=cloudinary_api_secret or os.getenv("CLOUDINARY_API_SECRET", ""),
            secure=True,
        )

    def upload_image(self, image_bytes: bytes, filename: Optional[str] = None) -> Optional[str]:
        """Upload image bytes using the configured provider, falling back to the other."""
        if not filename:
            filename = f"post_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if self.provider == "cloudinary":
            url = self._upload_cloudinary(image_bytes, filename)
            if url:
                return url
            print("Cloudinary upload failed, falling back to imgBB...")
            return self._upload_imgbb(image_bytes, filename)
        else:
            url = self._upload_imgbb(image_bytes, filename)
            if url:
                return url
            print("imgBB upload failed, falling back to Cloudinary...")
            return self._upload_cloudinary(image_bytes, filename)

    def _upload_cloudinary(self, image_bytes: bytes, public_id: str) -> Optional[str]:
        """Upload to Cloudinary and return the secure URL."""
        if not cloudinary.config().cloud_name:
            print("Error: Cloudinary credentials not configured")
            return None
        try:
            result = cloudinary.uploader.upload(
                image_bytes,
                public_id=public_id,
                folder="interview-genie-social",
                overwrite=True,
                resource_type="image",
            )
            url = result.get("secure_url")
            print(f"Uploaded image to Cloudinary: {url}")
            return url
        except Exception as e:
            print(f"Error uploading image to Cloudinary: {e}")
            return None

    def _upload_imgbb(self, image_bytes: bytes, filename: str) -> Optional[str]:
        """Upload to imgBB and return the public URL."""
        if not self.imgbb_api_key:
            print("Error: IMGBB_API_KEY not set")
            return None
        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            response = requests.post(
                IMGBB_API_URL,
                data={"key": self.imgbb_api_key, "image": image_b64, "name": filename},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                url = data["data"]["url"]
                print(f"Uploaded image to imgBB: {url}")
                return url
            print(f"imgBB upload failed: {data}")
            return None
        except Exception as e:
            print(f"Error uploading image to imgBB: {e}")
            return None
