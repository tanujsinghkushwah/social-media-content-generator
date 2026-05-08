# Social Media Content Generator

Automated pipeline that generates viral tech interview content for X (Twitter), Instagram, and LinkedIn. Produces platform-optimised post text + AI images, logs everything to a Google Sheet, and schedules posting via the Buffer API through a Google Apps Script trigger.

## Features

- **Trending Topic Discovery** — HackerNews, Google News RSS, Dev.to, Reddit r/cscareerquestions, DuckDuckGo
- **Triple-Platform Content** — one LLM call generates three distinct posts optimised per platform
- **AI Image Generation** — Cloudflare Workers AI (Flux model) with Pillow fallback; uploaded to Cloudinary
- **Per-Channel Status Tracking** — X, Instagram, and LinkedIn each have their own status column; a failure on one platform never causes re-posts on the others
- **Buffer Scheduling** — Google Apps Script posts to all three channels via the Buffer GraphQL API on a daily cron
- **Firebase Remote Config** — centralised config management with `.env` override support
- **GitHub Actions** — automated daily content generation at 9 AM IST

## Google Sheet Layout

Each generated row uses nine columns:

| Col | Header | Description |
|-----|--------|-------------|
| A | Date (IST) | Generation timestamp |
| B | Topic/Keywords | Trend title + source URL |
| C | X Post | ≤ 260-char punchy tweet |
| D | Instagram Post | 700–1100-char story-arc post with hashtags |
| E | LinkedIn Post | 400–700-char insight-led professional post |
| F | Image URL | `=HYPERLINK(…)` to Cloudinary image |
| G | Status X | `PENDING` → `COMPLETED` / `FAILED` / `SKIPPED` |
| H | Status Instagram | `PENDING` → `COMPLETED` / `FAILED` / `NO IMAGE` / `SKIPPED` |
| I | Status LinkedIn | `PENDING` → `COMPLETED` / `FAILED` / `SKIPPED` |

**Terminal statuses** (never retried by the scheduler): `COMPLETED`, `FAILED`, `NO IMAGE`, `SKIPPED`.  
If a channel fails on a given day it stays `FAILED`; use `postChannelNow(rowIndex, platform)` in the GAS editor to backfill it manually.

## Pipeline Flow

```
1. Fetch trending topics (multi-source: HN, GNews, Dev.to, Reddit, DDG)
2. Pick persona + content pillar + hook style
3. Generate X + Instagram + LinkedIn posts via LiteLLM / OpenRouter
4. Generate image prompt, render via Cloudflare Workers AI
5. Upload image to Cloudinary → public URL
6. Append 9-column row to Google Sheet with Status = PENDING
```

## Setup

### 1. Clone and Install

```bash
git clone <repo-url>
cd social-media-content-generator
python3 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file:

```env
# Content generation (OpenRouter via LiteLLM)
OPENROUTER_API=your_openrouter_api_key
CONTENT_MODEL=openai/gpt-oss-120b:free   # comma-separated for fallback chain

# Image generation (Cloudflare Workers AI)
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell

# Image hosting (Cloudinary)
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret

# Google Sheets
GSHEET_ID=your_google_sheet_id

