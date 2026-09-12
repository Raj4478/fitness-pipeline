import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler } from '../api/telegram.js';
import { downloadConfirmKeyboard, formatKeyboard, makeDownloadAction, readDownloadAction } from '../src/experience.js';

const env = {
  TELEGRAM_BOT_TOKEN: '123:test-token',
  TELEGRAM_ALLOWED_USER_ID: '42',
  TELEGRAM_WEBHOOK_SECRET: 'test-secret',
  GH_ACTIONS_TOKEN: 'gh-secret',
  GITHUB_REPO: 'owner/repo',
  GITHUB_DEFAULT_BRANCH: 'master'
};
const videoId = 'abcdef12345';
const source = `https://www.youtube.com/watch?v=${videoId}`;

function fixture() {
  const calls = [];
  const handler = createHandler({
    env,
    fetchImpl: async (url, options = {}) => {
      const target = String(url);
      if (target.includes('api.github.com')) {
        calls.push({ type: 'github', url: target, authorization: options.headers?.Authorization, body: JSON.parse(options.body) });
        return { status: 204, ok: true, json: async () => ({}) };
      }
      const body = options.body instanceof FormData ? options.body : JSON.parse(options.body || '{}');
      calls.push({ type: 'telegram', url: target, body });
      return { status: 200, ok: true, json: async () => ({ ok: true, result: { message_id: calls.length } }) };
    },
    metadataFn: async () => assert.fail('download must not call metadata'),
    generateFn: async () => assert.fail('download must not call Groq')
  });
  async function run(body) {
    const res = { status(code) { this.code = code; return this; }, json(data) { this.data = data; return this; } };
    await handler({ method: 'POST', headers: { 'x-telegram-bot-api-secret-token': env.TELEGRAM_WEBHOOK_SECRET }, body }, res);
    return res;
  }
  return { calls, run };
}

function message(text, updateId = 1) {
  return { update_id: updateId, message: { from: { id: 42 }, chat: { id: 42, type: 'private' }, text } };
}

function callback(data, updateId = 2) {
  return { update_id: updateId, callback_query: { id: `q-${updateId}`, from: { id: 42 }, data, message: { chat: { id: 42, type: 'private' } } };
}

test('pasted YouTube link keyboard contains a signed Download video button', () => {
  const keyboard = formatKeyboard(videoId, 42, env.TELEGRAM_WEBHOOK_SECRET, 100000);
  const button = keyboard.inline_keyboard.flat().find(item => item.text === '⬇️ Download video');
  assert.ok(button?.callback_data);
  const action = readDownloadAction(button.callback_data, 42, env.TELEGRAM_WEBHOOK_SECRET, 100001);
  assert.deepEqual(action, { videoId, phase: 'request' });
  assert.ok(Buffer.byteLength(button.callback_data) <= 64);
});

test('download request callback asks for rights confirmation without dispatching', async () => {
  const f = fixture();
  const data = makeDownloadAction(videoId, 'request', 42, env.TELEGRAM_WEBHOOK_SECRET);
  const res = await f.run(callback(data));
  assert.equal(res.data.status, 'download_confirmation');
  assert.equal(f.calls.filter(call => call.type === 'github').length, 0);
  const prompt = f.calls.find(call => call.type === 'telegram' && call.body.text?.includes('Only continue'));
  assert.ok(prompt);
  const confirm = prompt.body.reply_markup.inline_keyboard.flat().find(item => item.text.includes('I have rights'));
  assert.ok(confirm?.callback_data);
});

test('signed rights confirmation queues GitHub yt-dlp worker exactly once', async () => {
  const f = fixture();
  const data = makeDownloadAction(videoId, 'confirm', 42, env.TELEGRAM_WEBHOOK_SECRET);
  const res = await f.run(callback(data));
  assert.equal(res.data.status, 'download_queued');
  const dispatches = f.calls.filter(call => call.type === 'github');
  assert.equal(dispatches.length, 1);
  assert.match(dispatches[0].url, /youtube_download_worker\.yml\/dispatches$/);
  assert.equal(dispatches[0].body.inputs.url, source);
  assert.equal(dispatches[0].body.inputs.chat_id, '42');
  assert.equal(dispatches[0].body.ref, 'master');
  assert.equal(dispatches[0].authorization, 'Bearer gh-secret');
  assert.ok(!JSON.stringify(dispatches[0].body).includes('gh-secret'));
});

test('plain Instagram Reel URL immediately queues the worker for the same chat', async () => {
  const f = fixture();
  const res = await f.run(message('https://www.instagram.com/reel/ABC123/?igsh=tracking', 9));
  assert.equal(res.data.status, 'download_queued');
  const dispatches = f.calls.filter(call => call.type === 'github');
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].body.inputs.url, 'https://www.instagram.com/reel/ABC123/');
  assert.equal(dispatches[0].body.inputs.chat_id, '42');
  assert.equal(f.calls.some(call => call.type === 'telegram' && call.body.text?.includes('Instagram Reel queued')), true);
});

test('/download YouTube command requires confirmation unless --authorized is present', async () => {
  const first = fixture();
  assert.equal((await first.run(message(`/download ${source}`))).data.status, 'download_confirmation');
  assert.equal(first.calls.filter(call => call.type === 'github').length, 0);

  const second = fixture();
  assert.equal((await second.run(message(`/download ${source} --authorized`, 3))).data.status, 'download_queued');
  assert.equal(second.calls.filter(call => call.type === 'github').length, 1);
});

test('download confirmation payload rejects user changes and tampering', () => {
  const data = makeDownloadAction(videoId, 'confirm', 42, 'secret', 100000);
  assert.deepEqual(readDownloadAction(data, 42, 'secret', 100001), { videoId, phase: 'confirm' });
  assert.equal(readDownloadAction(data, 43, 'secret', 100001), null);
  assert.equal(readDownloadAction(data.replace('confirm', 'request'), 42, 'secret', 100001), null);
  assert.throws(() => downloadConfirmKeyboard('bad id', 42, 'secret'));
});
