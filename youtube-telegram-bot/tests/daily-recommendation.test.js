import test from 'node:test';
import assert from 'node:assert/strict';
import { getDailyReelRecommendation, formatDailyReelRecommendation, dailyRecommendationKeyboard } from '../src/daily-recommendation.js';
import { readReelMoodAction } from '../src/original-reel.js';
import { createHandler } from '../api/telegram.js';

const secret = 'test-secret';

test('weekday recommendations map to expected deity families and moods in IST', () => {
  const cases = [
    ['2026-09-27T06:00:00Z', 'Sunday', 'Rama / Surya', 'motivational'],
    ['2026-09-28T06:00:00Z', 'Monday', 'Shiva', 'peaceful'],
    ['2026-09-29T06:00:00Z', 'Tuesday', 'Hanuman / Durga', 'motivational'],
    ['2026-09-30T06:00:00Z', 'Wednesday', 'Ganesha', 'joyful'],
    ['2026-10-01T06:00:00Z', 'Thursday', 'Krishna / Vishnu', 'devotional'],
    ['2026-10-02T06:00:00Z', 'Friday', 'Lakshmi / Durga', 'joyful'],
    ['2026-10-03T06:00:00Z', 'Saturday', 'Hanuman / Shani', 'reflective']
  ];
  for (const [iso, weekday, deity, mood] of cases) {
    const rec = getDailyReelRecommendation(new Date(iso));
    assert.equal(rec.weekday, weekday);
    assert.equal(rec.deity, deity);
    assert.equal(rec.mood, mood);
    assert.ok(rec.topic.length >= 3);
    assert.ok(rec.hook.endsWith('?'));
  }
});

test('daily recommendation CTA reuses the signed mood action', () => {
  const now = new Date('2026-10-01T06:00:00Z').getTime();
  const rec = getDailyReelRecommendation(new Date(now));
  const keyboard = dailyRecommendationKeyboard(rec, 42, secret, now);
  const data = keyboard.inline_keyboard[0][0].callback_data;
  assert.deepEqual(readReelMoodAction(data, 42, secret, now + 1000), { mood: 'devotional' });
});

test('formatted recommendation explains deity, mood, topic and Instagram angle', () => {
  const rec = getDailyReelRecommendation(new Date('2026-09-28T06:00:00Z'));
  const text = formatDailyReelRecommendation(rec);
  assert.match(text, /Deity: Shiva/);
  assert.match(text, /Mood: peaceful/);
  assert.match(text, /Instagram angle:/);
  assert.match(text, /Hook:/);
});

test('/today sends the current recommendation and CTA', async () => {
  const calls = [];
  const env = {
    TELEGRAM_BOT_TOKEN: '123:test-token',
    TELEGRAM_ALLOWED_USER_ID: '42',
    TELEGRAM_WEBHOOK_SECRET: secret,
    GH_ACTIONS_TOKEN: 'gh-secret',
    GITHUB_REPO: 'owner/repo',
    GITHUB_DEFAULT_BRANCH: 'master'
  };
  const nowValue = new Date('2026-09-28T06:00:00Z').getTime();
  const handler = createHandler({
    env,
    now: () => nowValue,
    fetchImpl: async (url, options = {}) => {
      calls.push({ url: String(url), body: JSON.parse(options.body || '{}') });
      return { ok: true, status: 200, json: async () => ({ ok: true, result: { message_id: 1 } }) };
    },
    metadataFn: async () => assert.fail('today must not read YouTube metadata'),
    generateFn: async () => assert.fail('today must not run content generation')
  });
  const res = {
    status(code) { this.code = code; return this; },
    json(data) { this.data = data; return this; }
  };
  await handler({
    method: 'POST',
    headers: { 'x-telegram-bot-api-secret-token': secret },
    body: {
      update_id: 88,
      message: {
        from: { id: 42 },
        chat: { id: 42, type: 'private' },
        text: '/today'
      }
    }
  }, res);
  assert.equal(res.data.status, 'daily_recommendation');
  const sent = calls.find(call => call.body.text?.includes('Daily Reel Recommendation'));
  assert.ok(sent);
  assert.match(sent.body.text, /Deity: Shiva/);
  assert.equal(sent.body.reply_markup.inline_keyboard[0][0].text, '🎬 Create today’s Reel');
});
