const token = process.env.TELEGRAM_BOT_TOKEN || '';
const webhookUrl = process.env.WEBHOOK_URL || '';
const secret = process.env.TELEGRAM_WEBHOOK_SECRET || '';

if (!token || !webhookUrl) {
  console.error('TELEGRAM_BOT_TOKEN and WEBHOOK_URL are required');
  process.exit(1);
}

const response = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    url: webhookUrl.replace(/\/$/, '') + '/api/telegram',
    secret_token: secret || undefined,
    allowed_updates: ['message', 'edited_message'],
    drop_pending_updates: true
  })
});

const body = await response.json();
console.log(JSON.stringify(body, null, 2));
if (!response.ok || body.ok === false) process.exit(1);
