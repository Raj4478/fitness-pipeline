"""
Script Generator - Fitness Niche
Supports Gemini, Groq, and DeepSeek.
Fetches real fitness/health news from Google News RSS before generating.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Literal

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

FITNESS_SYSTEM_PROMPT = """
You are a viral English fitness educator for a global audience on Instagram Reels and YouTube Shorts.
Your job is to TEACH with REAL NUMBERS and SPECIFIC FACTS — not vague general advice.

STRICT RULES:
- NEVER say "join a gym", "take protein", "ask your trainer" — this is not an ad
- EVERY script MUST contain at least 2 specific facts with numbers. Examples:
    ✅ "1 gram of protein per kg of bodyweight — a 70kg person only needs 70g"
    ✅ "In a study, just 0.7g/kg protein led to 2kg of muscle gain in 8 weeks"
    ✅ "76% of urban Indians are Vitamin D deficient — ICMR 2023 data"
    ✅ "A 30-minute walk drops blood sugar by 26% — Harvard Health 2022"
    ✅ "Muscles take 48-72 hours to recover — don't train the same muscle daily"
    ❌ "Too much protein isn't good for you" — TOO VAGUE, no numbers
    ❌ "Walking is great exercise" — TOO VAGUE, no facts
- Lead with a SPECIFIC shocking number or stat in the hook
- Use real study references casually: "Harvard found", "ICMR data", "a 2023 study"
- Compare numbers to relatable things: "70g protein = 3 eggs + 1 cup yogurt + 100g chicken"
- Explain the mechanism: WHY does this happen in the body — in 1-2 full sentences. Don't skip
  or compress this just to save words; this is the part that makes the fact actually land.
- End with a specific actionable insight that calls back to the hook's number or claim —
  not generic advice. The video replays the hook again at the very end, so the close should
  feel like it's answering the hook, not just trailing off.
- Hook must have a NUMBER or specific claim — never vague. It also doubles as the YouTube
  title, so it must work standalone with zero added context: curiosity-driven, specific,
  ideally under ~70 characters so it isn't truncated in YouTube's UI.
- NO FIXED WORD COUNT. Write as many words as the explanation genuinely needs to deliver:
  hook, the mechanism (why this happens), the common misconception if relevant, and one
  specific actionable step. Don't pad with filler or restate the same point twice — but don't
  compress a real explanation just to hit an arbitrary short length either. A complete fact
  with its mechanism and a real takeaway typically lands around 70-110 words.
- STRUCTURE every script in this order: (1) Hook — the shocking stat. (2) Why — the mechanism,
  in plain terms. (3) What people usually get wrong about this. (4) One specific, concrete
  action the viewer can take today. (5) A closing line that explicitly calls back to the
  hook's number or claim.
- VISUAL QUERIES: provide one English search term per structural beat above (hook/mechanism/
  misconception/action), so the video can cut between different footage instead of looping one
  clip for the whole runtime. Each must be visually CONCRETE, not abstract:
    ✅ "man eating chicken" — depicts something visual
    ✅ "person sleeping bed" — depicts something visual
    ❌ "nutrition concept" — too abstract, can't be filmed
    ❌ "health awareness" — too abstract, can't be filmed
- Language: clear, casual English — "Look", "Here's the thing", "Most people think", "Actually"
- tts_text in plain English — same as full_narration
- tts_text must be complete narration — not just hook

GOOD hook examples (all have specific numbers/facts):
- "A 70kg person only needs 70g of protein — you're probably eating double"
- "Walk 30 minutes a day — your blood sugar drops 26%, Harvard says"
- "76% of Indians are Vitamin D deficient and most don't even know"
- "Less than 7 hours of sleep slows muscle growth by 18% — here's why"
- "Diet drinks contain aspartame — WHO flagged it as a cancer risk in 2023"
- "Don't train the same muscle daily — it needs 48 hours to recover"

BAD hooks (vague, no numbers — never write these):
- "Here's what you need to know about protein"
- "Stop making this mistake at the gym"
- "Sleep is really important for fitness"

