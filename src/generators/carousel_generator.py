"""
Carousel Generator — creates Instagram carousel slides as PNG images.
Each carousel has 5-7 slides covering a fitness fact topic.
Pure Pillow-based — no external dependencies.
Output: PNG files ready to post as Instagram carousel.
"""

import logging
import textwrap
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("tmp/carousels")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Slide dimensions — Instagram square
SLIDE_W = 1080
SLIDE_H = 1080

# Brand colors
BG_COLOR = (10, 10, 10)          # near black
ACCENT_COLOR = (255, 178, 0)      # golden yellow
TEXT_COLOR = (255, 255, 255)      # white
SUBTEXT_COLOR = (180, 180, 180)   # light grey
HIGHLIGHT_COLOR = (255, 100, 0)   # orange accent

CAROUSEL_SYSTEM_PROMPT = """
You are a viral Instagram carousel creator for Indian fitness Gen Z.
Create a 6-slide carousel about the given fitness topic.

Each slide should have:
- A short punchy headline (max 8 words)
- 1-2 lines of body text with a SPECIFIC fact/number
- An emoji that fits the content

Format as JSON array of 6 slides:
[
  {
    "type": "cover",
    "headline": "eye-catching title with number or shock factor",
    "body": "teaser — make them swipe",
    "emoji": "🏋️"
  },
  {
    "type": "fact",
    "headline": "Fact #1 headline",
    "body": "specific fact with number/study",
    "emoji": "💪"
  },
  ... (4 more fact slides) ...
  {
    "type": "cta",
    "headline": "Save karo yaar!",
    "body": "Follow @fitfacts.india for daily science-backed facts",
    "emoji": "🔥"
  }
]

Rules:
- All text in Roman Hinglish (no Devanagari)
- Every fact slide must have a specific number or study
- Cover must be shocking/curiosity-driven
- Last slide is always CTA with follow message
- Keep text SHORT — these are slides not paragraphs

Respond ONLY with valid JSON array. No markdown.
""".strip()


@dataclass
class CarouselSlide:
    slide_num: int
    slide_type: str
    headline: str
    body: str
    emoji: str
    image_path: Path


@dataclass
class Carousel:
    carousel_id: str
    topic: str
    slides: list[CarouselSlide]
    output_dir: Path


