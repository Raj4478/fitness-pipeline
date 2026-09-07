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

test('requires an allowlisted HTTPS direct video', () => {
  assert.equal(validateDownloadUrl('http://cdn.example.com/a.mp4', ['cdn.example.com']).reason, 'https_required');
  assert.equal(validateDownloadUrl('https://other.example.com/a.mp4', ['cdn.example.com']).reason, 'host_not_allowlisted');
  assert.equal(validateDownloadUrl('https://cdn.example.com/a.txt', ['cdn.example.com']).reason, 'unsupported_media_type');
  assert.equal(validateDownloadUrl('https://cdn.example.com/a.mp4', ['cdn.example.com']).mode, 'direct_relay');
});

test('parses allowlisted hosts', () => {
  assert.deepEqual(parseAllowHosts('cdn.one.com, cdn.two.com'), ['cdn.one.com', 'cdn.two.com']);
});
