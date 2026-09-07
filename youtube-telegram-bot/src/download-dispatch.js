import { extractYouTubeId } from './youtube.js';

const WORKFLOW_FILE = 'youtube_download_worker.yml';

export function hasRightsAcknowledgement(text) {
  return /(?:^|\s)--authorized(?:\s|$)/i.test(String(text || ''));
}

export function resolveGitHubRepo(env = process.env) {
  const explicit = String(env.GITHUB_REPO || '').trim();
  if (explicit) return explicit;
  const owner = String(env.VERCEL_GIT_REPO_OWNER || '').trim();
  const slug = String(env.VERCEL_GIT_REPO_SLUG || '').trim();
  return owner && slug ? `${owner}/${slug}` : '';
}

export async function queueAuthorizedDownload(url, {
  env = process.env,
  fetchImpl = fetch
} = {}) {
  if (!extractYouTubeId(url)) {
    const error = new Error('invalid_youtube_url');
    error.code = 'invalid_youtube_url';
    throw error;
  }

  const token = String(env.GH_ACTIONS_TOKEN || '').trim();
  const repo = resolveGitHubRepo(env);
  const branch = String(env.GITHUB_DEFAULT_BRANCH || 'master').trim();
  if (!token || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo) || !branch) {
    const error = new Error('download_configuration_incomplete');
    error.code = 'download_configuration_incomplete';
    throw error;
  }

  const endpoint = `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const response = await fetchImpl(endpoint, {
    method: 'POST',
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      ref: branch,
      inputs: { url: String(url) }
    }),
    signal: AbortSignal.timeout(5000)
  });

  if (response.status !== 204) {
    const error = new Error('download_dispatch_failed');
    error.code = 'download_dispatch_failed';
    throw error;
  }
  return { queued: true };
}
