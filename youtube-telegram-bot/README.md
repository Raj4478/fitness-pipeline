# Chiro Studio — YouTube → Telegram

Private Telegram-first assistant for a chiropractic-focused social account. Paste a YouTube/Shorts link to create original captions, hooks, Reel scripts, carousel/story ideas, or—when you own the media or have permission to reuse it—request an on-demand video download.

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
/download <youtube-or-direct-media-url>
/help
/privacy
```

Using `/download` is intended only for media you own or are authorized to reuse.

## Architecture

```text
Telegram
   │
   ├── content request ──> Vercel webhook ──> YouTube metadata ──> Groq ──> Telegram
   │
   └── /download YouTube URL
          │
          └── GitHub Actions workflow_dispatch
                 │
                 └── yt-dlp + ffmpeg worker
                        │
                        ├── 720p
                        ├── fallback 480p
                        └── fallback 360p
                               │
                               └── Telegram MP4
```

The download worker is `.github/workflows/youtube_download_worker.yml` and runs **only on demand**. It has no schedule and does not re-enable the legacy fitness/Twitter automation.

## yt-dlp guardrails

The worker uses upstream `yt-dlp/yt-dlp` and deliberately does not configure cookies, account credentials, proxies, or geo-bypass behavior. It rejects:

- private/sign-in-gated videos
- members/subscriber-only videos
- premium-only videos
- live streams
- videos above the configured duration limit

It uses `--no-playlist` behavior and downloads at most one video. The default maximum duration is 15 minutes.

Telegram's hosted Bot API currently accepts bot video/file uploads up to 50 MB, so the worker keeps a 49 MB safety ceiling and steps down from 720p to 480p/360p when needed.

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

## Content generation

Default niche:

```text
chiropractic education, posture, mobility and spine health
```

Generated health-adjacent copy is instructed to avoid diagnosis, guaranteed relief/cure claims, invented medical facts, and individualized medical advice.

## Development

```bash
cd youtube-telegram-bot
npm test
```

The tests cover YouTube URL parsing, OAuth metadata behavior, Telegram experience logic, download routing, and GitHub Actions dispatch construction. The Python download worker is syntax-checked in CI.

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
