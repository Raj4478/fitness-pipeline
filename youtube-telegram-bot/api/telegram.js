import { extractYouTubeId, fetchYouTubeMetadata } from '../src/youtube.js';
import { generateContent } from '../src/content.js';
import { parseAllowHosts, validateDownloadUrl } from '../src/download-policy.js';
import { sendPermittedVideo, sendText, editText, telegramCall } from '../src/telegram.js';
import { HELP, PRIVACY, FORMATS, firstUrl, readAction, formatKeyboard, sourceSummary, formatDraft } from '../src/experience.js';
import { boundedFetch } from '../src/network.js';

export function createHandler({ env = process.env, fetchImpl = fetch, metadataFn = fetchYouTubeMetadata, generateFn = generateContent, now = Date.now } = {}) {
  // Best-effort duplicate suppression for a warm instance, not a durable job queue.
  const seen = new Map();
  const busy = new Set();
  return async function handler(req, res) {
    if (req.method === 'GET') return res.status(200).json({ ok: true, service: 'youtube-telegram-chiro-bot', version: '0.2.0' });
    if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'method_not_allowed' });
    const token = env.TELEGRAM_BOT_TOKEN || '';
    const allowedUser = String(env.TELEGRAM_ALLOWED_USER_ID || '').trim();
    const secret = env.TELEGRAM_WEBHOOK_SECRET || '';
    if (!token || !/^\d+$/.test(allowedUser) || !secret) {
      return res.status(503).json({ ok: false, error: 'bot_configuration_incomplete' });
    }
    if (req.headers?.['x-telegram-bot-api-secret-token'] !== secret) return res.status(401).json({ ok: false, error: 'invalid_webhook_secret' });
    const callback = req.body?.callback_query;
    const message = callback?.message || req.body?.message;
    const userId = callback?.from?.id || message?.from?.id;
    if (!message?.chat?.id || message.chat.type !== 'private' || String(userId) !== allowedUser) {
      return res.status(200).json({ ok: true, ignored: true });
    }
    const chatId = message.chat.id;
    const deadline = AbortSignal.timeout(22000);
    const io = (url, options = {}) => fetchImpl(url, { ...options, signal: options.signal ? AbortSignal.any([options.signal, deadline]) : deadline });
    let progressId, stage = 'input', generating = false, videoId, format = 'caption';
    const success = status => res.status(200).json({ ok: true, status });
    try {
      if (callback) {
        await telegramCall(token, 'answerCallbackQuery', { callback_query_id: callback.id }, io);
        const action = readAction(callback.data, userId, secret, now());
        if (!action) {
          await sendText(token, chatId, 'That button has expired or is unavailable. Paste the YouTube link again to choose a format.', io);
          return success('expired_action');
        }
        ({ videoId, format } = action);
      }
      for (const [key, time] of seen) if (now() - time > 300000) seen.delete(key);
      const updateId = req.body?.update_id;
      if (Number.isSafeInteger(updateId)) {
        if (seen.has(updateId)) return success('duplicate');
        if (seen.size >= 500) seen.delete(seen.keys().next().value);
        seen.set(updateId, now());
      }
      const text = String(message.text || message.caption || '').trim();
      const command = text.match(/^\/(\w+)(?:@\w+)?(?:\s|$)/)?.[1]?.toLowerCase();
      if (!callback) {
        if (command === 'start' || command === 'help') { await sendText(token, chatId, HELP, io); return success('help'); }
        if (command === 'privacy') { await sendText(token, chatId, PRIVACY, io); return success('privacy'); }
        if (!text) { await sendText(token, chatId, 'Please send one YouTube video or Shorts link as text. Voice notes and uploaded videos are not analysed yet. Use /help for examples.', io); return success('unsupported_input'); }
        if (command === 'download') {
          const verdict = validateDownloadUrl(firstUrl(text), parseAllowHosts(env.DOWNLOAD_ALLOWLIST_HOSTS));
          if (!verdict.ok) {
            await sendText(token, chatId, verdict.reason === 'youtube_download_not_supported'
              ? 'YouTube links can be used for content drafts. To relay your own video, use a permitted direct media link from your configured storage host.'
              : 'That media link is unavailable for relay. Send a direct HTTPS video link from your configured storage host. Use /help for the content-drafting options.', io);
            return success('download_blocked');
          }
          await sendPermittedVideo(token, chatId, verdict.url, 'Permitted media relay', io);
          return success('sent');
        }
        if (command && !['analyze', ...Object.keys(FORMATS)].includes(command)) {
          await sendText(token, chatId, 'I do not recognise that command. Paste a YouTube link to choose a format, or use /help.', io);
          return success('unknown_command');
        }
        const urls = text.match(/https?:\/\/[^\s<>]+/gi) || [];
        if (urls.length > 1) { await sendText(token, chatId, 'Please send one video at a time so each draft has a clear source.', io); return success('multiple_links'); }
        videoId = extractYouTubeId(firstUrl(text));
        if (!videoId) { await sendText(token, chatId, 'Send a YouTube watch or Shorts link, for example:\nhttps://www.youtube.com/watch?v=VIDEO_ID\n\nPaste the link alone to choose a format, or put /analyze before it for a caption.', io); return success('invalid_link'); }
        if (!command) {
          await sendText(token, chatId, 'What would you like to create?\n\nChoose a format below. Drafts use public video metadata and need editorial review.', io, { reply_markup: formatKeyboard(videoId, userId, secret, now()) });
          return success('choose_format');
        }
        format = command === 'analyze' ? 'caption' : command;
      }
      if (busy.has(userId)) { await sendText(token, chatId, 'Your previous draft is still being prepared. Please wait for it to finish, then choose another format.', io); return success('busy'); }
      busy.add(userId); generating = true;
      const progress = await sendText(token, chatId, `Preparing your ${FORMATS[format].label.toLowerCase()}…\n1/2 · Reading public video details.`, io);
      progressId = progress?.message_id;
      stage = 'metadata';
      const metadata = await metadataFn(`https://www.youtube.com/watch?v=${videoId}`, {
        apiKey: env.YOUTUBE_API_KEY || '',
        oauth: { clientId: env.YOUTUBE_CLIENT_ID || '', clientSecret: env.YOUTUBE_CLIENT_SECRET || '', refreshToken: env.YOUTUBE_REFRESH_TOKEN || '' },
        fetchImpl: boundedFetch(io, 4000)
      });
      if (progressId) await editText(token, chatId, progressId, `${sourceSummary(metadata)}\n\n2/2 · Writing your ${FORMATS[format].label.toLowerCase()}…`, io).catch(() => {});
      stage = 'generation';
      const content = await generateFn(metadata, {
        apiKey: env.GROQ_API_KEY || '', model: env.GROQ_MODEL || 'openai/gpt-oss-120b',
        niche: env.ACCOUNT_NICHE || 'chiropractic education, posture, mobility and spine health',
        tone: env.ACCOUNT_TONE || 'educational, curious, concise and non-diagnostic',
        hashtagCount: Number(env.HASHTAG_COUNT || 8), format, fetchImpl: boundedFetch(io, 15000)
      });
      stage = 'delivery';
      await sendText(token, chatId, formatDraft(metadata, content, format), io, { reply_markup: formatKeyboard(videoId, userId, secret, now(), content) });
      if (progressId) await editText(token, chatId, progressId, `${sourceSummary(metadata)}\n\n✓ Draft ready below.`, io).catch(() => {});
      return success('generated');
    } catch {
      // Never log or echo provider payloads, source descriptions, user text or token-bearing URLs.
      console.error(JSON.stringify({ event: 'chiro_request_failed', stage }));
      const message = stage === 'metadata'
        ? 'I could not read that video’s public details. Check that it is public and the link opens, then try again.'
        : 'Your draft could not be completed this time. Please try again in a moment.';
      const recovery = videoId ? { reply_markup: formatKeyboard(videoId, userId, secret, now()) } : {};
      await (progressId
        ? editText(token, chatId, progressId, message, fetchImpl, recovery)
        : sendText(token, chatId, message, fetchImpl, recovery)).catch(() => {});
      return success('handled_error');
    } finally {
      if (generating) busy.delete(userId);
    }
  };
}
export default createHandler();