# Pipeline settings
POST_COUNT=3
LLM_CALL_DELAY_SECONDS=15
```

### 3. Get API Keys

| Service | URL | Notes |
|---------|-----|-------|
| OpenRouter | https://openrouter.ai/ | Free tier available; supports model fallback chain |
| Cloudflare | https://dash.cloudflare.com/ | Workers AI free tier |
| Cloudinary | https://cloudinary.com/ | Free tier (25 GB storage) |
| Buffer | https://buffer.com/ | Needed for the GAS posting script |

### 4. Google Sheets Setup

1. Create a new Google Sheet.
2. Copy the Sheet ID from the URL: `docs.google.com/spreadsheets/d/{SHEET_ID}/edit`.
3. Share the sheet with your Firebase service account email (Editor access) — find it in `serviceAccountKey.json` → `client_email`.
4. Enable the **Google Sheets API** in your GCP project.
5. On first run the pipeline writes the header row automatically.

### 5. Firebase Setup (Remote Config)

1. Create a Firebase project at [Firebase Console](https://console.firebase.google.com/).
2. Generate a service account key: **Project Settings → Service Accounts → Generate New Private Key**.
3. Save it as `serviceAccountKey.json` in the project root.
4. Optionally add config values to Firebase Remote Config for centralised management (`.env` values always take precedence).

### 6. Buffer / GAS Scheduling Setup

1. Open your Google Sheet → **Extensions → Apps Script**.
2. Paste the contents of `scripts/buffer-gscript.js`.
3. Update `CONFIG.SPREADSHEET_ID` to your sheet ID and set `BUFFER_API_KEY` in Script Properties.
4. Run `fetchChannelId()` once to verify your Buffer channel IDs, then update `CONFIG.CHANNELS` if needed.
5. Run `createDailyTrigger()` once to register the midnight IST daily trigger.

## Usage

### Generate Content

```bash
source venv/bin/activate
python3 run_bot.py
```

### Test a Single Post (with live topic fetch)

```bash
python3 scripts/test_single_post.py
```

### Test with a Custom Topic

```bash
python3 scripts/test_single_post.py --topic "FAANG hiring freeze 2025"
python3 scripts/test_single_post.py --topic "System design tips" --no-image
```

### Migrate an Existing 6-Column Sheet to the New Layout

If you have rows from before the per-channel status upgrade:

```bash
python3 scripts/migrate_sheet_to_v2.py
```

This inserts the LinkedIn Post column (copying Instagram content), shifts Image URL, expands the single Status into three per-channel columns, and maps `COMPLETED` → all `COMPLETED`, everything else → `PENDING`.

## GAS Scheduler Functions

| Function | How to use |
|----------|-----------|
| `schedulePostsToBuffer()` | Main daily trigger — posts up to 3 pending rows per channel |
| `postNow()` | Instantly post `TARGET_ROW` to all non-terminal channels |
| `postChannelNow(rowIndex, platform)` | Manual backfill for one channel, e.g. `postChannelNow(7, "instagram")` |
| `fetchChannelId()` | List all Buffer channel IDs (run once to verify config) |
| `createDailyTrigger()` | Register the midnight IST cron (run once) |

## Project Structure

```
src/
├── constants.py         # Keywords, fallback config defaults
├── config.py            # Firebase Remote Config + .env loading
├── ai_service.py        # LiteLLM multi-platform content + image prompt generation
├── gsheet_client.py     # Google Sheets client (9-column layout, per-channel status)
├── image_generator.py   # Cloudflare Workers AI + Pillow fallback
├── storage_client.py    # Cloudinary image upload
├── trend_fetcher.py     # Multi-source trending topic fetcher
├── pipeline.py          # Orchestration: fetch → generate → image → sheet
├── personas.py          # Content personas, pillars, hook styles
└── main.py              # run_bot.py entry point

scripts/
├── buffer-gscript.js        # Google Apps Script — Buffer API scheduler (paste into GAS editor)
├── test_single_post.py      # Local end-to-end test for one post
├── migrate_sheet_to_v2.py   # One-time migration: 6-col → 9-col sheet layout

run_bot.py               # Root entry point
```

## GitHub Actions (Automated Daily Runs)

The workflow runs daily at 9:00 AM IST (3:30 AM UTC).

### Required Secrets

Add these in **GitHub → Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `FIREBASE_SERVICE_ACCOUNT` | JSON content of `serviceAccountKey.json` |
| `OPENROUTER_API` | OpenRouter API key |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | Cloudflare Workers AI token |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `GSHEET_ID` | Google Sheet ID |
| `IMAGE_MODEL` | Image model (optional) |
| `CONTENT_MODEL` | Content model (optional) |
| `POST_COUNT` | Posts to generate per run (e.g. `3`) |

## Customization

### Personas and Content Pillars
Edit `src/personas.py` to add or change audience personas, content pillars (e.g. `tool_reveal`, `interview_horror_recovery`), and hook styles.

### Post Prompts
Edit `_build_prompt()` in `src/pipeline.py` to adjust the rules for any platform's post format.

### Image Style
Edit `generate_image_prompt()` in `src/ai_service.py` to change the visual aesthetic.

### Posting Schedule
Edit `CONFIG.SCHEDULE_SLOTS_WEEKDAY` / `SCHEDULE_SLOTS_WEEKEND` in `scripts/buffer-gscript.js`.

## License

MIT
