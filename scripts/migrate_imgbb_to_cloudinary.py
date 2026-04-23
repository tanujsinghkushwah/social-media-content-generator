"""Migrate ImgBB image URLs to Cloudinary for PENDING rows in Google Sheet."""

import os
import re
import sys
import time
from typing import Optional
import requests
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from google.oauth2 import service_account
import gspread
from gspread.utils import ValueInputOption

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column indices (1-based)
COL_IMAGE_URL = 4   # Column D
COL_STATUS = 5      # Column E (X)

HYPERLINK_RE = re.compile(r'=HYPERLINK\("([^"]+)"', re.IGNORECASE)


def extract_url_from_hyperlink(cell_value: str) -> Optional[str]:
    """Extract the raw URL from a HYPERLINK formula or return the value as-is."""
    if not cell_value:
        return None
    m = HYPERLINK_RE.match(cell_value.strip())
    if m:
        return m.group(1)
    if cell_value.startswith("http"):
        return cell_value
    return None


def upload_to_cloudinary(image_bytes: bytes, public_id: str) -> Optional[str]:
    """Upload image bytes to Cloudinary and return the secure URL."""
    try:
        result = cloudinary.uploader.upload(
            image_bytes,
            public_id=public_id,
            folder="interview-genie-social",
            overwrite=True,
            resource_type="image",
        )
        return result.get("secure_url")
    except Exception as e:
        print(f"  Cloudinary upload failed: {e}")
        return None


def download_image(url: str) -> Optional[bytes]:
    """Download image from URL and return raw bytes."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"  Download failed ({url}): {e}")
        return None


def main():
    # --- Cloudinary config ---
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )
    if not all([
        os.getenv("CLOUDINARY_CLOUD_NAME"),
        os.getenv("CLOUDINARY_API_KEY"),
        os.getenv("CLOUDINARY_API_SECRET"),
    ]):
        print("ERROR: Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET in .env")
        sys.exit(1)

    # --- Google Sheets config ---
    service_account_file = os.getenv("SERVICE_ACCOUNT_FILE", "serviceAccountKey.json")
    spreadsheet_id = os.getenv("GSHEET_ID")
    if not spreadsheet_id:
        print("ERROR: Set GSHEET_ID in .env")
        sys.exit(1)

    credentials = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES
    )
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(spreadsheet_id).sheet1

    all_rows = sheet.get_all_values(value_render_option="FORMULA")
    if not all_rows:
        print("Sheet is empty.")
        return

    header = all_rows[0]
    data_rows = all_rows[1:]  # skip header row

    pending_count = 0
    migrated = 0
    failed = 0

    for i, row in enumerate(data_rows):
        row_index = i + 2  # 1-based, +1 for header

        # Pad row if it has fewer columns
        status = row[COL_STATUS - 1].strip() if len(row) >= COL_STATUS else ""
        if status.upper() != "PENDING":
            continue

        pending_count += 1
        image_cell = row[COL_IMAGE_URL - 1].strip() if len(row) >= COL_IMAGE_URL else ""
        imgbb_url = extract_url_from_hyperlink(image_cell)

        if not imgbb_url:
            print(f"Row {row_index}: No image URL found (cell value: {image_cell!r}), skipping.")
            failed += 1
            continue

        print(f"Row {row_index}: Downloading from ImgBB... {imgbb_url}")
        image_bytes = download_image(imgbb_url)
        if not image_bytes:
            failed += 1
            continue

        # Use row index as public_id for idempotency
        public_id = f"post_image_row{row_index}"
        print(f"Row {row_index}: Uploading to Cloudinary as '{public_id}'...")
        cloudinary_url = upload_to_cloudinary(image_bytes, public_id)
        if not cloudinary_url:
            failed += 1
            continue

        new_cell = f'=HYPERLINK("{cloudinary_url}", "View Image")'
        try:
            sheet.update(
                f"D{row_index}",
                [[new_cell]],
                value_input_option=ValueInputOption.user_entered,
            )
            print(f"Row {row_index}: Updated image URL -> {cloudinary_url}")
            migrated += 1
        except Exception as e:
            print(f"Row {row_index}: Failed to update sheet: {e}")
            failed += 1

        time.sleep(0.5)  # avoid rate-limiting

    print(f"\nDone. Pending rows found: {pending_count} | Migrated: {migrated} | Failed: {failed}")


if __name__ == "__main__":
    main()
