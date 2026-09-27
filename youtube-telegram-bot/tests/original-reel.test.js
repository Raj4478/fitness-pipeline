import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler } from '../api/telegram.js';
import {
  makeReelMoodAction,
  readReelMoodAction,
  reelMoodKeyboard,
  readReelReply,
  parseCreateReelCommand
} from '../src/original-reel.js';

const env = {
  TELEGRAM_BOT_TOKEN: '123:test-token',
  TELEGRAM_ALLOWED_USER_ID: '42',
  TELEGRAM_WEBHOOK_SECRET: 'test-secret',
  GH_ACTIONS_TOKEN: 'gh-secret',
  GITHUB_REPO: 'owner/repo',
  GITHUB_DEFAULT_BRANCH: 'master'
};

function fixture() {
  const calls = [];
  const handler = createHandler({
    env,
    now: () => 100000,
    fetchImpl: async (url, options = {}) => {
      const target = String(url);
      if (target.includes('api.github.com')) {
        calls.push({ type: 'github', url: target, body: JSON.parse(options.body || '{}') });
        return { status: 204, ok: true, json: async () => ({}) };
      }
      const body = options.body instanceof FormData ? options.body : JSON.parse(options.body || '{}');
      calls.push({ type: 'telegram', url: target, body });
      return { status: 200, ok: true, json: async () => ({ ok: true, result: { message_id: calls.length } }) };
    },
    metadataFn: async () => assert.fail('original Reel flow must not call YouTube metadata'),
    generateFn: async () => assert.fail('original Reel flow must not use draft generator')
  });

  async function run(body) {
    const res = {
      status(code) { this.code = code; return this; },
      json(data) { this.data = data; return this; }
    };
    await handler({
      method: 'POST',
      headers: { 'x-telegram-bot-api-secret-token': env.TELEGRAM_WEBHOOK_SECRET },
      body
    }, res);
    return res;
  }
  return { calls, run };
}

function message(text, updateId = 1, extra = {}) {
  return {
    update_id: updateId,
    message: {
      from: { id: 42 },
      chat: { id: 42, type: 'private' },
      text,
      ...extra
    }
  };
}

function callback(data, updateId = 2) {
  return {
    update_id: updateId,
    callback_query: {
      id: `q-${updateId}`,
      from: { id: 42 },
      data,
      message: { chat: { id: 42, type: 'private' } }
    }
  };
}

test('mood callbacks are signed, compact and reject tampering', () => {
  const data = makeReelMoodAction('peaceful', 42, env.TELEGRAM_WEBHOOK_SECRET, 100000);
  assert.deepEqual(readReelMoodAction(data, 42, env.TELEGRAM_WEBHOOK_SECRET, 100001), { mood: 'peaceful' });
  assert.equal(readReelMoodAction(data, 43, env.TELEGRAM_WEBHOOK_SECRET, 100001), null);
  assert.equal(readReelMoodAction(data.replace('peaceful', 'joyful'), 42, env.TELEGRAM_WEBHOOK_SECRET, 100001), null);
  assert.ok(Buffer.byteLength(data) <= 64);
  assert.equal(reelMoodKeyboard(42, env.TELEGRAM_WEBHOOK_SECRET, 100000).inline_keyboard.flat().length, 6);
});

test('/create_reel starts with the mood picker', async () => {
  const f = fixture();
  const res = await f.run(message('/create_reel'));
  assert.equal(res.data.status, 'reel_mood_prompt');
  const sent = f.calls.find(call => call.type === 'telegram' && call.body.text?.includes('Choose the mood'));
  assert.ok(sent);
  assert.equal(sent.body.reply_markup.inline_keyboard.flat().length, 6);
  assert.equal(f.calls.filter(call => call.type === 'github').length, 0);
});

test('mood button asks for a topic using ForceReply', async () => {
  const f = fixture();
  const data = makeReelMoodAction('devotional', 42, env.TELEGRAM_WEBHOOK_SECRET, 100000);
  const res = await f.run(callback(data));
  assert.equal(res.data.status, 'reel_topic_prompt');
  const prompt = f.calls.find(call => call.type === 'telegram' && call.body.text?.includes('Mood preset: devotional'));
  assert.ok(prompt);
  assert.equal(prompt.body.reply_markup.force_reply, true);
});

test('replying to the mood prompt dispatches the original Reel workflow', async () => {
  const f = fixture();
  const reply = {
    from: { id: 123, is_bot: true },
    text: '🎬 Original devotional Reel\nMood: Peaceful 🌙\nMood preset: peaceful\n\nReply to this message with ONE topic or situation.'
  };
  const res = await f.run(message('overthinking at night', 3, { reply_to_message: reply }));
  assert.equal(res.data.status, 'original_reel_queued');
  const dispatch = f.calls.find(call => call.type === 'github');
  assert.ok(dispatch);
  assert.match(dispatch.url, /original_reel_worker\.yml\/dispatches$/);
  assert.deepEqual(dispatch.body.inputs, {
    mood: 'peaceful',
    topic: 'overthinking at night',
    chat_id: '42'
  });
});

test('direct mood + topic command dispatches without conversational state', async () => {
  const f = fixture();
  const res = await f.run(message('/create_reel reflective relationships and expectations', 4));
  assert.equal(res.data.status, 'original_reel_queued');
  const dispatch = f.calls.find(call => call.type === 'github');
  assert.equal(dispatch.body.inputs.mood, 'reflective');
  assert.equal(dispatch.body.inputs.topic, 'relationships and expectations');
});

test('reply parser only accepts replies to this bot and valid topics', () => {
  const good = {
    text: 'anger',
    reply_to_message: {
      from: { id: 123, is_bot: true },
      text: 'Mood preset: motivational'
    }
  };
  assert.deepEqual(readReelReply(good, env.TELEGRAM_BOT_TOKEN), { mood: 'motivational', topic: 'anger' });
  assert.equal(readReelReply({ ...good, reply_to_message: { ...good.reply_to_message, from: { id: 999, is_bot: true } } }, env.TELEGRAM_BOT_TOKEN), null);
  assert.deepEqual(parseCreateReelCommand('/create_reel joyful gratitude'), { mode: 'queue', mood: 'joyful', topic: 'gratitude' });
});
