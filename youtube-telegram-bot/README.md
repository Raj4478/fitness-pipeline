# YouTube → Telegram Chiropractic Content Bot

Standalone webhook service for a new chiropractic-themed social account. It does **not** re-enable any of the repository's disabled fitness/Twitter schedules.

## What it does

Send a YouTube video or Shorts link to the Telegram bot and it returns:

- video title + source channel
- an original hook
- an original chiropractic/posture/mobility caption
- configurable hashtags
- a suggested content angle
- a medical-safety note
- a source-attribution line

Commands:

- `/analyze <youtube-url>` — analyze explicitly (plain pasted YouTube links also work)
- `/download <direct-media-url>` — relay an allowlisted HTTPS video you own/have permission to use
- `/help`

## Download policy

This service intentionally does **not** extract downloadable media from YouTube URLs. YouTube links are analysis-only. `/download` accepts only direct `.mp4`, `.mov`, `.m4v`, or `.webm` HTTPS URLs whose hostname is listed in `DOWNLOAD_ALLOWLIST_HOSTS`.

This keeps the downloader useful for your own CDN/storage/original media without bypassing YouTube access restrictions.

Telegram can fetch a permitted video from an HTTP(S) URL directly. Telegram's hosted Bot API has size limits, so large media should be stored/uploaded through a suitable media pipeline instead of proxied through this function.

## Architecture

`Telegram → Vercel /api/telegram → YouTube metadata → Groq → Telegram reply`

Metadata depth:

1. Always: YouTube oEmbed title, channel and thumbnail.
2. With `YOUTUBE_API_KEY`: YouTube Data API description, tags, publication date, duration and view count.

The service does not scrape YouTube pages or attempt to obtain private/transcript data from arbitrary third-party videos.

## Environment variables

Copy `.env.example` and configure:

- `TELEGRAM_BOT_TOKEN` — token from BotFather
- `TELEGRAM_ALLOWED_USER_ID` — strongly recommended; makes the bot private
- `TELEGRAM_WEBHOOK_SECRET` — random secret used to authenticate Telegram webhook calls
- `WEBHOOK_URL` — deployed Vercel origin, e.g. `https://your-project.vercel.app`
- `GROQ_API_KEY` — caption/hashtag generation
- `GROQ_MODEL` — defaults to `openai/gpt-oss-120b`
- `YOUTUBE_API_KEY` — optional but recommended for richer analysis
- `ACCOUNT_NICHE`, `ACCOUNT_TONE`, `HASHTAG_COUNT` — content strategy controls
- `DOWNLOAD_ALLOWLIST_HOSTS` — comma-separated media hosts you control/have permission to relay

## Deploy on Vercel

Set the Vercel project Root Directory to `youtube-telegram-bot` if deploying this folder from the parent repository.

After the production URL and environment variables are configured, register the Telegram webhook from this directory:

```bash
npm run set-webhook
```

The command registers `${WEBHOOK_URL}/api/telegram` and supplies `TELEGRAM_WEBHOOK_SECRET` to Telegram.

## Content safety

The Groq prompt is deliberately conservative for health-adjacent content:

- no diagnosis from a clip
- no guaranteed relief/cure claims
- no invented medical facts
- source attribution included
- persistent/severe symptoms are directed toward qualified professional assessment

## Tests

```bash
npm test
```

Tests cover YouTube URL recognition and the rights-gated download policy.
