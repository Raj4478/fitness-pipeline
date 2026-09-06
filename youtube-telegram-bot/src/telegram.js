const TELEGRAM_API = 'https://api.telegram.org';

export async function telegramCall(token, method, payload, fetchImpl = fetch) {
  const response = await fetchImpl(`${TELEGRAM_API}/bot${token}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(`Telegram ${method} failed: ${response.status} ${data.description || ''}`.trim());
  }
  return data.result;
}

export async function sendText(token, chatId, text, fetchImpl = fetch) {
  const chunks = splitText(String(text), 3900);
  for (const chunk of chunks) {
    await telegramCall(token, 'sendMessage', {
      chat_id: chatId,
      text: chunk,
      disable_web_page_preview: false
    }, fetchImpl);
  }
}

export async function sendPermittedVideo(token, chatId, mediaUrl, caption = '', fetchImpl = fetch) {
  return telegramCall(token, 'sendVideo', {
    chat_id: chatId,
    video: mediaUrl,
    caption: String(caption).slice(0, 1000),
    supports_streaming: true
  }, fetchImpl);
}

export function splitText(text, maxLength = 3900) {
  if (text.length <= maxLength) return [text];
  const chunks = [];
  let remaining = text;
  while (remaining.length > maxLength) {
    let cut = remaining.lastIndexOf('\n', maxLength);
    if (cut < maxLength * 0.6) cut = remaining.lastIndexOf(' ', maxLength);
    if (cut <= 0) cut = maxLength;
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}
