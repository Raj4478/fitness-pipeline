import { dailyRecommendationKeyboard, formatDailyReelRecommendation, getDailyReelRecommendation } from '../src/daily-recommendation.js';

const token = String(process.env.TELEGRAM_BOT_TOKEN || '').trim();
const userId = String(process.env.TELEGRAM_ALLOWED_USER_ID || '').trim();
const secret = String(process.env.TELEGRAM_WEBHOOK_SECRET || '').trim();

if (!token || !/^\d+$/.test(userId) || !secret) {
  throw new Error('daily_recommendation_configuration_incomplete');
}

const recommendation = getDailyReelRecommendation(new Date());
const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    chat_id: Number(userId),
    text: formatDailyReelRecommendation(recommendation),
    reply_markup: dailyRecommendationKeyboard(recommendation, Number(userId), secret),
    link_preview_options: { is_disabled: true }
  })
});

const body = await response.text();
if (!response.ok) {
  throw new Error(`telegram_daily_recommendation_failed:${response.status}:${body.slice(0, 500)}`);
}

console.log(JSON.stringify({
  ok: true,
  date: recommendation.date,
  weekday: recommendation.weekday,
  deity: recommendation.deity,
  mood: recommendation.mood,
  topic: recommendation.topic
}));
