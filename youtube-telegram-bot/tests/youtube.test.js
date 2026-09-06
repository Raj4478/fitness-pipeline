import test from 'node:test';
import assert from 'node:assert/strict';
import { extractYouTubeId } from '../src/youtube.js';

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
