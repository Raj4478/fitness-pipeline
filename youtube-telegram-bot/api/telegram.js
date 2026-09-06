import { extractYouTubeId, fetchYouTubeMetadata } from '../src/youtube.js';
import { generateContent } from '../src/content.js';
import { parseAllowHosts, validateDownloadUrl } from '../src/download-policy.js';
import { sendPermittedVideo, sendText } from '../src/telegram.js';

const HELP = `Send me a YouTube link and I will generate:\n• a hook\n• an original chiropractic-style caption\n• hashtags\n• a content angle\n• a safety note\n• source attribution\n\nCommands:\n/analyze <youtube-url>\n/download <permitted-direct-media-url>\n/help\n\nYouTube extraction/download bypass is intentionally not supported. If you own the video, use a permitted direct media URL or upload/provide the original file through your own storage.`;

export default async function handler(req, res) {
  if (req.method === 'GET') return res.status(200).json({ ok: true, service: 'youtube-telegram-chiro-bot' });
  if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'method_not_allowed' });

  const token = process.env.TELEGRAM_BOT_TOKEN || '';
  if (!token) return res.status(500).json({ ok: false, error: 'telegram_token_missing' });

  const webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET || '';
  if (webhookSecret && req.headers['x-telegram-bot-api-secret-token'] !== webhookSecret) {
    return res.status(401).json({ ok: false, error: 'invalid_webhook_secret' });
  }

  const message = req.body?.message || req.body?.edited_message;
  if (!message?.chat?.id) return res.status(200).json({ ok: true, ignored: true });

  const chatId = message.chat.id;
  const userId = message.from?.id;
  const allowedUser = String(process.env.TELEGRAM_ALLOWED_USER_ID || '').trim();
  if (allowedUser && String(userId) !== allowedUser) {
    await sendText(token, chatId, 'This bot is private.');
    return res.status(200).json({ ok: true, ignored: true });
  }

  const text = String(message.text || message.caption || '').trim();

  try {
    if (!text || /^\/(start|help)(?:@\w+)?\b/i.test(text)) {
      await sendText(token, chatId, HELP);
      return res.status(200).json({ ok: true });
    }

    if (/^\/download(?:@\w+)?\b/i.test(text)) {
      const url = firstUrl(text);
      if (!url) {
        await sendText(token, chatId, 'Usage: /download <permitted direct media URL>');
        return res.status(200).json({ ok: true });
      }
      const verdict = validateDownloadUrl(url, parseAllowHosts(process.env.DOWNLOAD_ALLOWLIST_HOSTS));
      if (!verdict.ok) {
        const explanation = verdict.reason === 'youtube_download_not_supported'
          ? 'I can analyze that YouTube link, but I cannot extract/download the YouTube media file. If you own it, provide the original/direct file URL from an allowlisted host.'
          : `Download blocked: ${verdict.reason}. Only HTTPS video files from DOWNLOAD_ALLOWLIST_HOSTS are permitted.`;
        await sendText(token, chatId, explanation);
        return res.status(200).json({ ok: true, status: 'blocked', reason: verdict.reason });
      }
      await sendPermittedVideo(token, chatId, verdict.url, 'Permitted media relay');
      return res.status(200).json({ ok: true, status: 'sent' });
    }

    const url = firstUrl(text);
    if (!url || !extractYouTubeId(url)) {
      await sendText(token, chatId, 'Send a valid YouTube video/Shorts link, or use /help.');
      return res.status(200).json({ ok: true, status: 'invalid_link' });
    }

    await sendText(token, chatId, 'Analyzing the YouTube link…');
    const metadata = await fetchYouTubeMetadata(url, {
      apiKey: process.env.YOUTUBE_API_KEY || '',
      oauth: {
        clientId: process.env.YOUTUBE_CLIENT_ID || '',
        clientSecret: process.env.YOUTUBE_CLIENT_SECRET || '',
        refreshToken: process.env.YOUTUBE_REFRESH_TOKEN || ''
      }
    });
    const content = await generateContent(metadata, {
      apiKey: process.env.GROQ_API_KEY || '',
      model: process.env.GROQ_MODEL || 'openai/gpt-oss-120b',
      niche: process.env.ACCOUNT_NICHE || 'chiropractic education, posture, mobility and spine health',
      tone: process.env.ACCOUNT_TONE || 'educational, curious, concise, social-first and non-diagnostic',
      hashtagCount: Number(process.env.HASHTAG_COUNT || 18)
    });

    const responseText = formatResult(metadata, content);
    await sendText(token, chatId, responseText);
    return res.status(200).json({ ok: true, status: 'analyzed', videoId: metadata.videoId });
  } catch (error) {
    console.error(error);
    await sendText(token, chatId, `Could not process that link: ${String(error?.message || error).slice(0, 500)}`).catch(() => {});
    return res.status(200).json({ ok: true, status: 'handled_error' });
  }
}

function firstUrl(text) {
  return String(text).match(/https?:\/\/[^\s<>]+/i)?.[0]?.replace(/[),.;!?]+$/, '') || '';
}

function formatResult(metadata, content) {
  return [
    `🎬 ${metadata.title}`,
    `👤 ${metadata.channelTitle || 'Unknown channel'}`,
    `🔎 Analysis: ${metadata.analysisDepth}`,
    '',
    `🎯 HOOK\n${content.hook}`,
    '',
    `📝 CAPTION\n${content.caption}`,
    '',
    `🏷️ HASHTAGS\n${content.hashtags.join(' ')}`,
    '',
    `💡 ANGLE\n${content.angle}`,
    '',
    `⚠️ NOTE\n${content.caution}`,
    '',
    `🙏 CREDIT\n${content.attribution}`
  ].join('\n');
}
