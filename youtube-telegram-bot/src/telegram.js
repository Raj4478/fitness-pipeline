import { boundedFetch } from './network.js';
const TELEGRAM_API = 'https://api.telegram.org';

export async function telegramCall(token, method, payload, fetchImpl = fetch) {
  const response = await boundedFetch(fetchImpl, 5000)(`${TELEGRAM_API}/bot${token}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    const error = new Error(`telegram_${response.status}`);
    error.code = 'telegram_error';
    throw error;
  }
  return data.result;
}

export async function sendText(token, chatId, text, fetchImpl = fetch, options = {}) {
  const chunks = splitText(String(text), 3900);
  let result;
  for (const [index, chunk] of chunks.entries()) {
    result = await telegramCall(token, 'sendMessage', {
      chat_id: chatId,
      text: chunk,
      link_preview_options: { is_disabled: true },
      ...(index === chunks.length - 1 ? options : {})
    }, fetchImpl);
  }
  return result;
}

export function editText(token, chatId, messageId, text, fetchImpl = fetch, options = {}) {
  return telegramCall(token, 'editMessageText', { chat_id: chatId, message_id: messageId, text, link_preview_options: { is_disabled: true }, ...options }, fetchImpl);
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
  if (!Number.isInteger(maxLength) || maxLength < 2) throw new Error('invalid_chunk_length');
  if (text.length <= maxLength) return [text];
  const chunks = [];
  let remaining = text;
  while (remaining.length > maxLength) {
    let cut = remaining.lastIndexOf('\n', maxLength);
    if (cut < maxLength * 0.6) cut = remaining.lastIndexOf(' ', maxLength);
    if (cut <= 0) cut = maxLength;
    if (/[\uD800-\uDBFF]/.test(remaining[cut - 1])) cut--;
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

export async function sendDocument(token, chatId, text, fetchImpl = fetch) {
  const form = new FormData();
  form.set('chat_id', String(chatId));
  form.set('document', new Blob([text], { type: 'text/plain;charset=utf-8' }), 'chiro-draft.txt');
  form.set('caption', 'Your draft, including source credit and review notes.');
  const response = await boundedFetch(fetchImpl, 5000)(`${TELEGRAM_API}/bot${token}/sendDocument`, { method: 'POST', body: form });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok !== true) throw new Error('document_delivery_failed');
  return data.result;
}
