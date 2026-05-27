"""
Script Generator — Fitness Niche
Supports three LLM providers: Gemini (primary), Groq (fallback), DeepSeek.
Fetches real fitness/health news from Google News RSS before generating.
Scripts are fact-based, myth-busting — not gym ads.
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
Your job is to TEACH fitness science — not sell gym memberships or supplements.

STRICT RULES:
- NEVER say "gym join karo", "protein lo", "trainer se poocho" — ye ad nahi hai
- ALWAYS lead with a shocking fitness fact, myth bust, or real health news
- Use relatable comparisons: chai, roti, office chair, 9-to-5 job, Netflix binge
- Explain the science simply — WHY does this happen in the body
- End with something that makes them go "yaar ye toh pata hi nahi tha" — shareable
- Hook must stop someone mid-scroll in 2 seconds
- Language: Natural Hinglish — "Yaar", "soch", "matlab", "dekho", "actually", "sunlo"
- Total narration: 120-150 words

GOOD hook examples:
- "Roz gym jaate ho? Ye ek galti sab karte hain jo results rok deti hai"
- "8 ghante sone ke baad bhi thaka feel hota hai? Ye reason hai"
- "Walking vs Running — calorie burn mein fark sirf 20% hai, science bolta hai"
- "India mein 70% log Vitamin D deficient hain — aur unhe pata bhi nahi"
- "Sugar-free drinks peete ho? Study ne kaha ye zyada dangerous hai"

BAD examples (never do this):
- "Gym join karo fit rehne ke liye"
- "Protein shake piyo muscles ke liye"  
- Generic "exercise karo healthy raho" advice

If a fitness/health news headline is provided, base the script on that real news.
Otherwise use a shocking fitness fact or myth bust relevant to the topic.

Respond ONLY with valid JSON. No markdown, no explanation.
""".strip()

RESPONSE_SCHEMA = """
{
  "hook": "shocking opening line (max 12 words, must be a fact/myth bust — not advice)",
  "body": "main narration — explain the fact/science, why it matters, real numbers (3-4 sentences)",
  "full_narration": "complete script hook + body as one paragraph",
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
    caption: str
    visual_query: str
    niche: str
    topic: str

    def build_caption(self, niche: str) -> str:
        return (
            f"{self.caption}\n\n"
            f"#fitness #health #fitnessfacts #indianfitness #gym #reels #viral #india"
        )


async def fetch_fitness_news(topic: str) -> str:
    """
    Fetch latest fitness/health news from Google News RSS.
    Free, no API key needed.
    """
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
    except Exception as e:
        logger.warning("News fetch failed (non-critical): %s", e)
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
                logger.info("Script generated via %s | hook: %s", provider_name, script.hook[:50])
                return script
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in FATAL_STATUS_CODES:
                    logger.warning("%s: HTTP %d — skipping", provider_name, code)
                else:
                    logger.warning("%s: HTTP %d — trying next", provider_name, code)
                last_error = exc
            except Exception as exc:
                logger.warning("%s failed: %s — trying next", provider_name, exc)
                last_error = exc

        raise RuntimeError(
            f"All LLM providers failed ({providers}). Last error: {last_error}"
        )

    def _build_user_prompt(self, niche: str, topic: str, news_context: str = "") -> str:
        news_line = (
            f"\n\nTODAY'S HEALTH NEWS: \"{news_context}\"\n"
            f"Base the script on this real news. Explain what it means for everyday Indians."
            if news_context
            else "\n\nNo news available — use a shocking fitness fact or myth bust about this topic."
        )
        return (
            f"Write a viral Hinglish fitness EDUCATION Reel about: '{topic}'."
            f"{news_line}\n\n"
            f"Remember: Teach a fact. Bust a myth. Shock them first. No ads.\n"
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
                        "temperature": 0.85,
                        "maxOutputTokens": 700,
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
                        {"role": "user", "content": self._build_user_prompt(niche, topic, news_context)},
                    ],
                    "temperature": 0.85,
                    "max_tokens": 700,
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
                        {"role": "user", "content": self._build_user_prompt(niche, topic, news_context)},
                    ],
                    "temperature": 0.85,
                    "max_tokens": 700,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            return json.loads(resp.json()["choices"][0]["message"]["content"])

    def _parse(self, raw: dict, niche: str, topic: str) -> Script:
        required = ["hook", "body", "full_narration", "caption", "visual_query"]
        missing = [k for k in required if not raw.get(k)]
        if missing:
            raise ValueError(f"LLM response missing fields: {missing}")
        return Script(
            hook=raw["hook"].strip(),
            body=raw["body"].strip(),
            full_narration=raw["full_narration"].strip(),
            caption=raw["caption"].strip(),
            visual_query=raw["visual_query"].strip(),
            niche=niche,
            topic=topic,
        )