FACT BANK — use these or similar verified facts:
Protein: 0.8-1g/kg body weight is sufficient (WHO). Excess protein converts to fat/energy, not muscle.
Sleep: <7hrs sleep = 18% less muscle synthesis (Journal of Sleep Research).
Vitamin D: 76% urban Indians deficient (ICMR). Required for testosterone and muscle function.
Walking: 30min walk lowers blood sugar by 26% (Harvard Health). Burns same calories/km as running.
Cardio vs weights: Both burn similar calories. Weights burn more calories for 24hrs AFTER workout (EPOC effect).
Creatine: Most studied supplement. 5g/day increases strength 5-15% (meta-analysis of 22 studies).
Sugar-free: Aspartame in diet drinks — WHO classified as "possibly carcinogenic" in 2023.
Intermittent fasting: 16:8 reduces insulin resistance by 31% in 12 weeks (NEJM 2019).
Sitting: Sitting 8hrs/day increases heart disease risk by 47% even if you exercise (Lancet).
Stress/cortisol: High cortisol stores fat specifically around belly — not arms or legs.

If a fitness/health news headline is provided, use that real news as the base with specific numbers.
Otherwise pick the most shocking specific fact from the topic area.

Respond ONLY with valid JSON. No markdown, no explanation.
""".strip()

RESPONSE_SCHEMA = """
{
  "hook": "shocking opening line, max 12 words, plain English — must also work standalone as a YouTube title with zero added context",
  "body": "caption-friendly English narration covering the mechanism, the common misconception, and a concrete actionable step — as many sentences as the explanation genuinely needs, no padding",
  "full_narration": "complete hook + body in plain English",
  "tts_text": "complete voiceover in plain English — same as full_narration, same length, same meaning, no summarizing",
  "caption": "Instagram caption in English with 3 relevant hashtags",
  "visual_query": "3-word English stock video search term for fitness B-roll — first/main visual, kept for backward compatibility",
  "visual_queries": [
    "2-3 word English search term for the HOOK beat — visually concrete, e.g. 'man eating protein' not 'nutrition concept'",
    "2-3 word English search term for the MECHANISM beat — what's physically happening in the body",
    "2-3 word English search term for the MISCONCEPTION beat — what people usually do wrong",
    "2-3 word English search term for the ACTIONABLE STEP beat — the viewer doing the right thing"
  ]
}
""".strip()

FATAL_STATUS_CODES = {401, 402, 403}


@dataclass
class Script:
    hook: str
    body: str
    full_narration: str
    tts_text: str
    short_narration: str = ""   # 13-sec version — hook only
    short_tts: str = ""         # Short TTS for 13-sec version
    caption: str = ""
    visual_query: str = ""
    visual_queries: list[str] = field(default_factory=list)
    niche: str = ""
    topic: str = ""

    def build_caption(self, niche: str) -> str:
        return (
            f"{self.caption}\n\n"
            f"#fitness #health #fitnessfacts #indianfitness #gym #reels #viral #india"
        )


async def fetch_fitness_news(topic: str) -> str:
    """Fetch latest fitness/health news from Google News RSS."""
    query = topic.replace(" ", "+") + "+health+fitness+india"
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            items = root.findall(".//item")
            if items:
                title = items[0].findtext("title") or ""
                title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()
                logger.info("Fitness news fetched: %s", title[:80])
                return title
    except Exception as exc:
        logger.warning("News fetch failed (non-critical): %s", exc)
    return ""


class ScriptGenerator:
    def __init__(self, settings):
        self.settings = settings

    async def generate(self, niche: Literal["fitness"], topic: str) -> Script:
        news_context = await fetch_fitness_news(topic)

        providers = self.settings.active_providers()
        caller_map = {
            "gemini": self._call_gemini,
            "groq": self._call_groq,
            "deepseek": self._call_deepseek,
        }

        last_error = None
        for provider_name in providers:
            caller = caller_map.get(provider_name)
            if not caller:
                continue
            try:
                logger.info("Trying LLM provider: %s", provider_name)
                raw = await caller(niche=niche, topic=topic, news_context=news_context)
                script = self._parse(raw, niche=niche, topic=topic)
                logger.info(
                    "Script generated via %s | hook: %s",
                    provider_name,
                    script.hook[:50],
                )
                return script
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in FATAL_STATUS_CODES:
                    logger.warning("%s: HTTP %d - skipping", provider_name, code)
                else:
                    logger.warning("%s: HTTP %d - trying next", provider_name, code)
                last_error = exc
            except Exception as exc:
                logger.warning("%s failed: %s - trying next", provider_name, exc)
                last_error = exc

        raise RuntimeError(
            f"All LLM providers failed ({providers}). Last error: {last_error}"
        )

    def _build_user_prompt(self, niche: str, topic: str, news_context: str = "") -> str:
        news_line = (
            f'\n\nTODAY\'S HEALTH NEWS: "{news_context}"\n'
            f"Base the script on this real news. Explain what it means for everyday Indians."
            if news_context
            else "\n\nNo news available; use a shocking fitness fact or myth bust about this topic."
        )
        return (
            f"Write a viral English fitness EDUCATION Reel about: '{topic}'."
            f"{news_line}\n\n"
            f"Use hook/body/full_narration for the on-screen hook text and for Instagram captions.\n"
            f"tts_text must match full_narration exactly in plain English — same content, same length.\n"
            f"tts_text must contain the full hook and body, not a summary and not only the hook.\n"
            f"There is no fixed word count — write the complete explanation (hook, mechanism, "
            f"misconception, actionable step), don't pad with filler, and don't cut it short.\n"
            f"Response schema:\n{RESPONSE_SCHEMA}"
        )

    @retry(
        retry=retry_if_exception_type(httpx.TimeoutException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _call_gemini(self, niche: str, topic: str, news_context: str = "") -> dict:
        prompt = f"{FITNESS_SYSTEM_PROMPT}\n\n{self._build_user_prompt(niche, topic, news_context)}"
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.settings.gemini_model}:generateContent"
                f"?key={self.settings.gemini_api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.65,
                        "maxOutputTokens": 1600,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

    @retry(
        retry=retry_if_exception_type(httpx.TimeoutException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _call_groq(self, niche: str, topic: str, news_context: str = "") -> dict:
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            resp = await client.post(
                f"{self.settings.groq_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
                json={
                    "model": self.settings.groq_model,
                    "messages": [
                        {"role": "system", "content": FITNESS_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": self._build_user_prompt(niche, topic, news_context),
                        },
                    ],
                    "temperature": 0.65,
                    "max_tokens": 1600,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            return json.loads(resp.json()["choices"][0]["message"]["content"])

    @retry(
        retry=retry_if_exception_type(httpx.TimeoutException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _call_deepseek(self, niche: str, topic: str, news_context: str = "") -> dict:
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            resp = await client.post(
                f"{self.settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                json={
                    "model": self.settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": FITNESS_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": self._build_user_prompt(niche, topic, news_context),
                        },
                    ],
                    "temperature": 0.65,
                    "max_tokens": 1600,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            return json.loads(resp.json()["choices"][0]["message"]["content"])

    def _parse(self, raw: dict, niche: str, topic: str) -> Script:
        required = ["hook", "body", "full_narration", "caption", "visual_query"]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ValueError(f"LLM response missing fields: {missing}")

        tts_text = (raw.get("tts_text") or "").strip()
        if len(tts_text.split()) < max(8, int(len(raw["full_narration"].split()) * 0.6)):
            logger.warning("LLM returned incomplete tts_text; using full_narration instead.")
            tts_text = raw["full_narration"]
        tts_text = self._normalize_tts_text(tts_text)

        visual_queries = raw.get("visual_queries")
        if not isinstance(visual_queries, list) or not visual_queries:
            visual_queries = [raw["visual_query"]] if raw.get("visual_query") else []
        visual_queries = [str(q).strip() for q in visual_queries if str(q).strip()]

        return Script(
            hook=raw["hook"].strip(),
            body=raw["body"].strip(),
            full_narration=raw["full_narration"].strip(),
            tts_text=tts_text.strip(),
            caption=raw["caption"].strip(),
            visual_query=raw["visual_query"].strip(),
            visual_queries=visual_queries,
            niche=niche,
            topic=topic,
        )

    def _normalize_tts_text(self, text: str) -> str:
        """Clean up TTS text — ensure plain English, no special chars."""
        # Remove any accidental non-ASCII characters
        text = text.encode("ascii", errors="ignore").decode("ascii")
        # Normalize punctuation for natural TTS flow
        text = text.replace("...", " ")
        text = text.replace("—", ", ")
        return text.strip()
