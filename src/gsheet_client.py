"""Google Sheets client for logging generated content."""

from datetime import datetime
from typing import Optional

import gspread
from gspread.utils import ValueInputOption
from google.oauth2 import service_account
import pytz

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

IST = pytz.timezone("Asia/Kolkata")

HEADERS = [
    "Date (IST)",
    "Topic/Keywords",
    "X Post",
    "Instagram Post",
    "LinkedIn Post",
    "Image URL",
    "Status X",
    "Status Instagram",
    "Status LinkedIn",
]

CHANNEL_STATUS_COLUMN = {"x": 7, "instagram": 8, "linkedin": 9}


class GSheetClient:
    """Append post data rows to a Google Spreadsheet."""

    def __init__(self, service_account_file: str, spreadsheet_id: str):
        """Initialize with service account credentials and spreadsheet ID."""
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES
        )
        self.gc = gspread.authorize(credentials)
        self.spreadsheet_id = spreadsheet_id
        self._sheet = None
        self._headers_checked = False

    @property
    def sheet(self):
        """Lazy-load the first worksheet."""
        if self._sheet is None:
            spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            self._sheet = spreadsheet.sheet1
        return self._sheet

    def _has_valid_headers(self) -> bool:
        """Check if the sheet already has valid headers in row 1."""
        try:
            first_row = self.sheet.row_values(1)
            if not first_row:
                return False
            # Normalize whitespace to avoid false negatives from trailing spaces
            normalized = [v.strip() for v in first_row[:len(HEADERS)]]
            return normalized == HEADERS
        except Exception:
            return False

    def _ensure_headers(self):
        """Add headers if the sheet is empty or missing headers."""
        if self._headers_checked:
            return

        try:
            if not self._has_valid_headers():
                # Only safe to insert when sheet is truly empty — inserting into a
                # sheet with existing data shifts all rows down, making old row 1
                # appear as a data row (causing header text to be posted as content).
                all_values = self.sheet.get_all_values()
                is_empty = not all_values or all(
                    not any(cell.strip() for cell in row) for row in all_values
                )
                if is_empty:
                    self.sheet.insert_row(HEADERS, index=1)
                    print("Added column headers to sheet")
                else:
                    print("Warning: Sheet has data but headers don't match — skipping insert to avoid row shift")
            else:
                print("Headers already exist")
            self._format_header_row()
            self._headers_checked = True
        except Exception as e:
            print(f"Error checking/adding headers: {e}")
            self._headers_checked = True

    def _format_header_row(self):
        """Format the header row with bold text and blue background."""
        try:
            self.sheet.format("A1:I1", {
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                },
                "backgroundColor": {"red": 0.13, "green": 0.33, "blue": 0.53},
                "horizontalAlignment": "CENTER",
            })
            self.sheet.freeze(rows=1)
            print("Formatted and froze header row")
        except Exception as e:
            print(f"Error formatting header row: {e}")

    def append_row(
        self,
        keywords: str,
        x_post: str,
        instagram_post: str,
        linkedin_post: str,
        image_url: Optional[str],
        status_x: str = "PENDING",
        status_instagram: str = "PENDING",
        status_linkedin: str = "PENDING",
    ) -> bool:
        """Append a new row with post data to the sheet."""
        self._ensure_headers()

        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        image_cell = f'=HYPERLINK("{image_url}", "View Image")' if image_url else ""

        row = [
            timestamp,
            keywords,
            x_post,
            instagram_post,
            linkedin_post,
            image_cell,
            status_x,
            status_instagram,
            status_linkedin,
        ]
        try:
            self.sheet.append_row(row, value_input_option=ValueInputOption.user_entered)
            print(f"Appended row to sheet: {keywords[:30]}...")
            return True
        except Exception as e:
            print(f"Error appending row to sheet: {e}")
            return False

    def update_channel_status(self, row_index: int, channel: str, status: str) -> bool:
        """Update the per-channel status column for a given row.

        channel must be one of "x", "instagram", "linkedin".
        """
        col = CHANNEL_STATUS_COLUMN.get(channel.lower())
        if col is None:
            print(f"Unknown channel: {channel}")
            return False
        try:
            self.sheet.update_cell(row_index, col, status)
            return True
        except Exception as e:
            print(f"Error updating {channel} status: {e}")
            return False