class CarouselGenerator:
    def __init__(self, settings):
        self.settings = settings

    async def generate(self, topic: str, script_hook: str = "") -> Carousel:
        """Generate a full carousel for the given topic."""
        carousel_id = uuid.uuid4().hex[:8]
        logger.info("Generating carousel for topic: %s", topic)

        # Get slide content from LLM
        slides_data = await self._generate_slides(topic, script_hook)

        # Render each slide as PNG
        out_dir = OUTPUT_DIR / f"carousel_{carousel_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        slides = []
        for i, slide_data in enumerate(slides_data):
            img_path = out_dir / f"slide_{i+1:02d}.png"
            self._render_slide(slide_data, i + 1, len(slides_data), img_path)
            slides.append(CarouselSlide(
                slide_num=i + 1,
                slide_type=slide_data.get("type", "fact"),
                headline=slide_data.get("headline", ""),
                body=slide_data.get("body", ""),
                emoji=slide_data.get("emoji", "💪"),
                image_path=img_path,
            ))
            logger.info("Slide %d/%d rendered: %s", i+1, len(slides_data), img_path.name)

        carousel = Carousel(
            carousel_id=carousel_id,
            topic=topic,
            slides=slides,
            output_dir=out_dir,
        )
        logger.info("Carousel complete: %d slides in %s", len(slides), out_dir)
        return carousel

    async def _generate_slides(self, topic: str, hook: str) -> list[dict]:
        """Call LLM to generate slide content."""
        user_prompt = (
            f"Create a 6-slide Instagram carousel about: '{topic}'\n"
            f"Hook from video: '{hook}'\n"
            f"Make it fact-heavy, specific numbers, viral Roman Hinglish."
        )

        # Try Gemini first
        try:
            return await self._call_gemini(user_prompt)
        except Exception as e:
            logger.warning("Gemini failed for carousel: %s — trying Groq", e)

        # Fallback to Groq
        try:
            return await self._call_groq(user_prompt)
        except Exception as e:
            logger.error("All LLMs failed for carousel: %s", e)
            return self._fallback_slides(topic)

    async def _call_gemini(self, prompt: str) -> list[dict]:
        import json
        full_prompt = f"{CAROUSEL_SYSTEM_PROMPT}\n\n{prompt}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.settings.gemini_model}:generateContent"
                f"?key={self.settings.gemini_api_key}",
                json={
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 1000,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

    async def _call_groq(self, prompt: str) -> list[dict]:
        import json
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.settings.groq_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
                json={
                    "model": self.settings.groq_model,
                    "messages": [
                        {"role": "system", "content": CAROUSEL_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 1000,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            result = json.loads(resp.json()["choices"][0]["message"]["content"])
            # Groq returns object, extract array
            if isinstance(result, list):
                return result
            return list(result.values())[0] if result else []

    def _fallback_slides(self, topic: str) -> list[dict]:
        return [
            {"type": "cover", "headline": f"{topic.title()} — Facts You Need!", "body": "Swipe karo yaar 👉", "emoji": "🏋️"},
            {"type": "fact", "headline": "Fact #1", "body": "Science-backed fitness fact.", "emoji": "💪"},
            {"type": "fact", "headline": "Fact #2", "body": "Another important fact.", "emoji": "🔥"},
            {"type": "fact", "headline": "Fact #3", "body": "Key insight.", "emoji": "⚡"},
            {"type": "fact", "headline": "Fact #4", "body": "Remember this.", "emoji": "🧠"},
            {"type": "cta", "headline": "Save karo yaar!", "body": "Follow @fitfacts.india for daily facts", "emoji": "❤️"},
        ]

    def _render_slide(self, slide_data: dict, num: int, total: int, out_path: Path):
        """Render a single slide as PNG using Pillow."""
        from PIL import Image, ImageDraw, ImageFont

        slide_type = slide_data.get("type", "fact")
        headline = slide_data.get("headline", "")
        body = slide_data.get("body", "")
        emoji_text = slide_data.get("emoji", "💪")

        img = Image.new("RGB", (SLIDE_W, SLIDE_H), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Load fonts
        font_xl = self._load_font(72)
        font_lg = self._load_font(52)
        font_md = self._load_font(38)
        font_sm = self._load_font(28)
        font_xs = self._load_font(22)

        if slide_type == "cover":
            self._render_cover(draw, img, headline, body, emoji_text,
                               font_xl, font_lg, font_md, font_sm)
        elif slide_type == "cta":
            self._render_cta(draw, img, headline, body, emoji_text,
                             font_xl, font_lg, font_md)
        else:
            self._render_fact(draw, img, headline, body, emoji_text,
                              num, total, font_xl, font_lg, font_md, font_sm)

        # Slide counter dots
        self._draw_dots(draw, num, total)

        # Brand watermark
        draw.text((SLIDE_W - 20, SLIDE_H - 35), "@fitfacts.india",
                  font=font_xs, fill=SUBTEXT_COLOR, anchor="rs")

        img.save(str(out_path), "PNG", quality=95)

    def _render_cover(self, draw, img, headline, body, emoji, f_xl, f_lg, f_md, f_sm):
        from PIL import ImageDraw
        # Top accent bar
        draw.rectangle([0, 0, SLIDE_W, 8], fill=ACCENT_COLOR)

        # Emoji large
        draw.text((SLIDE_W // 2, 220), emoji, font=f_xl, fill=ACCENT_COLOR, anchor="mm")

        # Channel name
        draw.text((SLIDE_W // 2, 330), "FITFACTS.INDIA",
                  font=f_sm, fill=ACCENT_COLOR, anchor="mm")

        # Main headline
        lines = textwrap.wrap(headline.upper(), width=18)
        y = 430
        for line in lines:
            draw.text((SLIDE_W // 2, y), line, font=f_xl, fill=TEXT_COLOR, anchor="mm")
            y += 85

        # Body teaser
        body_lines = textwrap.wrap(body, width=30)
        y += 20
        for line in body_lines:
            draw.text((SLIDE_W // 2, y), line, font=f_md, fill=SUBTEXT_COLOR, anchor="mm")
            y += 48

        # Swipe indicator
        draw.text((SLIDE_W // 2, SLIDE_H - 80), "SWIPE → →",
                  font=f_sm, fill=ACCENT_COLOR, anchor="mm")

        # Bottom accent bar
        draw.rectangle([0, SLIDE_H - 8, SLIDE_W, SLIDE_H], fill=ACCENT_COLOR)

    def _render_fact(self, draw, img, headline, body, emoji, num, total, f_xl, f_lg, f_md, f_sm):
        # Side accent strip
        draw.rectangle([0, 0, 10, SLIDE_H], fill=ACCENT_COLOR)

        # Fact number badge
        draw.ellipse([50, 50, 150, 150], fill=ACCENT_COLOR)
        draw.text((100, 100), str(num - 1), font=f_lg, fill=BG_COLOR, anchor="mm")

        # Emoji
        draw.text((SLIDE_W // 2, 260), emoji, font=f_xl, fill=TEXT_COLOR, anchor="mm")

        # Headline
        lines = textwrap.wrap(headline, width=20)
        y = 380
        for line in lines:
            draw.text((SLIDE_W // 2, y), line, font=f_lg, fill=ACCENT_COLOR, anchor="mm")
            y += 70

        # Divider line
        draw.rectangle([80, y + 10, SLIDE_W - 80, y + 14], fill=ACCENT_COLOR)
        y += 40

        # Body fact
        body_lines = textwrap.wrap(body, width=32)
        for line in body_lines:
            draw.text((SLIDE_W // 2, y), line, font=f_md, fill=TEXT_COLOR, anchor="mm")
            y += 50

    def _render_cta(self, draw, img, headline, body, emoji, f_xl, f_lg, f_md):
        # Full gradient effect with rectangles
        for i in range(0, SLIDE_H, 4):
            alpha = int(40 * (i / SLIDE_H))
            draw.rectangle([0, i, SLIDE_W, i + 4],
                           fill=(alpha, int(alpha * 0.7), 0))

        # Top + bottom bars
        draw.rectangle([0, 0, SLIDE_W, 10], fill=ACCENT_COLOR)
        draw.rectangle([0, SLIDE_H - 10, SLIDE_W, SLIDE_H], fill=ACCENT_COLOR)

        # Emoji
        draw.text((SLIDE_W // 2, 250), emoji, font=f_xl, fill=ACCENT_COLOR, anchor="mm")

        # Headline
        draw.text((SLIDE_W // 2, 400), headline, font=f_lg, fill=TEXT_COLOR, anchor="mm")

        # Divider
        draw.rectangle([200, 460, SLIDE_W - 200, 466], fill=ACCENT_COLOR)

        # Body
        body_lines = textwrap.wrap(body, width=28)
        y = 510
        for line in body_lines:
            draw.text((SLIDE_W // 2, y), line, font=f_md, fill=TEXT_COLOR, anchor="mm")
            y += 55

        # Follow button style
        draw.rounded_rectangle([240, 700, 840, 780], radius=40, fill=ACCENT_COLOR)
        draw.text((SLIDE_W // 2, 740), "FOLLOW @fitfacts.india",
                  font=self._load_font(30), fill=BG_COLOR, anchor="mm")

    def _draw_dots(self, draw, current: int, total: int):
        """Draw slide progress dots at bottom."""
        dot_r = 6
        spacing = 22
        total_w = total * spacing
        start_x = (SLIDE_W - total_w) // 2
        y = SLIDE_H - 30

        for i in range(total):
            x = start_x + i * spacing + dot_r
            if i + 1 == current:
                draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r],
                             fill=ACCENT_COLOR)
            else:
                draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r],
                             fill=SUBTEXT_COLOR)

    def _load_font(self, size: int):
        from PIL import ImageFont
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        for fp in candidates:
            try:
                return ImageFont.truetype(fp, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()
