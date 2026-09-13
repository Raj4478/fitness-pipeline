import { pathToFileURL } from 'node:url';

export function productionVariables(env) {
  const required = ['VERCEL_TOKEN', 'VERCEL_ORG_ID', 'VERCEL_PROJECT_ID', 'WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_ALLOWED_USER_ID', 'TELEGRAM_WEBHOOK_SECRET', 'GROQ_API_KEY', 'GH_ACTIONS_TOKEN', 'GITHUB_REPO', 'GITHUB_DEFAULT_BRANCH', 'APP_COMMIT_SHA'];
  for (const key of required) if (!env[key]?.trim()) throw new Error(`Missing ${key}`);
  if (!/^\d+$/.test(env.TELEGRAM_ALLOWED_USER_ID)) throw new Error('Invalid allowed user ID');
  if (!/^[\w-]{1,256}$/.test(env.TELEGRAM_WEBHOOK_SECRET)) throw new Error('Invalid webhook secret');
  const origin = new URL(env.WEBHOOK_URL);
  if (origin.protocol !== 'https:' || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) throw new Error('WEBHOOK_URL must be an HTTPS origin');
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(env.GITHUB_REPO)) throw new Error('Invalid GitHub repository');
  if (!/^[a-f0-9]{40}$/.test(env.APP_COMMIT_SHA)) throw new Error('Invalid production commit');
  const keys = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_ALLOWED_USER_ID', 'TELEGRAM_WEBHOOK_SECRET', 'GROQ_API_KEY', 'YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN', 'YOUTUBE_API_KEY', 'GH_ACTIONS_TOKEN', 'GITHUB_REPO', 'GITHUB_DEFAULT_BRANCH', 'APP_COMMIT_SHA'];
  return keys.filter(key => env[key]).map(key => ({ key, value: env[key], type: 'encrypted', target: ['production'] }));
}

export async function configureProduction(env = process.env, fetchImpl = fetch) {
  const values = productionVariables(env);
  const url = new URL(`https://api.vercel.com/v10/projects/${encodeURIComponent(env.VERCEL_PROJECT_ID)}/env`);
  url.searchParams.set('teamId', env.VERCEL_ORG_ID);
  url.searchParams.set('upsert', 'true');
  const response = await fetchImpl(url, {
    method: 'POST', signal: AbortSignal.timeout(20000),
    headers: { Authorization: `Bearer ${env.VERCEL_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(values)
  });
  if (!response.ok) throw new Error(`Environment configuration failed (HTTP ${response.status})`);
  const body = await response.json();
  if (body.error || body.failed?.length) throw new Error('One or more environment variables could not be configured');
  console.log(`Configured ${values.length} production variables; values withheld.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    await configureProduction();
  } catch (error) {
    // Never print fetch causes, request headers or provider responses.
    console.error(error instanceof TypeError ? 'Configuration request failed.' : error.message);
    process.exit(1);
  }
}
