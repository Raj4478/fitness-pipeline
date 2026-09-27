import { createHmac, timingSafeEqual } from 'node:crypto';

export const REEL_MOODS = Object.freeze({
  peaceful: { label: 'Peaceful 🌙', description: 'slow, calming, reflective' },
  devotional: { label: 'Bhakti 🙏', description: 'warm, devotional, reverent' },
  healing: { label: 'Healing 🌿', description: 'gentle, reassuring, grounded' },
  motivational: { label: 'Motivational 🔥', description: 'energetic, practical, uplifting' },
  reflective: { label: 'Reflective 🪷', description: 'thoughtful, contemplative, introspective' },
  joyful: { label: 'Joyful ✨', description: 'bright, grateful, celebratory' }
});

function sign(payload, userId, secret) {
  return createHmac('sha256', secret).update(`${userId}:${payload}`).digest('base64url').slice(0, 12);
}

export function makeReelMoodAction(mood, userId, secret, now = Date.now()) {
  if (!Object.hasOwn(REEL_MOODS, mood)) throw new Error('invalid_reel_mood');
  const expiry = Math.floor(now / 1000 + 86400).toString(36);
  const payload = `r:${mood}:${expiry}`;
  return `${payload}:${sign(payload, userId, secret)}`;
}

export function readReelMoodAction(data, userId, secret, now = Date.now()) {
  const parts = String(data || '').split(':');
  if (parts.length !== 4 || parts[0] !== 'r') return null;
  const [, mood, expiry, signature] = parts;
  if (!Object.hasOwn(REEL_MOODS, mood) || !/^[a-z0-9]+$/.test(expiry)) return null;
  const seconds = parseInt(expiry, 36);
  if (!Number.isFinite(seconds) || seconds < now / 1000 || seconds > now / 1000 + 86401) return null;
  const payload = parts.slice(0, 3).join(':');
  const expected = sign(payload, userId, secret);
  if (Buffer.byteLength(signature) !== Buffer.byteLength(expected)) return null;
  if (!timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  return { mood };
}

export function reelMoodKeyboard(userId, secret, now = Date.now()) {
  const buttons = Object.entries(REEL_MOODS).map(([mood, value]) => ({
    text: value.label,
    callback_data: makeReelMoodAction(mood, userId, secret, now)
  }));
  return {
    inline_keyboard: [
      buttons.slice(0, 2),
      buttons.slice(2, 4),
      buttons.slice(4, 6)
    ]
  };
}

export function reelTopicPrompt(mood) {
  if (!Object.hasOwn(REEL_MOODS, mood)) throw new Error('invalid_reel_mood');
  return [
    '🎬 Original devotional Reel',
    `Mood: ${REEL_MOODS[mood].label}`,
    `Mood preset: ${mood}`,
    '',
    'Reply to this message with ONE topic or situation.',
    'Examples: overthinking, anger, faith during hard times, naam jap, relationships, mental peace.',
    '',
    'The worker will create a new 9:16 Reel with an original Hindi hook, original narration/text, Krishna visual treatment and copyright-safe original flute-style music.'
  ].join('\n');
}

export function readReelReply(message, token) {
  const reply = message?.reply_to_message;
  if (!reply?.from?.is_bot || String(reply.from.id) !== String(token || '').split(':')[0] || reply.forward_origin) return null;
  const mood = String(reply.text || '').match(/Mood preset:\s*([a-z]+)/i)?.[1]?.toLowerCase();
  if (!mood || !Object.hasOwn(REEL_MOODS, mood)) return null;
  const topic = String(message.text || '').trim().replace(/\s+/g, ' ');
  if (topic.length < 2 || topic.length > 140 || /^\//.test(topic)) return null;
  return { mood, topic };
}

export function parseCreateReelCommand(text) {
  const match = String(text || '').trim().match(/^\/create_reel(?:@\w+)?(?:\s+([a-z]+))?(?:\s+(.+))?$/i);
  if (!match) return null;
  const mood = match[1]?.toLowerCase() || '';
  const topic = String(match[2] || '').trim().replace(/\s+/g, ' ');
  if (!mood && !topic) return { mode: 'choose' };
  if (!Object.hasOwn(REEL_MOODS, mood)) return { mode: 'invalid_mood' };
  if (!topic) return { mode: 'ask_topic', mood };
  if (topic.length < 2 || topic.length > 140) return { mode: 'invalid_topic', mood };
  return { mode: 'queue', mood, topic };
}
