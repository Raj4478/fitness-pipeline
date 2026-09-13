import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { productionVariables, configureProduction } from '../scripts/configure-production.mjs';
import { queueAuthorizedDownload } from '../src/download-dispatch.js';
import { createHandler } from '../api/telegram.js';

const env = {
  VERCEL_TOKEN: 'deployment-token', VERCEL_ORG_ID: 'team_test', VERCEL_PROJECT_ID: 'prj_test',
  WEBHOOK_URL: 'https://example.vercel.app', TELEGRAM_BOT_TOKEN: 'bot-token',
  TELEGRAM_ALLOWED_USER_ID: '42', TELEGRAM_WEBHOOK_SECRET: 'webhook-secret', GROQ_API_KEY: 'groq-key',
  GH_ACTIONS_TOKEN: 'worker-token', GITHUB_REPO: 'owner/repo', GITHUB_DEFAULT_BRANCH: 'master',
  APP_COMMIT_SHA: 'a'.repeat(40), YOUTUBE_CLIENT_ID: 'youtube-client',
  YOUTUBE_CLIENT_SECRET: 'youtube-secret', YOUTUBE_REFRESH_TOKEN: 'youtube-refresh'
};

test('configured production variables support Instagram dispatch and preserve YouTube credentials', async () => {
  let runtime;
  await configureProduction(env, async (url, options) => {
    assert.equal(url.searchParams.get('teamId'), env.VERCEL_ORG_ID);
    assert.equal(url.searchParams.get('upsert'), 'true');
    const values = JSON.parse(options.body);
    assert.ok(values.every(item => item.type === 'encrypted' && item.target.join() === 'production'));
    runtime = Object.fromEntries(values.map(item => [item.key, item.value]));
    assert.equal(runtime.VERCEL_TOKEN, undefined);
    return { ok: true, json: async () => ({}) };
  });
  for (const key of ['YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN']) assert.equal(runtime[key], env[key]);
  await queueAuthorizedDownload('https://www.instagram.com/reel/ABC123/', { env: runtime, fetchImpl: async (url, options) => {
    assert.match(url, /repos\/owner\/repo\/actions\/workflows\/youtube_download_worker.yml\/dispatches$/);
    assert.equal(options.headers.Authorization, 'Bearer worker-token');
    assert.equal(JSON.parse(options.body).ref, 'master');
    return { status: 204 };
  } });
});

test('missing worker configuration and invalid commit fail before configuring Vercel', () => {
  for (const key of ['GH_ACTIONS_TOKEN', 'GITHUB_REPO', 'GITHUB_DEFAULT_BRANCH', 'APP_COMMIT_SHA']) {
    assert.throws(() => productionVariables({ ...env, [key]: '' }), new RegExp(`Missing ${key}`));
  }
  assert.throws(() => productionVariables({ ...env, APP_COMMIT_SHA: 'unknown' }), /Invalid production commit/);
});

test('Vercel access failures report status without revealing provider payloads', async () => {
  await assert.rejects(configureProduction(env, async () => ({ ok: false, status: 403, json: () => assert.fail('must not read provider payload') })), /^Error: Environment configuration failed \(HTTP 403\)$/);
});

test('health version matches activation package and identifies deployed commit', async () => {
  const handler = createHandler({ env });
  const response = { status(code) { this.code = code; return this; }, json(body) { this.body = body; } };
  await handler({ method: 'GET' }, response);
  assert.equal(response.code, 200);
  assert.equal(response.body.version, JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version);
  assert.equal(response.body.commit, env.APP_COMMIT_SHA);
  assert.equal(JSON.stringify(response.body).includes(env.GH_ACTIONS_TOKEN), false);
});
