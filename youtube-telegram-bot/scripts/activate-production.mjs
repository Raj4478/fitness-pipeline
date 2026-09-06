import { readFile } from 'node:fs/promises';
const env = process.env;
async function telegram(method, payload) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal: AbortSignal.timeout(15000)
  });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(`Telegram ${method} failed (HTTP ${response.status})`);
  return data.result;
}
try {
  const origin = new URL(env.WEBHOOK_URL);
  if (origin.protocol !== 'https:' || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) throw new Error('Invalid production origin');
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_WEBHOOK_SECRET) throw new Error('Missing Telegram configuration');
  const endpoint = new URL('/api/telegram', origin).href;
  const response = await fetch(endpoint, { signal: AbortSignal.timeout(15000), redirect: 'error' });
  const health = await response.json();
  const pkg = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  if (!response.ok || !health.ok || health.version !== pkg.version) throw new Error('Production version health check failed');
  const headers = { 'Content-Type': 'application/json', 'x-telegram-bot-api-secret-token': env.TELEGRAM_WEBHOOK_SECRET };
  // An empty update verifies configuration/authentication without sending a message.
  const accepted = await fetch(endpoint, { method: 'POST', headers, body: '{}', signal: AbortSignal.timeout(15000) });
  const result = await accepted.json();
  if (!accepted.ok || !result.ignored) throw new Error('Authenticated webhook probe failed');
  const rejected = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', signal: AbortSignal.timeout(15000) });
  if (rejected.status !== 401) throw new Error('Webhook authentication rejection probe failed');
  await telegram('setWebhook', { url: endpoint, secret_token: env.TELEGRAM_WEBHOOK_SECRET, allowed_updates: ['message', 'callback_query'], drop_pending_updates: false });
  const info = await telegram('getWebhookInfo', {});
  if (info.url !== endpoint || !info.allowed_updates?.includes('callback_query')) throw new Error('Webhook registration verification failed');
  const bot = await telegram('getMe', {});
  console.log(JSON.stringify({ live: true, version: health.version, endpoint, bot: bot.username, pendingUpdates: info.pending_update_count }));
} catch {
  console.error('Production activation failed. No provider payloads were logged. Check the deployment status and required configuration.');
  process.exit(1);
}
