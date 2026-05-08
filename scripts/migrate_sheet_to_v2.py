"""One-time migration: expand the 6-column sheet to the new 9-column layout.

Old layout (columns A-F):
  A = Date (IST)       B = Topic/Keywords    C = X Post
  D = Instagram Post   E = Image URL         F = Status

New layout (columns A-I):
  A = Date (IST)       B = Topic/Keywords    C = X Post
  D = Instagram Post   E = LinkedIn Post     F = Image URL
  G = Status X         H = Status Instagram  I = Status LinkedIn

For each data row:
  - LinkedIn Post (E) = copy of Instagram Post (old D)
  - Image URL    (F) = preserved from old E, HYPERLINK formula kept intact
  - Status X     (G) = COMPLETED if old Status was COMPLETED, else PENDING
  - Status IG    (H) = same
  - Status LI    (I) = same

Usage (from project root, venv active):
    python3 scripts/migrate_sheet_to_v2.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import gspread
from google.oauth2 import service_account

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

NEW_HEADERS = [
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

OLD_HEADERS = ["Date (IST)", "Topic/Keywords", "X Post", "Instagram Post", "Image URL", "Status"]


def map_status(old_status: str) -> str:
    """Map old single-column status to per-channel status value."""
    return "COMPLETED" if old_status.strip().upper() == "COMPLETED" else "PENDING"


def migrate():
    spreadsheet_id = os.getenv("GSHEET_ID", "").strip()
    if not spreadsheet_id:
        print("ERROR: GSHEET_ID not found in .env — set it and retry.")
        sys.exit(1)

    service_account_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "serviceAccountKey.json",
    )

    print(f"Connecting to spreadsheet: {spreadsheet_id}")
    credentials = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES
    )
    gc = gspread.authorize(credentials)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    sheet = spreadsheet.sheet1

    # Read display values (for logic) and formula values (to preserve HYPERLINK cells)
    print("Reading sheet data…")
    display_rows = sheet.get_all_values()
    # gspread returns formulas when value_render_option='FORMULA'
    formula_rows = sheet.get_all_values(value_render_option="FORMULA")

    if not display_rows:
        print("Sheet is empty — nothing to migrate.")
        return

    header = [v.strip() for v in display_rows[0]]

    # Guard: already migrated?
    if header == NEW_HEADERS:
        print("✅ Sheet already has the new 9-column layout. Nothing to do.")
        return
    if len(header) >= 9 and header[6:9] == NEW_HEADERS[6:9]:
        print("✅ Sheet already appears to have per-channel status columns. Nothing to do.")
        return

    data_rows = display_rows[1:]
    formula_data_rows = formula_rows[1:] if len(formula_rows) > 1 else []

    print(f"Found {len(data_rows)} data row(s) to migrate.\n")

    new_rows = []
    for idx, row in enumerate(data_rows):
        def col(i, default=""):
            return row[i] if len(row) > i else default

        def fcol(i, default=""):
            frow = formula_data_rows[idx] if idx < len(formula_data_rows) else row
            return frow[i] if len(frow) > i else default

        date_val     = col(0)
        keywords_val = col(1)
        x_post_val   = col(2)
        ig_post_val  = col(3)
        image_val    = fcol(4)   # keep formula (e.g. =HYPERLINK(...))
        old_status   = col(5, "PENDING")

        ch_status = map_status(old_status)

        new_row = [
            date_val,       # A: Date (IST)
            keywords_val,   # B: Topic/Keywords
            x_post_val,     # C: X Post
            ig_post_val,    # D: Instagram Post
            ig_post_val,    # E: LinkedIn Post  ← copy of Instagram
            image_val,      # F: Image URL      ← formula preserved
            ch_status,      # G: Status X
            ch_status,      # H: Status Instagram
            ch_status,      # I: Status LinkedIn
        ]
        new_rows.append(new_row)

        preview_x  = (x_post_val[:60] + "…") if len(x_post_val) > 60 else x_post_val
        print(f"  Row {idx + 2}: [{old_status!r:12s} → {ch_status}]  {preview_x!r}")

    print(f"\nClearing sheet and rewriting {len(new_rows)} row(s)…")
    sheet.clear()

    # Write header + data in one batch
    sheet.update([NEW_HEADERS] + new_rows, value_input_option="USER_ENTERED")

    # Re-apply header formatting
    sheet.format("A1:I1", {
        "textFormat": {
            "bold": True,
            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
        },
        "backgroundColor": {"red": 0.13, "green": 0.33, "blue": 0.53},
        "horizontalAlignment": "CENTER",
    })
    sheet.freeze(rows=1)

    print(f"\n✅ Migration complete — {len(new_rows)} row(s) updated to new 9-column layout.")
    print("   LinkedIn Post = copy of Instagram Post for all existing rows.")
    print("   Per-channel statuses (G/H/I) set based on old Status column.")


if __name__ == "__main__":
    migrate()
