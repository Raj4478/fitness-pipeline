import { readFileSync } from 'node:fs';
import { extractYouTubeId, fetchYouTubeMetadata } from '../src/youtube.js';
import { generateContent } from '../src/content.js';
import { parseAllowHosts, validateDownloadUrl } from '../src/download-policy.js';
import { hasRightsAcknowledgement, queueAuthorizedDownload, queueOriginalReel } from '../src/download-dispatch.js';
import { sendPermittedVideo, sendDocument, sendText, editText, telegramCall } from '../src/telegram.js';
import { HELP, PRIVACY, FORMATS, VARIANTS, EXAMPLES, repliedDraft, firstUrl, readAction, readDownloadAction, downloadConfirmKeyboard, formatKeyboard, sourceSummary, formatDraft } from '../src/experience.js';
import { boundedFetch } from '../src/network.js';
import { parseCreateReelCommand, readReelMoodAction, readReelReply, reelMoodKeyboard, reelTopicPrompt, REEL_MOODS } from '../src/original-reel.js';
import { dailyRecommendationKeyboard, formatDailyReelRecommendation, getDailyReelRecommendation } from '../src/daily-recommendation.js';

const DOWNLOAD_CONFIRMATION = 'Only continue if you own this video or have permission to download and reuse it. The worker will not use cookies or bypass private, members-only, premium, sign-in, DRM, or geo restrictions.';
const DOWNLOAD_QUEUED = '⬇️ Download queued. The on-demand yt-dlp worker will return an MP4 here if the source is accessible and the file can be kept within Telegram’s upload limit.';
const INSTAGRAM_DOWNLOAD_QUEUED = '⬇️ Instagram Reel queued. I’ll return the MP4 here if the Reel is public, accessible without login, and fits Telegram’s upload limit.';
const { version } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));

