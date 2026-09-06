const token = process.env.TELEGRAM_BOT_TOKEN || '';
const webhookUrl = process.env.WEBHOOK_URL || '';
const secret = process.env.TELEGRAM_WEBHOOK_SECRET || '';

if (!token || !webhookUrl || !secret || !/^\d+$/.test(process.env.TELEGRAM_ALLOWED_USER_ID || '')) {
  console.error('TELEGRAM_BOT_TOKEN, WEBHOOK_URL, TELEGRAM_WEBHOOK_SECRET and TELEGRAM_ALLOWED_USER_ID are required');
  process.exit(1);
}

const response = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    url: webhookUrl.replace(/\/$/, '') + '/api/telegram',
    secret_token: secret,
    allowed_updates: ['message', 'callback_query'],
    drop_pending_updates: process.env.DROP_PENDING_UPDATES === 'true'
  })
});

const body = await response.json();
console.log(JSON.stringify(body, null, 2));
if (!response.ok || body.ok === false) process.exit(1);
