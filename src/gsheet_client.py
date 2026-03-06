"""Google Sheets client for logging generated content."""

from datetime import datetime
from typing import Optional

import gspread
from google.oauth2 import service_account
import pytz

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

IST = pytz.timezone("Asia/Kolkata")

HEADERS = ["Date (IST)", "Topic/Keywords", "Post Content", "Image URL", "Status"]


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

    def _ensure_headers(self):
        """Add headers if the sheet is empty or missing headers."""
        if self._headers_checked:
            return

        try:
            first_row = self.sheet.row_values(1)
            if not first_row or first_row[0] != HEADERS[0]:
                self.sheet.insert_row(HEADERS, index=1)
                self._format_header_row()
                print("Added column headers to sheet")
            self._headers_checked = True
        except Exception as e:
            print(f"Error checking/adding headers: {e}")
            self._headers_checked = True

    def _format_header_row(self):
        """Format the header row with bold text and background color."""
        try:
            self.sheet.format("A1:E1", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.6},
                "horizontalAlignment": "CENTER",
            })
            self.sheet.format("A1:E1", {
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            })
        except Exception as e:
            print(f"Error formatting header row: {e}")

    def append_row(
        self,
        keywords: str,
        content: str,
        image_url: Optional[str],
        status: str = "PENDING",
    ) -> bool:
        """Append a new row with post data to the sheet."""
        self._ensure_headers()

        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        image_cell = f'=HYPERLINK("{image_url}", "View Image")' if image_url else ""

        row = [timestamp, keywords, content, image_cell, status]
        try:
            self.sheet.append_row(row, value_input_option="USER_ENTERED")
            print(f"Appended row to sheet: {keywords[:30]}...")
            return True
        except Exception as e:
            print(f"Error appending row to sheet: {e}")
            return False

    def update_status(self, row_index: int, status: str) -> bool:
        """Update the status column for a given row."""
        try:
            self.sheet.update_cell(row_index, 5, status)
            return True
        except Exception as e:
            print(f"Error updating status: {e}")
            return False
