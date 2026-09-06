import test from 'node:test';
import assert from 'node:assert/strict';
import { extractYouTubeId, fetchYouTubeMetadata } from '../src/youtube.js';

test('extracts standard YouTube watch URL', () => {
  assert.equal(extractYouTubeId('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), 'dQw4w9WgXcQ');
});

test('extracts youtu.be and Shorts URLs', () => {
  assert.equal(extractYouTubeId('https://youtu.be/dQw4w9WgXcQ?t=12'), 'dQw4w9WgXcQ');
  assert.equal(extractYouTubeId('https://youtube.com/shorts/dQw4w9WgXcQ'), 'dQw4w9WgXcQ');
});

test('rejects non-YouTube hosts', () => {
  assert.equal(extractYouTubeId('https://example.com/watch?v=dQw4w9WgXcQ'), null);
});

test('reuses YouTube OAuth refresh credentials for richer metadata', async () => {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url: String(url), options });

    if (String(url).includes('/oembed?')) {
      return response({
        title: 'Fallback title',
        author_name: 'Fallback channel',
        thumbnail_url: 'https://img.youtube.com/example.jpg'
      });
    }

    if (String(url) === 'https://oauth2.googleapis.com/token') {
      assert.equal(options.method, 'POST');
      const body = new URLSearchParams(options.body);
      assert.equal(body.get('client_id'), 'client-id');
      assert.equal(body.get('client_secret'), 'client-secret');
      assert.equal(body.get('refresh_token'), 'refresh-token');
      assert.equal(body.get('grant_type'), 'refresh_token');
      return response({ access_token: 'test-access-token' });
    }

    if (String(url).startsWith('https://www.googleapis.com/youtube/v3/videos')) {
      assert.equal(options.headers.Authorization, 'Bearer test-access-token');
      return response({
        items: [{
          snippet: {
            title: 'Rich title',
            channelTitle: 'Rich channel',
            description: 'Rich description',
            publishedAt: '2026-09-01T00:00:00Z',
            tags: ['posture', 'mobility'],
            thumbnails: { high: { url: 'https://img.youtube.com/rich.jpg' } }
          },
          contentDetails: { duration: 'PT45S' },
          statistics: { viewCount: '12345' }
        }]
      });
    }

    throw new Error(`Unexpected URL: ${url}`);
  };

  const metadata = await fetchYouTubeMetadata('https://youtu.be/dQw4w9WgXcQ', {
    oauth: {
      clientId: 'client-id',
      clientSecret: 'client-secret',
      refreshToken: 'refresh-token'
    },
    fetchImpl
  });

  assert.equal(metadata.analysisDepth, 'youtube-data-api-oauth');
  assert.equal(metadata.title, 'Rich title');
  assert.equal(metadata.channelTitle, 'Rich channel');
  assert.equal(metadata.description, 'Rich description');
  assert.deepEqual(metadata.tags, ['posture', 'mobility']);
  assert.equal(metadata.duration, 'PT45S');
  assert.equal(metadata.viewCount, '12345');
  assert.equal(calls.length, 3);
});

function response(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return payload; }
  };
}
