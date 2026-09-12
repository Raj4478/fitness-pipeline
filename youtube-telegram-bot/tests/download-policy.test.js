import test from 'node:test';
import assert from 'node:assert/strict';
import { parseAllowHosts, validateDownloadUrl } from '../src/download-policy.js';

test('routes YouTube links to the authorized worker', () => {
  assert.deepEqual(validateDownloadUrl('https://youtu.be/dQw4w9WgXcQ', []), {
    ok: true,
    url: 'https://youtu.be/dQw4w9WgXcQ',
    mode: 'youtube_worker'
  });
});

test('routes Instagram Reel links to the worker and removes tracking query parameters', () => {
  assert.deepEqual(validateDownloadUrl('https://www.instagram.com/reel/ABC123/?igsh=test', []), {
    ok: true,
    url: 'https://www.instagram.com/reel/ABC123/',
    mode: 'instagram_worker'
  });
  assert.equal(validateDownloadUrl('https://instagram.com/reels/ABC123/', []).mode, 'instagram_worker');
});

test('does not treat arbitrary Instagram pages as downloadable Reels', () => {
  assert.equal(validateDownloadUrl('https://www.instagram.com/example/', []).reason, 'unsupported_instagram_url');
  assert.equal(validateDownloadUrl('https://www.instagram.com/p/ABC123/', []).reason, 'unsupported_instagram_url');
});

test('requires an allowlisted HTTPS direct video', () => {
  assert.equal(validateDownloadUrl('http://cdn.example.com/a.mp4', ['cdn.example.com']).reason, 'https_required');
  assert.equal(validateDownloadUrl('https://other.example.com/a.mp4', ['cdn.example.com']).reason, 'host_not_allowlisted');
  assert.equal(validateDownloadUrl('https://cdn.example.com/a.txt', ['cdn.example.com']).reason, 'unsupported_media_type');
  assert.equal(validateDownloadUrl('https://cdn.example.com/a.mp4', ['cdn.example.com']).mode, 'direct_relay');
});

test('parses allowlisted hosts', () => {
  assert.deepEqual(parseAllowHosts('cdn.one.com, cdn.two.com'), ['cdn.one.com', 'cdn.two.com']);
});
