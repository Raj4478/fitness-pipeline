import { createHmac, timingSafeEqual } from 'node:crypto';

export const VARIANTS = Object.freeze({ short: 'Make a substantially shorter draft while preserving necessary context and caveats.', hindi: 'Write the draft in natural Hindi using Devanagari. Preserve names and source credit.', hinglish: 'Write in natural conversational Hinglish using Latin script. Preserve source credit.' });
export function validActionFormat(value) {
  const [format, variant, extra] = String(value).split('~');
  return Object.hasOwn(FORMATS, format) && extra === undefined && (variant === undefined || Object.hasOwn(VARIANTS, variant));
}
export const FORMATS = Object.freeze({
  caption: { label: 'Caption', instruction: 'Write a concise Instagram caption, 80–140 words, with one useful question or save/share invitation. No engagement bait.' },
  hooks: { label: 'Hook ideas', instruction: 'Write five numbered, distinct opening hooks with a short angle for each. No invented statistics, fear-based claims or clickbait medical promises.' },
  reel: { label: 'Reel script', instruction: 'Write an original 30-second Reel outline in three labelled sections: 0–3s Hook, 3–23s Main idea, 23–30s Close. Suggest original shots to create, without claiming they appear in the source video.' },
  carousel: { label: 'Carousel outline', instruction: 'Write five numbered slides: opening question, context, educational point, thoughtful takeaway, and closing question. Each slide needs a short title and at most two sentences. Do not invent clinical facts.' },
  stories: { label: 'Story sequence', instruction: 'Write three Instagram Story frames: an opening question, one contextual takeaway, and a poll with two neutral options. Suggest original visuals to create; never claim to have seen source footage.' },
  titles: { label: 'Title ideas', instruction: 'Write five distinct concise original titles and one short thumbnail-text suggestion for each. Avoid invented facts, clinical promises, fear and clickbait.' }
});

export const HELP = `Welcome to Chiro Studio 👋\n\nTurn a YouTube link into an original social draft.\n\n1. Paste one video or Shorts link.\n2. Choose Caption, Hooks, Reel, Carousel, Stories or Titles.\n3. Review your draft, then copy what you need.\n\nI use the public title and description where available. Video footage and transcripts are not analysed.\n\nShortcuts:\n/analyze <link> — draft a caption immediately\n/hooks <link> — five opening ideas\n/reel <link> — a 30-second script\n/carousel <link> — a five-slide outline\n/stories <link> — three Story frames\n/titles <link> — title and thumbnail ideas\n/hindi <link> — Hindi caption\n/hinglish <link> — Hinglish caption\n/short <link> — short caption\n/rewrite <instructions> — reply to a draft to edit it\n/export — reply to a draft for a text file\n/examples — sample workflows\n/help — this guide\n/privacy — how your input is used\n/download <youtube-or-direct-media-link> — download/relay media you own or are authorized to reuse. YouTube requests run through the on-demand yt-dlp worker.\n\nDrafts are for editorial review before publication.`;
export const PRIVACY = 'Chiro Studio is a private content assistant. A submitted YouTube URL is used to retrieve public metadata. That metadata is sent to Groq when AI generation is configured. Rewrites also send the draft you reply to and your editing instructions. Exports are generated in memory and sent to your Telegram chat. This service does not create a conversation-history database; messages remain in Telegram, and hosting/provider logs and retention policies still apply. Buttons expire after 24 hours. Avoid sending personal health information. Nothing is published to a social account automatically.';

// Signed stateless actions survive serverless cold starts without keeping chats in RAM.
export function makeAction(videoId, format, userId, secret, now = Date.now()) {
  if (!validActionFormat(format) || !/^[\w-]{6,20}$/.test(videoId)) throw new Error('invalid_action');
  const expiry = Math.floor(now / 1000 + 86400).toString(36);
  const payload = `c:${videoId}:${format}:${expiry}`;
  const mac = createHmac('sha256', secret).update(`${userId}:${payload}`).digest('base64url').slice(0, 12);
  return `${payload}:${mac}`;
}

