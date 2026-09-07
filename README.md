# Chiro YouTube Telegram Bot

A private Telegram-first assistant for a chiropractic-focused social account.

Send a YouTube video or Shorts link to generate original captions, hooks, Reel scripts, carousel/story ideas, or—when you own the media or have permission to reuse it—request an on-demand video download.

## What it does

- Accepts YouTube and Shorts links through Telegram
- Uses YouTube public metadata for content context
- Reuses the existing YouTube OAuth credentials
- Uses Groq for original chiropractic/posture/mobility social drafts
- Restricts the Telegram bot to the configured user ID
- Supports `/download <youtube-url>` through an on-demand upstream `yt-dlp` worker
- Supports allowlisted direct-media relay
- Keeps the legacy fitness/Twitter schedules disabled

## Telegram commands

```text
/analyze <youtube-url>
/hooks <youtube-url>
/reel <youtube-url>
/carousel <youtube-url>
/stories <youtube-url>
/titles <youtube-url>
/download <youtube-or-direct-media-url>
/help
```

Using `/download` is intended only for media you own or are authorized to reuse.

## Architecture

```text
Content:
Telegram → Vercel webhook → YouTube metadata → Groq → Telegram

Authorized download:
Telegram /download → Vercel webhook → GitHub Actions workflow_dispatch
                  → yt-dlp + ffmpeg → MP4 → Telegram
```

The download workflow is manual/on-demand only. There is no cron or polling trigger.

## yt-dlp worker

The worker:

- uses upstream `yt-dlp/yt-dlp`
- does not configure cookies, login credentials, proxies, or geo bypass
- rejects private/sign-in-gated, members-only, premium-only, and live content
- uses no-playlist behavior and downloads one video only
- defaults to a 15-minute maximum duration
- prefers 720p and falls back to 480p/360p
- enforces a 49 MB ceiling so the resulting file can fit Telegram's hosted Bot API upload limit

## Existing credentials reused

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_ID
GROQ_API_KEY
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
GH_ACTIONS_TOKEN
```

The webhook also uses:

```text
TELEGRAM_WEBHOOK_SECRET
GITHUB_REPO
GITHUB_DEFAULT_BRANCH
```

GitHub Actions secrets and Vercel environment variables are separate stores. Never commit secret values.

## Project location

The active service lives in:

```text
youtube-telegram-bot/
```

See [`youtube-telegram-bot/README.md`](youtube-telegram-bot/README.md) for deployment, commands, download guardrails, and environment configuration.

## Local development

```bash
cd youtube-telegram-bot
npm test
```

## Legacy pipeline

This repository originally contained the FitFacts fitness-content pipeline. Its automatic GitHub Actions schedules remain disabled.
