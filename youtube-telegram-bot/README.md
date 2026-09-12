# Chiro Studio — YouTube + Instagram → Telegram

Private Telegram-first assistant for a chiropractic-focused social account. Paste a YouTube/Shorts link to create original captions, hooks, Reel scripts, carousel/story ideas, or paste a public Instagram Reel URL to queue an on-demand yt-dlp download and receive the MP4 back in the same Telegram chat.

## Commands

```text
/analyze <youtube-url>
/hooks <youtube-url>
/reel <youtube-url>
/carousel <youtube-url>
/stories <youtube-url>
/titles <youtube-url>
/hindi <youtube-url>
/hinglish <youtube-url>
/short <youtube-url>
/download <youtube-or-instagram-reel-or-direct-media-url>
/help
/privacy
```

For Instagram, the fastest workflow is simply to paste one public Reel URL. The bot validates the URL, dispatches the GitHub Actions worker, and returns the downloaded MP4 to the originating private chat. Downloads are intended for media you own or are authorized to reuse.

## Architecture

```text
Telegram
   │
   ├── YouTube content request ──> Vercel webhook ──> YouTube metadata ──> Groq ──> Telegram
   │
   └── public Instagram Reel URL / authorized download request
          │
          └── GitHub Actions workflow_dispatch
                 │
                 └── yt-dlp + ffmpeg worker
                        │
                        ├── validate public source
                        ├── 720p
                        ├── fallback 480p
                        └── fallback 360p
                               │
                               └── Telegram MP4
```

The download worker is `.github/workflows/youtube_download_worker.yml`. Despite the legacy filename, it now handles supported public YouTube URLs and public Instagram Reel URLs. It runs only on demand and has no schedule.

## yt-dlp guardrails

The worker uses upstream `yt-dlp/yt-dlp` and deliberately does not configure Instagram/YouTube cookies, account credentials, proxies, or geo-bypass behavior. It rejects or fails closed for:

- private/sign-in-gated media
- members/subscriber-only or premium-only videos
- Instagram URLs that are not `/reel/...` or `/reels/...`
- live streams
- videos above the configured duration limit

It uses `--no-playlist` behavior and downloads at most one video. The default maximum duration is 15 minutes.

Telegram's hosted Bot API accepts bot video/file uploads up to 50 MB, so the worker keeps a 49 MB safety ceiling and steps down from 720p to 480p/360p when needed.

## Required environment variables

Webhook/runtime:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_ID
TELEGRAM_WEBHOOK_SECRET
GROQ_API_KEY
GH_ACTIONS_TOKEN
GITHUB_REPO
GITHUB_DEFAULT_BRANCH
```

YouTube metadata can reuse the existing credentials:

```text
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

`YOUTUBE_API_KEY` remains an optional alternative.

The GitHub worker itself reuses repository secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_ID
```

GitHub Actions secrets and Vercel environment variables are separate stores. If the webhook is deployed on Vercel, `GH_ACTIONS_TOKEN` must also be configured in that Vercel project; never commit its value.

## Instagram Reel flow

```text
1. Send https://www.instagram.com/reel/<shortcode>/ to the private Telegram bot.
2. The Vercel webhook verifies the Telegram webhook secret and allowed user.
3. The webhook triggers `youtube_download_worker.yml` with the normalized Reel URL and originating chat ID.
4. GitHub Actions installs the current pre-release yt-dlp runtime plus ffmpeg.
5. yt-dlp attempts the public Reel without cookies or login credentials.
6. The worker posts the MP4 to the same Telegram chat if it can keep the file below the Bot API upload limit.
7. The GitHub runner's temporary directory is deleted automatically when the job ends.
```

## Development

```bash
cd youtube-telegram-bot
npm test
```

The JavaScript tests cover YouTube URL parsing, OAuth metadata behavior, Telegram experience logic, download routing, and GitHub Actions dispatch construction. The Python worker can be syntax-checked with:

```bash
python -m py_compile scripts/download_youtube.py
```

## Deployment

Deploy the repository with the Vercel Root Directory set to:

```text
youtube-telegram-bot
```

Then configure the environment variables and register `${WEBHOOK_URL}/api/telegram` using:

```bash
npm run set-webhook
```

The repository's old automatic fitness workflows remain disabled.
