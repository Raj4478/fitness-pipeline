const YOUTUBE_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be']);
const INSTAGRAM_HOSTS = new Set(['instagram.com', 'www.instagram.com']);
const INSTAGRAM_REEL_PATH = /^\/reels?\/[^/]+\/?$/i;
const MEDIA_EXTENSIONS = new Set(['.mp4', '.mov', '.m4v', '.webm']);

export function validateDownloadUrl(input, allowHosts = []) {
  let url;
  try {
    url = new URL(String(input).trim());
  } catch {
    return { ok: false, reason: 'invalid_url' };
  }

  if (url.protocol !== 'https:') return { ok: false, reason: 'https_required' };
  const host = url.hostname.toLowerCase();

  if (YOUTUBE_HOSTS.has(host)) {
    return { ok: true, url: url.toString(), mode: 'youtube_worker' };
  }

  if (INSTAGRAM_HOSTS.has(host)) {
    if (!INSTAGRAM_REEL_PATH.test(url.pathname)) {
      return { ok: false, reason: 'unsupported_instagram_url' };
    }
    url.search = '';
    url.hash = '';
    return { ok: true, url: url.toString(), mode: 'instagram_worker' };
  }

  const normalizedAllowHosts = allowHosts.map((value) => String(value).trim().toLowerCase()).filter(Boolean);
  if (!normalizedAllowHosts.length || !normalizedAllowHosts.includes(host)) {
    return { ok: false, reason: 'host_not_allowlisted' };
  }

  const path = url.pathname.toLowerCase();
  const extension = [...MEDIA_EXTENSIONS].find((ext) => path.endsWith(ext));
  if (!extension) return { ok: false, reason: 'unsupported_media_type' };

  return { ok: true, url: url.toString(), extension, mode: 'direct_relay' };
}

export function parseAllowHosts(value = '') {
  return String(value).split(',').map((host) => host.trim()).filter(Boolean);
}
