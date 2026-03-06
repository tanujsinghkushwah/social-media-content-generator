# Social Media Content Generator

Automated pipeline for generating viral tech content for social media platforms. Generates post text + images and logs them to a Google Sheet for review and scheduling.

## Features

- **Trending Topic Discovery**: Fetches trending tech topics via web search (DuckDuckGo) with fallback to curated keywords
- **AI-Powered Content**: Uses LiteLLM with OpenRouter for text generation
- **Image Generation**: Creates engaging images via Cloudflare Workers AI (Flux model) with Pillow fallback
- **Image Hosting**: Uploads images to imgBB (free, no card required) for public URLs
- **Google Sheets Logging**: Records all generated content with timestamps, topics, content, image URLs, and status
- **Configurable Post Count**: Generate multiple posts per run via `POST_COUNT` setting
- **Rate Limit Friendly**: Configurable delays between LLM calls to respect free tier limits
- **GitHub Actions**: Automated daily runs at 9 AM IST

## Pipeline Flow

```
1. Fetch trending topics (web search + fallback keywords)
2. Generate viral post text via LiteLLM/OpenRouter
3. Generate image prompt via LiteLLM
4. Generate image via Cloudflare Workers AI
5. Upload image to imgBB → get public URL
6. Append row to Google Sheet: [Date, Topic, Content, Image URL, Status]
```

## Setup

### 1. Clone and Install

```bash
git clone <repo-url>
cd social-media-content-generator
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file:

```env
# Content generation (OpenRouter via LiteLLM)
OPENROUTER_API=your_openrouter_api_key
CONTENT_MODEL=arcee-ai/trinity-large-preview:free

# Image generation (Cloudflare Workers AI)
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell

# Image hosting (imgBB - free)
IMGBB_API_KEY=your_imgbb_api_key

# Google Sheets
GSHEET_ID=your_google_sheet_id

# Pipeline settings
POST_COUNT=3
LLM_CALL_DELAY_SECONDS=15
```

### 3. Get API Keys

| Service | URL | Notes |
|---------|-----|-------|
| OpenRouter | https://openrouter.ai/ | Free tier available |
| Cloudflare | https://dash.cloudflare.com/ | Workers AI free tier |
| imgBB | https://api.imgbb.com/ | Free, email signup only |

### 4. Google Sheets Setup

1. Create a new Google Sheet
2. Copy the Sheet ID from the URL: `docs.google.com/spreadsheets/d/{SHEET_ID}/edit`
3. Share the sheet with your Firebase service account email (Editor access)
   - Find the email in `serviceAccountKey.json` → `client_email`
4. Enable **Google Sheets API** in your GCP project

### 5. Firebase Setup (for Remote Config)

1. Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
2. Generate a service account key: Project Settings → Service Accounts → Generate New Private Key
3. Save as `serviceAccountKey.json` in project root
4. (Optional) Add config values to Firebase Remote Config for centralized management

## Project Structure

```
src/
├── __init__.py          # Package initialization
├── constants.py         # Keywords, default config values
├── config.py            # Firebase Remote Config + env var loading
├── ai_service.py        # LiteLLM wrapper for text generation
├── image_generator.py   # Cloudflare Workers AI + Pillow fallback
├── storage_client.py    # imgBB image upload client
├── gsheet_client.py     # Google Sheets client with auto-headers
├── trend_fetcher.py     # DuckDuckGo search for trending topics
├── pipeline.py          # Main pipeline orchestrating all services
└── main.py              # Entry point

run_bot.py               # Root-level entry point
```

## Usage

### Run Locally

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\Activate.ps1  # Windows PowerShell

# Run the pipeline
python run_bot.py
```

### Output

The pipeline generates rows in your Google Sheet with columns:
- **Date (IST)**: Timestamp when generated
- **Topic/Keywords**: The topic used for generation
- **Post Content**: The generated viral post text
- **Image URL**: Clickable link to view the image on imgBB
- **Status**: PENDING (ready to post) / FAILED (generation issue)

## GitHub Actions (Automated Daily Runs)

The workflow runs daily at 9:00 AM IST (3:30 AM UTC).

### Required Secrets

Add these in GitHub → Settings → Secrets and variables → Actions:

| Secret | Description |
|--------|-------------|
| `FIREBASE_SERVICE_ACCOUNT` | JSON content of `serviceAccountKey.json` |
| `OPENROUTER_API` | OpenRouter API key |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | Cloudflare Workers AI token |
| `IMAGE_MODEL` | Image model (optional) |
| `CONTENT_MODEL` | Content model (optional) |
| `GSHEET_ID` | Google Sheet ID |
| `IMGBB_API_KEY` | imgBB API key |
| `POST_COUNT` | Number of posts to generate (e.g., `6`) |

### Manual Trigger

You can also trigger the workflow manually from GitHub Actions → Run Content Generator → Run workflow.

## Customization

### Keywords (Fallback Topics)

Edit `src/constants.py` → `KEYWORDS` list to customize fallback topics when web search returns no results.

### Post Prompts

Edit `src/pipeline.py` → `_generate_post_content()` to customize the viral post generation prompt.

### Image Prompts

Edit `src/ai_service.py` → `generate_image_prompt()` to customize the image generation style.

### Schedule

Edit `.github/workflows/bot.yml` → `cron` expression to change the run schedule.

## License

MIT
