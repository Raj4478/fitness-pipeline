import { validateDownloadUrl } from './download-policy.js';

const WORKFLOW_FILE = 'youtube_download_worker.yml';
const ORIGINAL_REEL_WORKFLOW_FILE = 'original_reel_worker.yml';

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
  const verdict = validateDownloadUrl(url, []);
  if (!verdict.ok || !['youtube_worker', 'instagram_worker'].includes(verdict.mode)) {
    const error = new Error('invalid_worker_url');
    error.code = 'invalid_worker_url';
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
      inputs: { url: verdict.url }
    }),
    signal: AbortSignal.timeout(5000)
  });

  if (response.status !== 204) {
    const error = new Error('download_dispatch_failed');
    error.code = 'download_dispatch_failed';
    throw error;
  }
  return { queued: true, mode: verdict.mode };
}


async function dispatchWorkflow(workflowFile, inputs, {
  env = process.env,
  fetchImpl = fetch
} = {}) {
  const token = String(env.GH_ACTIONS_TOKEN || '').trim();
  const repo = resolveGitHubRepo(env);
  const branch = String(env.GITHUB_DEFAULT_BRANCH || 'master').trim();
  if (!token || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo) || !branch) {
    const error = new Error('github_actions_configuration_incomplete');
    error.code = 'github_actions_configuration_incomplete';
    throw error;
  }

  const endpoint = `https://api.github.com/repos/${repo}/actions/workflows/${workflowFile}/dispatches`;
  const response = await fetchImpl(endpoint, {
    method: 'POST',
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ ref: branch, inputs }),
    signal: AbortSignal.timeout(5000)
  });

  if (response.status !== 204) {
    const error = new Error('workflow_dispatch_failed');
    error.code = 'workflow_dispatch_failed';
    throw error;
  }
  return { queued: true };
}

export async function queueOriginalReel({ mood, topic, chatId }, options = {}) {
  const cleanMood = String(mood || '').trim().toLowerCase();
  const cleanTopic = String(topic || '').trim().replace(/\s+/g, ' ');
  if (!/^[a-z]{3,20}$/.test(cleanMood) || cleanTopic.length < 2 || cleanTopic.length > 140) {
    const error = new Error('invalid_original_reel_request');
    error.code = 'invalid_original_reel_request';
    throw error;
  }
  if (!Number.isSafeInteger(Number(chatId)) || Number(chatId) <= 0) {
    const error = new Error('invalid_chat_id');
    error.code = 'invalid_chat_id';
    throw error;
  }

  await dispatchWorkflow(ORIGINAL_REEL_WORKFLOW_FILE, {
    mood: cleanMood,
    topic: cleanTopic,
    chat_id: String(chatId)
  }, options);
  return { queued: true, mood: cleanMood, topic: cleanTopic };
}