export function createHandler({ env = process.env, fetchImpl = fetch, metadataFn = fetchYouTubeMetadata, generateFn = generateContent, now = Date.now } = {}) {
  const seen = new Map();
  const busy = new Set();
  return async function handler(req, res) {
    if (req.method === 'GET') return res.status(200).json({ ok: true, service: 'youtube-instagram-telegram-chiro-bot', version, commit: env.APP_COMMIT_SHA || null });
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
    let progressId, stage = 'input', generating = false, videoId, format = 'caption', variant = '', previousDraft = '', instructions = '';
    const success = status => res.status(200).json({ ok: true, status });
    try {
      if (callback) {
        await telegramCall(token, 'answerCallbackQuery', { callback_query_id: callback.id }, io);

        const reelMoodAction = readReelMoodAction(callback.data, userId, secret, now());
        if (reelMoodAction) {
          const { mood } = reelMoodAction;
          await sendText(token, chatId, reelTopicPrompt(mood), io, {
            reply_markup: {
              force_reply: true,
              selective: true,
              input_field_placeholder: 'e.g. overthinking'
            }
          });
          return success('reel_topic_prompt');
        }

        const downloadAction = readDownloadAction(callback.data, userId, secret, now());
        if (downloadAction) {
          videoId = downloadAction.videoId;
          if (downloadAction.phase === 'request') {
            await sendText(token, chatId, DOWNLOAD_CONFIRMATION, io, {
              reply_markup: downloadConfirmKeyboard(videoId, userId, secret, now())
            });
            return success('download_confirmation');
          }
          stage = 'download_dispatch';
          await queueAuthorizedDownload(`https://www.youtube.com/watch?v=${videoId}`, { chatId, env, fetchImpl: io });
          await sendText(token, chatId, DOWNLOAD_QUEUED, io);
          return success('download_queued');
        }

        const action = readAction(callback.data, userId, secret, now());
        if (!action) {
          await sendText(token, chatId, 'That button has expired or is unavailable. Paste the YouTube link again to choose a format.', io);
          return success('expired_action');
        }
        ({ videoId, format } = action);
        variant = action.variant || '';
        if (variant) previousDraft = String(message.text || '').slice(0, 3900);
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
        const repliedReel = readReelReply(message, token);
        if (repliedReel) {
          stage = 'original_reel_dispatch';
          await queueOriginalReel({ ...repliedReel, chatId }, { env, fetchImpl: io });
          await sendText(
            token,
            chatId,
            `🎨 Original Reel queued.\nMood: ${REEL_MOODS[repliedReel.mood].label}\nTopic: ${repliedReel.topic}\n\nI’ll send the finished MP4 and caption here when the GitHub worker completes.`,
            io
          );
          return success('original_reel_queued');
        }

        const createReel = parseCreateReelCommand(text);
        if (createReel) {
          if (createReel.mode === 'choose') {
            await sendText(token, chatId, '🎨 Choose the mood for your new original devotional Reel:', io, {
              reply_markup: reelMoodKeyboard(userId, secret, now())
            });
            return success('reel_mood_prompt');
          }
          if (createReel.mode === 'invalid_mood') {
            await sendText(token, chatId, `Choose one of: ${Object.keys(REEL_MOODS).join(', ')}.\n\nOr just send /create_reel and tap a mood.`, io);
            return success('invalid_reel_mood');
          }
          if (createReel.mode === 'ask_topic') {
            await sendText(token, chatId, reelTopicPrompt(createReel.mood), io, {
              reply_markup: {
                force_reply: true,
                selective: true,
                input_field_placeholder: 'e.g. overthinking'
              }
            });
            return success('reel_topic_prompt');
          }
          if (createReel.mode === 'invalid_topic') {
            await sendText(token, chatId, 'Keep the Reel topic between 2 and 140 characters.', io);
            return success('invalid_reel_topic');
          }
          if (createReel.mode === 'queue') {
            stage = 'original_reel_dispatch';
            await queueOriginalReel({ mood: createReel.mood, topic: createReel.topic, chatId }, { env, fetchImpl: io });
            await sendText(
              token,
              chatId,
              `🎨 Original Reel queued.\nMood: ${REEL_MOODS[createReel.mood].label}\nTopic: ${createReel.topic}\n\nI’ll send the finished MP4 and caption here when the GitHub worker completes.`,
              io
            );
            return success('original_reel_queued');
          }
        }

        if (command === 'today' || command === 'daily') {
          const recommendation = getDailyReelRecommendation(new Date(now()));
          await sendText(
            token,
            chatId,
            formatDailyReelRecommendation(recommendation),
            io,
            { reply_markup: dailyRecommendationKeyboard(recommendation, userId, secret, now()) }
          );
          return success('daily_recommendation');
        }

        if (command === 'start' || command === 'help') { await sendText(token, chatId, HELP, io); return success('help'); }
        if (command === 'examples') { await sendText(token, chatId, EXAMPLES, io); return success('examples'); }
        if (command === 'privacy') { await sendText(token, chatId, PRIVACY, io); return success('privacy'); }
        if (!text) { await sendText(token, chatId, 'Please send one YouTube video, Shorts link, or public Instagram Reel URL as text. Use /help for examples.', io); return success('unsupported_input'); }

        if (command === 'download') {
          const sourceUrl = firstUrl(text);
          const verdict = validateDownloadUrl(sourceUrl, parseAllowHosts(env.DOWNLOAD_ALLOWLIST_HOSTS));
          if (!verdict.ok) {
            await sendText(token, chatId, 'That media link is unavailable for relay. Send a valid YouTube link, public Instagram Reel, or a direct HTTPS video link from your configured storage host.', io);
            return success('download_blocked');
          }

          if (verdict.mode === 'instagram_worker') {
            stage = 'download_dispatch';
            await queueAuthorizedDownload(verdict.url, { chatId, env, fetchImpl: io });
            await sendText(token, chatId, INSTAGRAM_DOWNLOAD_QUEUED, io);
            return success('download_queued');
          }

          if (verdict.mode === 'youtube_worker') {
            videoId = extractYouTubeId(verdict.url);
            if (!hasRightsAcknowledgement(text)) {
              await sendText(token, chatId, DOWNLOAD_CONFIRMATION, io, {
                reply_markup: downloadConfirmKeyboard(videoId, userId, secret, now())
              });
              return success('download_confirmation');
            }
            stage = 'download_dispatch';
            await queueAuthorizedDownload(verdict.url, { chatId, env, fetchImpl: io });
            await sendText(token, chatId, DOWNLOAD_QUEUED, io);
            return success('download_queued');
          }

          await sendPermittedVideo(token, chatId, verdict.url, 'Permitted media relay', io);
          return success('sent');
        }

        if (command === 'rewrite' || command === 'export') {
          const draft = repliedDraft(message, token);
          if (!draft) { await sendText(token, chatId, 'Reply directly to one of my complete generated drafts with /export or /rewrite followed by editing instructions.', io); return success('reply_required'); }
          if (command === 'export') { await sendDocument(token, chatId, draft.text, io); return success('exported'); }
          instructions = text.replace(/^\/rewrite(?:@\w+)?\s*/i, '').trim();
          if (!instructions || instructions.length > 500) { await sendText(token, chatId, 'Add 1–500 characters of editing instructions after /rewrite, for example: Make it friendlier and finish with a question.', io); return success('invalid_instructions'); }
          previousDraft = draft.text; format = draft.format; videoId = extractYouTubeId(draft.source);
        }
        if (command && !['analyze', 'rewrite', 'create_reel', 'today', 'daily', ...Object.keys(VARIANTS), ...Object.keys(FORMATS)].includes(command)) {
          await sendText(token, chatId, 'I do not recognise that command. Paste a YouTube link to choose a format, paste an Instagram Reel to download it, or use /help.', io);
          return success('unknown_command');
        }
        if (!previousDraft) {
          const urls = text.match(/https?:\/\/[^\s<>]+/gi) || [];
          if (urls.length > 1) { await sendText(token, chatId, 'Please send one video at a time.', io); return success('multiple_links'); }
          const sourceUrl = firstUrl(text);
          const downloadVerdict = validateDownloadUrl(sourceUrl, parseAllowHosts(env.DOWNLOAD_ALLOWLIST_HOSTS));
          if (!command && downloadVerdict.ok && downloadVerdict.mode === 'instagram_worker') {
            stage = 'download_dispatch';
            await queueAuthorizedDownload(downloadVerdict.url, { chatId, env, fetchImpl: io });
            await sendText(token, chatId, INSTAGRAM_DOWNLOAD_QUEUED, io);
            return success('download_queued');
          }
          videoId = extractYouTubeId(sourceUrl);
          if (!videoId) { await sendText(token, chatId, 'Send a YouTube watch/Shorts link for content generation, or paste a public Instagram Reel URL to download it.', io); return success('invalid_link'); }
          if (!command) {
            await sendText(token, chatId, 'What would you like to create?\n\nChoose a content format or download the video if you have permission to reuse it.', io, { reply_markup: formatKeyboard(videoId, userId, secret, now()) });
            return success('choose_format');
          }
          variant = Object.hasOwn(VARIANTS, command || '') ? command : '';
          format = command === 'analyze' || variant ? 'caption' : command;
        }
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
        hashtagCount: Number(env.HASHTAG_COUNT || 8), format, variant, previousDraft, instructions, fetchImpl: boundedFetch(io, 15000)
      });
      stage = 'delivery';
      await sendText(token, chatId, formatDraft(metadata, content, format), io, { reply_markup: formatKeyboard(videoId, userId, secret, now(), { ...content, format }) });
      if (progressId) await editText(token, chatId, progressId, `${sourceSummary(metadata)}\n\n✓ Draft ready below.`, io).catch(() => {});
      return success('generated');
    } catch {
      console.error(JSON.stringify({ event: 'chiro_request_failed', stage }));
      const errorMessage = stage === 'metadata'
        ? 'I could not read that video’s public details. Check that it is public and the link opens, then try again.'
        : stage === 'download_dispatch'
          ? 'I could not queue the download worker. Check the GitHub Actions token/repository configuration and try again.'
          : stage === 'original_reel_dispatch'
            ? 'I could not queue the original Reel generator. Check the GitHub Actions configuration and try again.'
            : 'Your request could not be completed this time. Please try again in a moment.';
      const recovery = videoId && stage !== 'download_dispatch' ? { reply_markup: formatKeyboard(videoId, userId, secret, now()) } : {};
      await (progressId
        ? editText(token, chatId, progressId, errorMessage, fetchImpl, recovery)
        : sendText(token, chatId, errorMessage, fetchImpl, recovery)).catch(() => {});
      return success('handled_error');
    } finally {
      if (generating) busy.delete(userId);
    }
  };
}
export default createHandler();
