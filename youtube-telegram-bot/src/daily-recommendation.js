import { makeReelMoodAction } from './original-reel.js';

const DAY_PLANS = Object.freeze({
  Sunday: {
    deity: 'Rama / Surya',
    mood: 'motivational',
    why: 'Sunday is commonly associated with Surya; Rama is also a strong devotional fit for confidence, purpose and a fresh start.',
    topics: [
      ['fresh start', 'नई शुरुआत के लिए मन कैसे तैयार करें?'],
      ['confidence', 'आत्मविश्वास कम हो तो पहला कदम क्या हो?'],
      ['discipline', 'दिन की शुरुआत मजबूत कैसे करें?']
    ]
  },
  Monday: {
    deity: 'Shiva',
    mood: 'peaceful',
    why: 'Monday is commonly associated with Shiva and is a natural fit for calm, emotional balance and mental stillness.',
    topics: [
      ['overthinking', 'मन बार-बार वही बात क्यों सोचता है?'],
      ['mental peace', 'बेचैनी में मन को शांत कैसे रखें?'],
      ['letting go', 'जो हमारे बस में नहीं उसे कैसे छोड़ें?']
    ]
  },
  Tuesday: {
    deity: 'Hanuman / Durga',
    mood: 'motivational',
    why: 'Tuesday is commonly associated with Hanuman and, in some traditions, Durga—strong themes for courage, discipline and protection.',
    topics: [
      ['courage', 'डर के बावजूद सही कदम कैसे उठाएँ?'],
      ['anger', 'गुस्से की ऊर्जा को सही दिशा कैसे दें?'],
      ['discipline', 'मन न करे तब भी अनुशासन कैसे रखें?']
    ]
  },
  Wednesday: {
    deity: 'Ganesha',
    mood: 'joyful',
    why: 'Wednesday is commonly associated with Ganesha, making clarity, obstacles, learning and new beginnings natural themes.',
    topics: [
      ['obstacles', 'काम बार-बार अटक जाए तो क्या करें?'],
      ['focus', 'भटकते मन को काम पर कैसे लौटाएँ?'],
      ['new beginnings', 'नई शुरुआत से डर क्यों लगता है?']
    ]
  },
  Thursday: {
    deity: 'Krishna / Vishnu',
    mood: 'devotional',
    why: 'Thursday is commonly associated with Vishnu and Guru; Krishna-focused devotion works especially well for faith, surrender and spiritual learning.',
    topics: [
      ['faith', 'मुश्किल समय में भगवान पर भरोसा कैसे रखें?'],
      ['naam jap', 'नाम जप करते समय मन भटके तो क्या करें?'],
      ['surrender', 'हर चीज़ को नियंत्रित करने की जरूरत क्यों नहीं?']
    ]
  },
  Friday: {
    deity: 'Lakshmi / Durga',
    mood: 'joyful',
    why: 'Friday is commonly associated with Lakshmi and the Divine Feminine, making gratitude, harmony, beauty and abundance strong themes.',
    topics: [
      ['gratitude', 'कृतज्ञता मन को भीतर से कैसे बदलती है?'],
      ['relationships', 'रिश्तों में अपेक्षा कम कैसे करें?'],
      ['abundance', 'जो है उसकी कद्र करना क्यों जरूरी है?']
    ]
  },
  Saturday: {
    deity: 'Hanuman / Shani',
    mood: 'reflective',
    why: 'Saturday is commonly associated with Shani and Hanuman, which fits patience, karma, resilience and disciplined reflection.',
    topics: [
      ['patience', 'मुश्किल दौर में धैर्य कैसे बनाए रखें?'],
      ['karma', 'हर परिणाम तुरंत क्यों नहीं मिलता?'],
      ['resilience', 'बार-बार गिरकर भी आगे कैसे बढ़ें?']
    ]
  }
});

function indiaParts(date = new Date()) {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    weekday: 'long',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });
  const parts = Object.fromEntries(formatter.formatToParts(date).map(part => [part.type, part.value]));
  return {
    weekday: parts.weekday,
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day)
  };
}

function stableIndex(year, month, day, length) {
  const ordinal = Math.floor(Date.UTC(year, month - 1, day) / 86400000);
  return ((ordinal % length) + length) % length;
}

export function getDailyReelRecommendation(date = new Date()) {
  const parts = indiaParts(date);
  const plan = DAY_PLANS[parts.weekday];
  const [topic, hook] = plan.topics[stableIndex(parts.year, parts.month, parts.day, plan.topics.length)];
  const isoDate = `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`;
  return {
    date: isoDate,
    weekday: parts.weekday,
    deity: plan.deity,
    mood: plan.mood,
    topic,
    hook,
    why: plan.why,
    instagramAngle: 'Use fresh original visuals, start with the specific hook on frame 1, keep the Reel focused on one problem, and end with one useful takeaway people may save or send.'
  };
}

export function formatDailyReelRecommendation(recommendation) {
  return [
    `📅 Daily Reel Recommendation · ${recommendation.weekday}`,
    '',
    `🕉️ Deity: ${recommendation.deity}`,
    `🎨 Mood: ${recommendation.mood}`,
    `💡 Topic: ${recommendation.topic}`,
    '',
    `🎯 Hook: ${recommendation.hook}`,
    '',
    `Why today: ${recommendation.why}`,
    '',
    `Instagram angle: ${recommendation.instagramAngle}`,
    '',
    'This is a content-planning recommendation, not a guarantee of reach.'
  ].join('\n');
}

export function dailyRecommendationKeyboard(recommendation, userId, secret, now = Date.now()) {
  return {
    inline_keyboard: [[{
      text: '🎬 Create today’s Reel',
      callback_data: makeReelMoodAction(recommendation.mood, userId, secret, now)
    }]]
  };
}
