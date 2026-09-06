# Chiro Studio: researched UX upgrade

## Changes

Previously a pasted link immediately triggered one long caption response. Now it opens a four-format picker without a model call. Choosing a format shows source-retrieval and drafting progress, then delivers a draft with fixed source attribution and follow-up buttons. `/analyze` retains the immediate-caption shortcut.

Source context explicitly distinguishes public metadata from viewing footage or reading a transcript. Missing AI credentials produce labelled fill-in templates. Provider failures become actionable messages; raw payloads and credential-bearing URLs are not logged or sent to users. Rich metadata outages preserve basic oEmbed context.

## Research and decisions

- [Telegram design guidelines](https://core.telegram.org/bots/guidelines): clear onboarding and buttons for primary actions. Applied through a three-step welcome and four format choices, while retaining command shortcuts.
- [Telegram bot features](https://core.telegram.org/bots/features): inline keyboards support actions within the conversation. Applied to format changes and source navigation.
- [Telegram Bot API](https://core.telegram.org/bots/api): callback payloads allow 1–64 bytes, callbacks need acknowledgement, and copy-text buttons allow 1–256 characters. Actions are compact, signed, user-bound and expire after 24 hours. The copy button copies the opening hook; captions remain available through Telegram's normal copy interaction.
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs): GPT-OSS 20B/120B support strict JSON schemas. These models use a required-field schema; other configured models retain JSON-object mode. Local validation rejects missing, oversized and truncated output regardless of model. Structured outputs validate shape, not factual correctness.
- [Groq API reference](https://console.groq.com/docs/api-reference): generation has an explicit output budget. Reasoning settings are only sent for the supported GPT-OSS models. This implementation returns complete validated drafts rather than streaming partial JSON; stage progress provides feedback during the wait.

These are design decisions based on platform capabilities, not evidence of measured retention gains. No live user research or generation-quality benchmark has been run.

## Example interaction

1. Paste one YouTube video link.
2. Choose Caption, Hook ideas, Reel script or Carousel outline.
3. See reading progress, then the title/channel and the metadata-only limitation.
4. Receive a labelled draft with a review note and source credit.
5. Copy the opening hook or choose another format. Each selection makes a fresh generation request.

## Upgrade and verification

The manual **Deploy Chiro Studio** GitHub Actions workflow runs tests, transfers the existing bot/provider secrets to encrypted production variables, builds and deploys, then verifies the live version and webhook authentication before registering Telegram. It preserves pending updates and does not send a test message. It does not run the legacy fitness workflows.

Deployment setup uses repository variables `CHIRO_VERCEL_ORG_ID`, `CHIRO_VERCEL_PROJECT_ID`, `CHIRO_WEBHOOK_URL` and secrets `CHIRO_VERCEL_TOKEN`, `CHIRO_WEBHOOK_SECRET`. Refresh the deployment credential if it expires or is revoked. Never put token values in workflow files. Only `public/` is published as static content; application source is packaged into the function.

- Runtime: Node 20.3 or newer; no new npm dependencies.
- Required: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_WEBHOOK_SECRET`. Missing values return 503; wrong webhook secrets return 401. Only the configured user's private chat is served.
- Set `GROQ_API_KEY` for AI drafts. Otherwise labelled starter templates are intentional.
- After deployment, re-run `npm run set-webhook` with the production origin to subscribe to `message` and `callback_query`. Edited messages no longer generate drafts. Pending updates are preserved by default.
- Run `npm test`. Tests mock external APIs and exercise complete webhook request-to-response flows without Telegram messages or provider credits.
- Before production use, manually verify `/start`, a pasted link, all four buttons, copy hook and source navigation in your own Telegram chat. Assess actual generated drafts for usefulness and unsupported claims.

## Limits and next priorities

This remains a private metadata-to-content assistant. It has no transcript ingestion, video understanding, medical fact-checking, saved draft database, cross-instance rate limiting, durable queue or cancellation. Prompt restrictions cannot guarantee factual correctness.

Duplicate-update suppression and the busy indicator are best-effort within a warm serverless instance and reset on cold starts. Duplicate IDs expire after five minutes. Signed buttons survive cold starts. Requests have a 22-second shared network deadline and up to five seconds for an error response; slow providers may require another attempt. Exactly-once generation/delivery is not guaranteed.

Next, build a reviewed evaluation set across the four formats, then add saved drafts and durable jobs if usage justifies storage. Measure time to first useful draft, completion rate and how often outputs require substantial editing. Add opt-in feedback with a clear retention policy. Do not describe the bot as clinically validated or as having watched source footage.

## Version 0.3.0

Added Story sequences, title ideas, per-draft Hindi/Hinglish/shortening, reply-based rewriting, text export and a verified command menu. All 35 mocked tests pass. Reply workflows accept complete drafts from this bot in the configured private chat, not forwarded drafts or other senders. Exports preserve source and review notes. Provider-generated translations and rewrites still need editorial review; no multilingual quality benchmark has been completed.