export function readAction(data, userId, secret, now = Date.now()) {
  const parts = String(data || '').split(':');
  if (parts.length !== 5 || parts[0] !== 'c') return null;
  const [, videoId, format, expiry, signature] = parts;
  if (!validActionFormat(format) || !/^[\w-]{6,20}$/.test(videoId) || !/^[a-z0-9]+$/.test(expiry)) return null;
  const seconds = parseInt(expiry, 36);
  if (!Number.isFinite(seconds) || seconds < now / 1000 || seconds > now / 1000 + 86401) return null;
  const payload = parts.slice(0, 4).join(':');
  const expected = createHmac('sha256', secret).update(`${userId}:${payload}`).digest('base64url').slice(0, 12);
  if (Buffer.byteLength(signature) !== Buffer.byteLength(expected) || !timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  const [base, variant] = format.split('~');
  return { videoId, format: base, ...(variant ? { variant } : {}) };
}

export function formatKeyboard(videoId, userId, secret, now = Date.now(), content = null) {
  const buttons = Object.entries(FORMATS).map(([format, { label }]) => ({
    text: label, callback_data: makeAction(videoId, format, userId, secret, now)
  }));
  const rows = [];
  for (let i = 0; i < buttons.length; i += 2) rows.push(buttons.slice(i, i + 2));
  if (content) {
    rows.push(...[['short'], ['hindi', 'hinglish']].map(group => group.map(variant => ({
      text: { short: 'Shorter version', hindi: 'Hindi', hinglish: 'Hinglish' }[variant],
      callback_data: makeAction(videoId, `${content.format || 'caption'}~${variant}`, userId, secret, now)
    }))));
  }
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
    ...(content.variant ? [`Style: ${content.variant}`] : []),
    content.hook, content.caption, content.hashtags.join(' '),
    `Editorial angle: ${content.angle}`,
    `Review note: ${content.caution}`,
    `Source inspiration: ${String(metadata.channelTitle || 'YouTube creator').slice(0, 100)}\n${metadata.canonicalUrl}`,
    'Reply with /rewrite and your instructions to edit this draft, or /export for a text file.'
  ].join('\n\n');
}

export function firstUrl(text) {
  return String(text).match(/https?:\/\/[^\s<>]+/i)?.[0]?.replace(/[),.;!?]+$/, '') || '';
}

export const EXAMPLES = 'Paste a YouTube link to choose a format.\n\nFor a Hindi caption: /hindi followed by your link.\nTo edit: reply to a generated draft with /rewrite Make this friendlier and finish with a question.\nTo save: reply to a draft with /export.\nTo download authorized media: /download followed by the YouTube or direct media link.\n\nLanguage and length choices apply to that draft only. They are not saved as account preferences.';
export const COMMANDS = [
  ['start', 'Open Chiro Studio'], ['analyze', 'Create a caption from a YouTube link'],
  ['hooks', 'Create opening hooks'], ['reel', 'Create a Reel script'], ['carousel', 'Create slide outlines'],
  ['stories', 'Create three Story frames'], ['titles', 'Create title and thumbnail ideas'],
  ['hindi', 'Create a Hindi caption'], ['hinglish', 'Create a Hinglish caption'], ['short', 'Create a shorter caption'],
  ['download', 'Download authorized YouTube/media'],
  ['rewrite', 'Reply to a draft with editing instructions'], ['export', 'Reply to a draft to download a text file'],
  ['examples', 'See example workflows'], ['help', 'Show all features'], ['privacy', 'How your input is used']
].map(([command, description]) => ({ command, description }));
export function repliedDraft(message, token) {
  const reply = message.reply_to_message;
  if (!reply?.from?.is_bot || String(reply.from.id) !== token.split(':')[0] || reply.forward_origin) return null;
  const text = reply.text || '';
  const format = Object.entries(FORMATS).find(([, value]) => text.startsWith(value.label.toUpperCase() + ' · '))?.[0];
  const source = text.match(/Source inspiration: [^\n]*\n(https:\/\/www\.youtube\.com\/watch\?v=[\w-]{6,20})(?:\n|$)/)?.[1];
  return format && source && text.length <= 3900 ? { format, source, text } : null;
}
