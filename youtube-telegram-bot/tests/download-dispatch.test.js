import test from 'node:test';
import assert from 'node:assert/strict';
import { hasRightsAcknowledgement, queueAuthorizedDownload, resolveGitHubRepo } from '../src/download-dispatch.js';

test('recognizes explicit rights acknowledgement', () => {
  assert.equal(hasRightsAcknowledgement('/download https://youtu.be/dQw4w9WgXcQ --authorized'), true);
  assert.equal(hasRightsAcknowledgement('/download https://youtu.be/dQw4w9WgXcQ'), false);
});

test('resolves repository from explicit or Vercel metadata', () => {
  assert.equal(resolveGitHubRepo({ GITHUB_REPO: 'owner/repo' }), 'owner/repo');
  assert.equal(resolveGitHubRepo({ VERCEL_GIT_REPO_OWNER: 'owner', VERCEL_GIT_REPO_SLUG: 'repo' }), 'owner/repo');
});

test('queues workflow_dispatch without exposing token in payload', async () => {
  let captured;
  const fetchImpl = async (url, options) => {
    captured = { url, options };
    return { status: 204 };
  };
  const env = { GH_ACTIONS_TOKEN: 'secret-token', GITHUB_REPO: 'owner/repo', GITHUB_DEFAULT_BRANCH: 'master' };
  const result = await queueAuthorizedDownload('https://youtu.be/dQw4w9WgXcQ', { env, fetchImpl });
  assert.equal(result.queued, true);
  assert.match(captured.url, /youtube_download_worker\.yml\/dispatches$/);
  assert.equal(JSON.parse(captured.options.body).inputs.url, 'https://youtu.be/dQw4w9WgXcQ');
  assert.equal(captured.options.body.includes('secret-token'), false);
});
