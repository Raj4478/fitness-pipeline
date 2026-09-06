import { createHmac, timingSafeEqual } from 'node:crypto';

export const FORMATS = Object.freeze({
  caption: { label: 'Caption', instruction: 'Write a concise Instagram caption, 80–140 words, with one useful question or save/share invitation. No engagement bait.' },
  hooks: { label: 'Hook ideas', instruction: 'Write five numbered, distinct opening hooks with a short angle for each. No invented statistics, fear-based claims or clickbait medical promises.' },
  reel: { label: 'Reel script', instruction: 'Write an original 30-second Reel outline in three labelled sections: 0–3s Hook, 3–23s Main idea, 23–30s Close. Suggest original shots to create, without claiming they appear in the source video.' },
  carousel: { label: 'Carousel outline', instruction: 'Write five numbered slides: opening question, context, educational point, thoughtful takeaway, and closing question. Each slide needs a short title and at most two sentences. Do not invent clinical facts.' }
});

export const HELP = `Welcome to Chiro Studio 👋\n\nTurn a YouTube link into an original social draft.\n\n1. Paste one video or Shorts link.\n2. Choose Caption, Hook ideas, Reel script or Carousel.\n3. Review your draft, then copy what you need.\n\nI use the public title and description where available. Video footage and transcripts are not analysed.\n\nShortcuts:\n/analyze <link> — draft a caption immediately\n/hooks <link> — five opening ideas\n/reel <link> — a 30-second script\n/carousel <link> — a five-slide outline\n/help — this guide\n/privacy — how your input is used\n/download <direct-media-url> — relay your permitted media\n\nDrafts are for editorial review before publication.`;
export const PRIVACY = 'Chiro Studio is a private content assistant. A submitted YouTube URL is used to retrieve public metadata. That metadata is sent to Groq when AI generation is configured. This service does not create a conversation-history database; messages remain in Telegram, and hosting/provider logs and retention policies still apply. Buttons expire after 24 hours. Avoid sending personal health information. Nothing is published to a social account automatically.';

// Signed stateless actions survive serverless cold starts without keeping chats in RAM.
export function makeAction(videoId, format, userId, secret, now = Date.now()) {
  if (!Object.hasOwn(FORMATS, format) || !/^[\w-]{6,20}$/.test(videoId)) throw new Error('invalid_action');
  const expiry = Math.floor(now / 1000 + 86400).toString(36);
  const payload = `c:${videoId}:${format}:${expiry}`;
  const mac = createHmac('sha256', secret).update(`${userId}:${payload}`).digest('base64url').slice(0, 12);
  return `${payload}:${mac}`;
}

export function readAction(data, userId, secret, now = Date.now()) {
  const parts = String(data || '').split(':');
  if (parts.length !== 5 || parts[0] !== 'c') return null;
  const [, videoId, format, expiry, signature] = parts;
  if (!Object.hasOwn(FORMATS, format) || !/^[\w-]{6,20}$/.test(videoId) || !/^[a-z0-9]+$/.test(expiry)) return null;
  const seconds = parseInt(expiry, 36);
  if (!Number.isFinite(seconds) || seconds < now / 1000 || seconds > now / 1000 + 86401) return null;
  const payload = parts.slice(0, 4).join(':');
  const expected = createHmac('sha256', secret).update(`${userId}:${payload}`).digest('base64url').slice(0, 12);
  if (Buffer.byteLength(signature) !== Buffer.byteLength(expected) || !timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  return { videoId, format };
}

export function formatKeyboard(videoId, userId, secret, now = Date.now(), content = null) {
  const buttons = Object.entries(FORMATS).map(([format, { label }]) => ({
    text: label, callback_data: makeAction(videoId, format, userId, secret, now)
  }));
  const rows = [buttons.slice(0, 2), buttons.slice(2)];
  // Telegram CopyTextButton is limited to 256 characters. Never silently truncate a caption.
  if (content?.hook && content.hook.length <= 256) rows.push([{ text: 'Copy opening hook', copy_text: { text: content.hook } }]);
  rows.push([{ text: 'Open source video', url: `https://www.youtube.com/watch?v=${videoId}` }]);
  return { inline_keyboard: rows };
}

export function sourceSummary(metadata) {
  const context = metadata.description ? 'Public title and description' : 'Public title and channel only';
  return `🎬 ${String(metadata.title).slice(0, 180)}\nBy ${String(metadata.channelTitle || 'Unknown creator').slice(0, 100)}\n\nSource context: ${context}. Video footage and transcript have not been analysed.`;
}

export function formatDraft(metadata, content, format) {
  return [
    `${FORMATS[format].label.toUpperCase()} · ${content.generationMode === 'template' ? 'STARTER TEMPLATE' : 'AI DRAFT'}`,
    content.hook, content.caption, content.hashtags.join(' '),
    `Editorial angle: ${content.angle}`,
    `Review note: ${content.caution}`,
    `Source inspiration: ${String(metadata.channelTitle || 'YouTube creator').slice(0, 100)}\n${metadata.canonicalUrl}`,
    'Long-press to copy. Use the buttons for another format.'
  ].join('\n\n');
}

export function firstUrl(text) {
  return String(text).match(/https?:\/\/[^\s<>]+/i)?.[0]?.replace(/[),.;!?]+$/, '') || '';
}
