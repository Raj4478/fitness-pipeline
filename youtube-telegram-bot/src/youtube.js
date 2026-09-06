export function extractYouTubeId(input) {
  try {
    const url = new URL(String(input).trim());
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    if (host === 'youtu.be') {
      return cleanId(url.pathname.split('/').filter(Boolean)[0]);
    }
    if (!['youtube.com', 'm.youtube.com', 'music.youtube.com'].includes(host)) return null;
    if (url.pathname === '/watch') return cleanId(url.searchParams.get('v'));
    const parts = url.pathname.split('/').filter(Boolean);
    if (['shorts', 'embed', 'live'].includes(parts[0])) return cleanId(parts[1]);
    return null;
  } catch {
    return null;
  }
}

function cleanId(value) {
  const id = String(value || '').trim();
  return /^[A-Za-z0-9_-]{6,20}$/.test(id) ? id : null;
}

export async function fetchYouTubeMetadata(inputUrl, { apiKey = '', fetchImpl = fetch } = {}) {
  const videoId = extractYouTubeId(inputUrl);
  if (!videoId) throw new Error('Invalid YouTube URL');

  const canonicalUrl = `https://www.youtube.com/watch?v=${videoId}`;
  const result = {
    videoId,
    canonicalUrl,
    title: '',
    channelTitle: '',
    description: '',
    publishedAt: '',
    tags: [],
    duration: '',
    viewCount: '',
    thumbnailUrl: '',
    analysisDepth: apiKey ? 'youtube-data-api' : 'oembed'
  };

  const oembedUrl = `https://www.youtube.com/oembed?url=${encodeURIComponent(canonicalUrl)}&format=json`;
  const oembedResponse = await fetchImpl(oembedUrl, { headers: { 'User-Agent': 'youtube-telegram-chiro-bot/0.1' } });
  if (!oembedResponse.ok) throw new Error(`YouTube metadata lookup failed: ${oembedResponse.status}`);
  const oembed = await oembedResponse.json();
  result.title = oembed.title || '';
  result.channelTitle = oembed.author_name || '';
  result.thumbnailUrl = oembed.thumbnail_url || '';

  if (apiKey) {
    const apiUrl = new URL('https://www.googleapis.com/youtube/v3/videos');
    apiUrl.searchParams.set('part', 'snippet,contentDetails,statistics');
    apiUrl.searchParams.set('id', videoId);
    apiUrl.searchParams.set('key', apiKey);
    const apiResponse = await fetchImpl(apiUrl, { headers: { Accept: 'application/json' } });
    if (apiResponse.ok) {
      const payload = await apiResponse.json();
      const item = payload.items?.[0];
      if (item) {
        result.title = item.snippet?.title || result.title;
        result.channelTitle = item.snippet?.channelTitle || result.channelTitle;
        result.description = item.snippet?.description || '';
        result.publishedAt = item.snippet?.publishedAt || '';
        result.tags = Array.isArray(item.snippet?.tags) ? item.snippet.tags.slice(0, 30) : [];
        result.duration = item.contentDetails?.duration || '';
        result.viewCount = item.statistics?.viewCount || '';
        result.thumbnailUrl = item.snippet?.thumbnails?.high?.url || item.snippet?.thumbnails?.medium?.url || result.thumbnailUrl;
      }
    } else {
      result.analysisDepth = 'oembed-fallback';
    }
  }

  return result;
}
