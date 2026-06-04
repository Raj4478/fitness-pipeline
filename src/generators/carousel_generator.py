"""
Carousel Generator — Upload-ready Instagram carousel slides.
Format: 1080x1350 (4:5 portrait — maximum feed real estate)
Output: PNG slides + caption.txt ready to copy-paste
"""

import logging
import textwrap
import uuid
import json
from dataclasses import dataclass
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("tmp/carousels")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Instagram 4:5 portrait — best for feed
SLIDE_W = 1080
SLIDE_H = 1350

# Brand palette
BG_DARK     = (8, 8, 8)
BG_CARD     = (18, 18, 18)
YELLOW      = (255, 186, 0)
ORANGE      = (255, 100, 0)
WHITE       = (255, 255, 255)
GREY        = (160, 160, 160)
GREY_DARK   = (40, 40, 40)

LOGO_PATH = Path("assets/logo.png")

CAROUSEL_PROMPT = """
You are a viral Instagram carousel creator for Indian fitness Gen Z.
Create exactly 6 slides about the given topic.

Return a JSON array of exactly 6 objects:
[
  {
    "type": "cover",
    "headline": "SHORT shocking headline max 6 words in Roman Hinglish",
    "subheadline": "1 line teaser — swipe karo",
    "fact": "",
    "emoji": "🏋️"
  },
  {
    "type": "fact",
    "headline": "Fact #1 — short label",
    "subheadline": "one line context",
    "fact": "The specific stat/number/study — max 20 words",
    "emoji": "💪"
  },
  {
    "type": "fact",
    "headline": "Fact #2 — short label",
    "subheadline": "one line context",
    "fact": "specific stat with number",
    "emoji": "🔥"
  },
  {
    "type": "fact",
    "headline": "Fact #3 — short label",
    "subheadline": "one line context",
    "fact": "specific stat with number",
    "emoji": "⚡"
  },
  {
    "type": "fact",
    "headline": "Fact #4 — short label",
    "subheadline": "one line context",
    "fact": "specific stat with number",
    "emoji": "🧠"
  },
  {
    "type": "cta",
    "headline": "Save karo yaar!",
    "subheadline": "Daily fitness facts ke liye follow karo",
    "fact": "@fitfacts.india",
    "emoji": "❤️"
  }
]

STRICT RULES:
- All text Roman Hinglish — NO Devanagari
- Every fact slide must have a real number or study
- Keep all text SHORT — these are slides not paragraphs  
- headline max 6 words
- fact max 20 words
- Return ONLY the JSON array, nothing else
""".strip()


@dataclass
class CarouselSlide:
    slide_num: int
    slide_type: str
    headline: str
    subheadline: str
    fact: str
    emoji: str
    image_path: Path


@dataclass 
class Carousel:
    carousel_id: str
    topic: str
    slides: list
    output_dir: Path
    caption_path: Path


