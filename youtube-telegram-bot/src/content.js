const DEFAULT_HASHTAGS = [
  '#chiropractic', '#chiropractor', '#mobility', '#posture', '#backpain',
  '#neckpain', '#spinehealth', '#movement', '#wellness', '#physiotherapy',
  '#painmanagement', '#healthtips', '#mobilitytraining', '#posturetips', '#recovery'
];

export async function generateContent(metadata, {
  apiKey = '',
  model = 'openai/gpt-oss-120b',
  niche = 'chiropractic education, posture, mobility and spine health',
  tone = 'educational, curious, concise, social-first and non-diagnostic',
  hashtagCount = 18,
  fetchImpl = fetch
} = {}) {
  if (!apiKey) return fallbackContent(metadata, { niche, hashtagCount });

  const prompt = `Create original Instagram content inspired by the supplied YouTube metadata for a NEW chiropractic-themed account.\n\nRules:\n- Do not copy the source video's title or description verbatim beyond unavoidable names/short phrases.\n- Do not diagnose anyone. Do not promise cures, guaranteed relief, alignment claims, or medical outcomes.\n- If the metadata does not support a factual medical claim, do not invent one.\n- Frame chiropractic clips as education/commentary and encourage professional evaluation for persistent/severe symptoms.\n- Credit the original channel clearly.\n- Generate exactly ${hashtagCount} relevant hashtags, balancing niche and broader discovery tags; avoid spammy unrelated tags.\n- Tone: ${tone}.\n- Niche: ${niche}.\n\nMetadata: ${JSON.stringify({
    title: metadata.title,
    channelTitle: metadata.channelTitle,
    description: String(metadata.description || '').slice(0, 3500),
    tags: metadata.tags || [],
    duration: metadata.duration,
    publishedAt: metadata.publishedAt
  })}\n\nReturn JSON with exactly: hook, caption, hashtags, angle, caution, attribution.`;

  const response = await fetchImpl('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: 'You are a careful social-media editor for health-adjacent educational content. Return valid JSON only.' },
        { role: 'user', content: prompt }
      ],
      response_format: { type: 'json_object' },
      reasoning_effort: 'low'
    })
  });

  if (!response.ok) throw new Error(`Groq generation failed: ${response.status} ${await response.text()}`);
  const payload = await response.json();
  const raw = payload?.choices?.[0]?.message?.content || '{}';
  const parsed = JSON.parse(raw);
  return normalize(parsed, metadata, hashtagCount);
}

function normalize(value, metadata, hashtagCount) {
  const hashtags = Array.isArray(value.hashtags)
    ? value.hashtags.map((tag) => String(tag).trim()).filter(Boolean).map((tag) => tag.startsWith('#') ? tag : `#${tag.replace(/\s+/g, '')}`).slice(0, hashtagCount)
    : [];
  return {
    hook: String(value.hook || '').trim(),
    caption: String(value.caption || '').trim(),
    hashtags: hashtags.length ? hashtags : DEFAULT_HASHTAGS.slice(0, hashtagCount),
    angle: String(value.angle || 'Educational movement/posture commentary').trim(),
    caution: String(value.caution || 'Educational content only; persistent or severe symptoms should be assessed by a qualified healthcare professional.').trim(),
    attribution: String(value.attribution || `Source inspiration: ${metadata.channelTitle || 'original YouTube creator'} — ${metadata.canonicalUrl}`).trim()
  };
}

function fallbackContent(metadata, { niche, hashtagCount }) {
  const title = metadata.title || 'this movement clip';
  const channel = metadata.channelTitle || 'the original creator';
  return {
    hook: 'Your body gives you signals — the context matters.',
    caption: `A useful clip to start a conversation about ${niche}. “${title}” can be a good prompt to think about movement, posture and individual assessment rather than one-size-fits-all fixes. Save it for reference, and get persistent or severe symptoms assessed by a qualified professional.`,
    hashtags: DEFAULT_HASHTAGS.slice(0, Math.max(1, Math.min(hashtagCount, DEFAULT_HASHTAGS.length))),
    angle: 'Educational commentary with a mobility/posture lens',
    caution: 'Educational content only; no diagnosis or guaranteed treatment claims.',
    attribution: `Source inspiration: ${channel} — ${metadata.canonicalUrl}`
  };
}
