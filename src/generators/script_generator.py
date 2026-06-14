"""
Script Generator - Fitness Niche
Supports Gemini, Groq, and DeepSeek.
Fetches real fitness/health news from Google News RSS before generating.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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
You are a viral Hinglish fitness educator for Indian Gen Z (18-28 yrs) on Instagram Reels.
Your job is to TEACH with REAL NUMBERS and SPECIFIC FACTS — not vague general advice.

STRICT RULES:
- NEVER say "gym join karo", "protein lo", "trainer se poocho" — ye ad nahi hai
- EVERY script MUST contain at least 2 specific facts with numbers. Examples:
    ✅ "1 gram protein per kg bodyweight — 70kg insaan ke liye sirf 70g chahiye"
    ✅ "Study mein 8 weeks mein 2kg muscle gain hua sirf 0.7g/kg protein se"
    ✅ "India mein 76% urban adults Vitamin D deficient hain — ICMR 2023 data"
    ✅ "30 min walk se blood sugar 26% drop hoti hai — Harvard Health 2022"
    ✅ "Muscle 48-72 ghante mein recover hoti hai, roz same muscle mat thao"
    ❌ "Zyada protein body ke liye accha nahi" — TOO VAGUE, no numbers
    ❌ "Walking bahut acchi exercise hai" — TOO VAGUE, no facts
- Lead with a SPECIFIC shocking number or stat in the hook
- Use real study references casually: "Harvard ne bola", "ICMR data", "2023 study mein"
- Compare numbers to relatable things: "70g protein = 3 eggs + 1 cup dahi + 100g chicken"
- Explain the mechanism: WHY does this happen in the body — in 1 simple sentence
- End with a specific actionable insight — not generic advice
- Hook must have a NUMBER or specific claim — never vague
- Total narration: 35-45 words ONLY (15 second video — every word counts)
- Captions: short punchy sentences, easy to read on screen
- Language: casual Hinglish — "Yaar", "sun", "soch", "dekho", "actually"
- tts_text in Devanagari Hindi/Hinglish for proper TTS pronunciation
- tts_text must be complete narration — not just hook
- Never use formal Hindi: aavashyak, kshamata, adhik — use zaroorat, zyada, etc.

GOOD hook examples (all have specific numbers/facts):
- "70kg insaan ko sirf 70g protein chahiye — tu shayad double kha raha hai"
- "Roz 30 min walk karo — blood sugar 26% drop hoti hai, Harvard study"
- "India mein 76% log Vitamin D deficient hain — aur unhe pata bhi nahi"
- "8 ghante neend na lo toh muscle 18% slower grow karti hai — ye study suno"
- "Sugar-free drink mein aspartame hota hai — 2023 WHO ne cancer risk flag kiya"
- "Same muscle roz mat thao — 48 ghante recovery time chahiye science ke mutabiq"

BAD hooks (vague, no numbers — never write these):
- "Protein ke baare mein ye jaano"
- "Gym mein ye galti mat karna"
- "Sleep bahut zaruri hai fitness ke liye"

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
  "hook": "shocking opening line, max 12 words, Roman Hinglish",
  "body": "caption-friendly Roman Hinglish narration with 4-6 short sentences",
  "full_narration": "complete hook + body in the same caption-friendly Roman Hinglish",
  "tts_text": "complete 35-45 word voiceover, same meaning as full_narration, written in Devanagari Hindi/Hinglish for better TTS pronunciation",
  "caption": "Instagram caption with 3 relevant hashtags",
  "visual_query": "3-word English stock video search term for fitness B-roll"
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
    short_tts: str = ""         # Devanagari TTS for 13-sec
    caption: str = ""
    visual_query: str = ""
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
            f"Write a viral Hinglish fitness EDUCATION Reel about: '{topic}'."
            f"{news_line}\n\n"
            f"Use hook/body/full_narration for on-screen Roman Hinglish captions.\n"
            f"Use tts_text only for voiceover pronunciation. Write tts_text in Devanagari Hindi/Hinglish.\n"
            f"tts_text must contain the full hook and body, not a summary and not only the hook.\n"
            f"Keep subtitle sentences short and punchy. No long paragraphs.\n"
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
                        "maxOutputTokens": 900,
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
                    "max_tokens": 900,
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
                    "max_tokens": 900,
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
        return Script(
            hook=raw["hook"].strip(),
            body=raw["body"].strip(),
            full_narration=raw["full_narration"].strip(),
            tts_text=tts_text.strip(),
            caption=raw["caption"].strip(),
            visual_query=raw["visual_query"].strip(),
            niche=niche,
            topic=topic,
        )

    def _normalize_tts_text(self, text: str) -> str:
        replacements = {
            "आवश्यकता": "ज़रूरत",
            "आवश्यक": "ज़रूरी",
            "अतिरिक्त": "एक्स्ट्रा",
            "ऊर्जा": "एनर्जी",
            "मिथ्या": "मिथ",
            "भ्रमित": "कन्फ्यूज़",
            "शरीर": "बॉडी",
            "संग्रह": "स्टोर",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