class CarouselGenerator:
    def __init__(self, settings):
        self.settings = settings

    async def generate(self, topic: str, script_hook: str = "", hashtags: str = "") -> Carousel:
        carousel_id = uuid.uuid4().hex[:8]
        logger.info("Generating carousel: %s", topic)

        slides_data = await self._get_slides(topic, script_hook)

        out_dir = OUTPUT_DIR / f"carousel_{carousel_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        slides = []
        for i, sd in enumerate(slides_data[:6]):
            img_path = out_dir / f"slide_{i+1:02d}.png"
            self._render_slide(sd, i + 1, len(slides_data[:6]), img_path)
            slides.append(CarouselSlide(
                slide_num=i + 1,
                slide_type=sd.get("type", "fact"),
                headline=sd.get("headline", ""),
                subheadline=sd.get("subheadline", ""),
                fact=sd.get("fact", ""),
                emoji=sd.get("emoji", "💪"),
                image_path=img_path,
            ))
            logger.info("Slide %d/%d done", i + 1, len(slides_data[:6]))

        # Write caption file
        caption_path = out_dir / "CAPTION.txt"
        self._write_caption(caption_path, topic, script_hook, slides, hashtags)

        carousel = Carousel(
            carousel_id=carousel_id,
            topic=topic,
            slides=slides,
            output_dir=out_dir,
            caption_path=caption_path,
        )
        logger.info("Carousel complete: %s", out_dir)
        return carousel

    async def _get_slides(self, topic: str, hook: str) -> list:
        prompt = f"Topic: {topic}\nHook from video: {hook}\nCreate 6 slides with real facts."
        for caller in [self._gemini, self._groq]:
            try:
                result = await caller(prompt)
                if isinstance(result, list) and len(result) >= 4:
                    return result
            except Exception as e:
                logger.warning("LLM failed: %s", e)
        return self._fallback(topic)

    async def _gemini(self, prompt: str) -> list:
        full = f"{CAROUSEL_PROMPT}\n\n{prompt}"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.settings.gemini_model}:generateContent?key={self.settings.gemini_api_key}",
                json={"contents": [{"parts": [{"text": full}]}],
                      "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1200,
                                           "responseMimeType": "application/json"}},
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

    async def _groq(self, prompt: str) -> list:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self.settings.groq_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
                json={"model": self.settings.groq_model,
                      "messages": [{"role": "system", "content": CAROUSEL_PROMPT},
                                   {"role": "user", "content": prompt}],
                      "temperature": 0.7, "max_tokens": 1200,
                      "response_format": {"type": "json_object"}},
            )
            r.raise_for_status()
            data = json.loads(r.json()["choices"][0]["message"]["content"])
            return data if isinstance(data, list) else list(data.values())[0]

    def _fallback(self, topic: str) -> list:
        return [
            {"type": "cover", "headline": f"{topic.title()} Facts!", "subheadline": "Swipe karo yaar", "fact": "", "emoji": "🏋️"},
            {"type": "fact", "headline": "Fact #1", "subheadline": "Science says", "fact": "Key fitness fact with number.", "emoji": "💪"},
            {"type": "fact", "headline": "Fact #2", "subheadline": "Study shows", "fact": "Another important fact.", "emoji": "🔥"},
            {"type": "fact", "headline": "Fact #3", "subheadline": "Remember this", "fact": "Critical insight.", "emoji": "⚡"},
            {"type": "fact", "headline": "Fact #4", "subheadline": "Most people don't know", "fact": "Surprising stat.", "emoji": "🧠"},
            {"type": "cta", "headline": "Save karo yaar!", "subheadline": "Daily fitness facts ke liye follow karo", "fact": "@fitfacts.india", "emoji": "❤️"},
        ]

    # ── Rendering ──────────────────────────────────────────────────────

    def _render_slide(self, sd: dict, num: int, total: int, path: Path):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (SLIDE_W, SLIDE_H), BG_DARK)
        draw = ImageDraw.Draw(img)
        t = sd.get("type", "fact")

        if t == "cover":
            self._draw_cover(draw, img, sd, num, total)
        elif t == "cta":
            self._draw_cta(draw, img, sd, num, total)
        else:
            self._draw_fact(draw, img, sd, num, total)

        img.save(str(path), "PNG")

    def _draw_cover(self, draw, img, sd, num, total):
        from PIL import Image, ImageDraw, ImageFilter

        # Yellow top bar
        draw.rectangle([0, 0, SLIDE_W, 12], fill=YELLOW)

        # Channel branding strip
        draw.rectangle([0, 60, SLIDE_W, 130], fill=GREY_DARK)
        draw.text((SLIDE_W // 2, 95), "FITFACTS.INDIA",
                  font=self._font(32), fill=YELLOW, anchor="mm")

        # Logo if exists
        if LOGO_PATH.exists():
            try:
                logo = Image.open(LOGO_PATH).convert("RGBA")
                logo = logo.resize((160, 160))
                img.paste(logo, (SLIDE_W // 2 - 80, 160), logo)
            except Exception:
                pass

        y_start = 360 if LOGO_PATH.exists() else 200

        # Emoji
        draw.text((SLIDE_W // 2, y_start), sd.get("emoji", "🏋️"),
                  font=self._font(80), fill=WHITE, anchor="mm")

        # Headline — big, yellow
        headline = sd.get("headline", "").upper()
        lines = textwrap.wrap(headline, width=16)
        y = y_start + 110
        for line in lines:
            draw.text((SLIDE_W // 2, y), line, font=self._font(72),
                      fill=YELLOW, anchor="mm")
            y += 88

        # Subheadline
        sub = sd.get("subheadline", "")
        if sub:
            y += 10
            for line in textwrap.wrap(sub, width=30):
                draw.text((SLIDE_W // 2, y), line, font=self._font(36),
                          fill=GREY, anchor="mm")
                y += 48

        # Swipe hint
        draw.text((SLIDE_W // 2, SLIDE_H - 130), "SWIPE FOR FACTS  →",
                  font=self._font(30), fill=YELLOW, anchor="mm")

        # Slide counter + bottom bar
        self._draw_bottom(draw, num, total)

    def _draw_fact(self, draw, img, sd, num, total):
        # Left accent strip
        draw.rectangle([0, 0, 10, SLIDE_H], fill=YELLOW)

        # Slide number badge top-right
        draw.ellipse([SLIDE_W - 110, 40, SLIDE_W - 40, 110], fill=YELLOW)
        draw.text((SLIDE_W - 75, 75), f"{num-1}/{total-1}",
                  font=self._font(28), fill=BG_DARK, anchor="mm")

        # Emoji — large
        draw.text((SLIDE_W // 2, 240), sd.get("emoji", "💪"),
                  font=self._font(100), fill=WHITE, anchor="mm")

        # Headline
        headline = sd.get("headline", "")
        lines = textwrap.wrap(headline, width=20)
        y = 380
        for line in lines:
            draw.text((SLIDE_W // 2, y), line, font=self._font(54),
                      fill=YELLOW, anchor="mm")
            y += 68

        # Yellow divider line
        y += 20
        draw.rectangle([60, y, SLIDE_W - 60, y + 5], fill=YELLOW)
        y += 30

        # Subheadline
        sub = sd.get("subheadline", "")
        if sub:
            draw.text((SLIDE_W // 2, y), sub, font=self._font(32),
                      fill=GREY, anchor="mm")
            y += 55

        # Fact box — card style
        fact = sd.get("fact", "")
        if fact:
            fact_lines = textwrap.wrap(fact, width=28)
            box_h = len(fact_lines) * 54 + 50
            box_y = y + 10
            # Card background
            draw.rounded_rectangle(
                [50, box_y, SLIDE_W - 50, box_y + box_h],
                radius=20, fill=GREY_DARK
            )
            # Left accent on card
            draw.rounded_rectangle(
                [50, box_y, 60, box_y + box_h],
                radius=0, fill=ORANGE
            )
            ty = box_y + 25
            for fl in fact_lines:
                draw.text((SLIDE_W // 2, ty), fl, font=self._font(40),
                          fill=WHITE, anchor="mm")
                ty += 54

        self._draw_bottom(draw, num, total)

    def _draw_cta(self, draw, img, sd, num, total):
        from PIL import Image

        # Gradient-style background bands
        for i in range(0, SLIDE_H, 6):
            alpha = int(30 * (i / SLIDE_H))
            draw.rectangle([0, i, SLIDE_W, i + 6],
                           fill=(alpha, int(alpha * 0.6), 0))

        # Top bar
        draw.rectangle([0, 0, SLIDE_W, 12], fill=YELLOW)

        # Logo
        if LOGO_PATH.exists():
            try:
                logo = Image.open(LOGO_PATH).convert("RGBA")
                logo = logo.resize((220, 220))
                img.paste(logo, (SLIDE_W // 2 - 110, 120), logo)
            except Exception:
                pass

        y = 380

        # Emoji
        draw.text((SLIDE_W // 2, y), sd.get("emoji", "❤️"),
                  font=self._font(80), fill=WHITE, anchor="mm")
        y += 110

        # Headline
        draw.text((SLIDE_W // 2, y), sd.get("headline", "Save karo yaar!"),
                  font=self._font(60), fill=WHITE, anchor="mm")
        y += 80

        # Subheadline
        sub = sd.get("subheadline", "")
        for line in textwrap.wrap(sub, width=28):
            draw.text((SLIDE_W // 2, y), line, font=self._font(36),
                      fill=GREY, anchor="mm")
            y += 50
        y += 20

        # Follow button
        draw.rounded_rectangle([120, y, SLIDE_W - 120, y + 90],
                               radius=45, fill=YELLOW)
        draw.text((SLIDE_W // 2, y + 45),
                  f"FOLLOW {sd.get('fact', '@fitfacts.india')}",
                  font=self._font(34), fill=BG_DARK, anchor="mm")
        y += 110

        # Save reminder
        draw.text((SLIDE_W // 2, y), "🔖 Save this for later",
                  font=self._font(30), fill=GREY, anchor="mm")

        # Bottom bar
        draw.rectangle([0, SLIDE_H - 12, SLIDE_W, SLIDE_H], fill=YELLOW)

    def _draw_bottom(self, draw, num: int, total: int):
        """Progress bar at bottom."""
        bar_h = 6
        bar_y = SLIDE_H - bar_h
        # Background
        draw.rectangle([0, bar_y, SLIDE_W, SLIDE_H], fill=GREY_DARK)
        # Progress
        progress_w = int(SLIDE_W * (num / total))
        draw.rectangle([0, bar_y, progress_w, SLIDE_H], fill=YELLOW)

    def _font(self, size: int):
        from PIL import ImageFont
        for fp in [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]:
            try:
                return ImageFont.truetype(fp, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()

    def _write_caption(self, path: Path, topic: str, hook: str,
                       slides: list, hashtags: str):
        """Write upload-ready caption + hashtags + posting guide."""
        # Build caption from slide content
        facts = [s for s in slides if s.slide_type == "fact"]
        fact_lines = "\n".join(
            f"{'💪🔥⚡🧠'[i % 4]} {s.headline}: {s.fact}"
            for i, s in enumerate(facts)
        )

        caption = f"""{hook}

{fact_lines}

Save this post — aaj se implement karo! 🏋️

━━━━━━━━━━━━━━━━━━━
{hashtags or '#fitness #gym #gymmotivation #fitnessmotivation #reels #gymlife #fitfam #bodybuilding #workout #healthylifestyle #fitnessindia #indianfitness #fitnessfacts #gymscience #fitfactsindia'}
━━━━━━━━━━━━━━━━━━━"""

        guide = f"""
════════════════════════════════
📱 INSTAGRAM POSTING GUIDE
════════════════════════════════

TOPIC: {topic}
SLIDES: {len(slides)} (slide_01.png → slide_0{len(slides)}.png)

STEP 1 — Open Instagram
STEP 2 — New Post → Select Multiple Photos
STEP 3 — Add slide_01.png through slide_0{len(slides)}.png IN ORDER
STEP 4 — Copy-paste caption below
STEP 5 — Post at 7AM / 1PM / 9PM IST for best reach

════════════════════════════════
📝 COPY-PASTE CAPTION:
════════════════════════════════

{caption}

════════════════════════════════
⏰ BEST POSTING TIMES (IST):
  Morning: 7:00 AM - 8:00 AM
  Afternoon: 12:30 PM - 1:30 PM  
  Evening: 9:00 PM - 10:00 PM

💡 PRO TIPS:
  • Post Reel first, Carousel next day
  • Reply to ALL comments in first 30 mins
  • Add location: India for extra reach
  • Use stories to tease the carousel
════════════════════════════════
"""
        path.write_text(guide, encoding="utf-8")
        logger.info("Caption file written: %s", path)
