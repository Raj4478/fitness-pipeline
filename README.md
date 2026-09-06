# Chiro YouTube Telegram Bot

A private, Telegram-first content assistant for a chiropractic-focused social account.

Send the bot a YouTube video or Shorts link and it analyzes the available public video metadata, then generates original social copy tailored to chiropractic education, posture, mobility, and spine-health content.

## What it does

- Accepts YouTube and YouTube Shorts links through Telegram
- Identifies the source video and channel
- Uses YouTube metadata for content context
- Reuses the repository's existing YouTube OAuth credentials for richer metadata when available
- Uses Groq to generate an original hook, caption, hashtags, and content angle
- Adds source attribution
- Uses conservative, non-diagnostic language for health-adjacent content
- Restricts the Telegram bot to the configured user ID
- Supports permitted direct-media relay for media you own or are authorized to reuse

## Telegram commands

```text
/analyze <youtube-url>
/download <permitted-direct-media-url>
/help
```

You can also paste a YouTube URL directly without using `/analyze`.

## Architecture

```text
Telegram
   │
   ▼
Webhook API
   │
   ├── YouTube oEmbed / YouTube Data API
   │
   ├── Groq content generation
   │
   └── Telegram response
```

The production bot service lives in:

```text
youtube-telegram-bot/
```

## Existing credentials reused

The service is designed to reuse the repository's existing secret names:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_ID
GROQ_API_KEY
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

Additional deployment-specific configuration may include:

```text
TELEGRAM_WEBHOOK_SECRET
WEBHOOK_URL
GROQ_MODEL
ACCOUNT_NICHE
ACCOUNT_TONE
HASHTAG_COUNT
DOWNLOAD_ALLOWLIST_HOSTS
```

Never commit secret values to the repository.

## Content profile

Default niche:

```text
chiropractic education, posture, mobility and spine health
```

The generator is intentionally instructed to avoid:

- diagnosing a person from a video clip
- guaranteed treatment or cure claims
- invented medical facts
- presenting educational social content as individualized medical advice

## Download policy

The bot does not extract arbitrary video files from YouTube.

`/download` is limited to explicitly permitted direct media URLs from allowlisted hosts for media you own or have permission to reuse.

## Local development

```bash
cd youtube-telegram-bot
npm test
```

The Node.js test suite covers YouTube URL parsing, metadata authentication behavior, and download-policy guardrails.

## Deployment

The bot is designed as a webhook service and can be deployed with the repository root configured to:

```text
youtube-telegram-bot
```

After deployment, configure the environment variables in the hosting platform and register the deployed `/api/telegram` endpoint as the Telegram webhook.

## Legacy pipeline

This repository originally contained the FitFacts fitness-content pipeline. Its automatic GitHub Actions schedules have been disabled. The chiropractic YouTube/Telegram bot is the active direction of the project.

## Status

- Telegram credentials: validated
- Groq credentials: validated
- YouTube OAuth refresh flow: validated
- Bot tests: passing
- Legacy automatic fitness workflows: disabled
