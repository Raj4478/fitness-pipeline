#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import wave
from array import array
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DURATION = 19.2
WIDTH = 1080
HEIGHT = 1920
SCENE_DURATIONS = (3.0, 3.4, 3.6, 5.4, 3.8)
MAX_TELEGRAM_BYTES = 49 * 1024 * 1024
KRISHNA_SHA256 = "2e4b59b4afb465314e510707faa0e96de46641cbb67b4b12990ffb3c4eb66c73"
MOODS = {
    "peaceful": {"label": "Peaceful", "brightness": -0.03, "saturation": 0.90, "tempo": 0.86},
    "devotional": {"label": "Bhakti", "brightness": 0.02, "saturation": 1.03, "tempo": 0.94},
    "healing": {"label": "Healing", "brightness": 0.01, "saturation": 0.86, "tempo": 0.82},
    "motivational": {"label": "Motivational", "brightness": 0.04, "saturation": 1.10, "tempo": 1.12},
    "reflective": {"label": "Reflective", "brightness": -0.07, "saturation": 0.80, "tempo": 0.78},
    "joyful": {"label": "Joyful", "brightness": 0.05, "saturation": 1.14, "tempo": 1.08},
}

KRISHNA_VISUAL_GUIDE = (
    "Lord Krishna portrayed respectfully in recognizable traditional Indian devotional iconography: "
    "youthful serene face, traditional luminous blue complexion, large compassionate almond-shaped dark eyes, "
    "gentle peaceful smile, subtle Vaishnava tilak, one elegant peacock feather set naturally in a refined jeweled mukut, "
    "yellow-gold pitambar with realistic fabric folds, Vaijayanti flower garland, delicate gold kundal and ornaments, "
    "polished wooden bansuri held naturally with anatomically correct fingers, subtle sacred radiance rather than fantasy glow; "
    "exactly two arms, balanced human anatomy, symmetrical eyes, natural hands, no extra limbs, no duplicated fingers, "
    "no fantasy armor, no weapon, no baby depiction, no caricature"
)
ASSET_PARTS = [
    ASSETS / "krishna-intro.00a.b64",
    ASSETS / "krishna-intro.00b.b64",
    *[ASSETS / f"krishna-intro.chunk{i:02d}.b64" for i in range(1, 9)],
    ASSETS / "krishna-intro.09a.b64",
    ASSETS / "krishna-intro.09b.b64",
]


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def clean(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit].rstrip()


def ass_escape(value: str) -> str:
    return str(value).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def subtitle_lines(value: str, max_chars: int = 28) -> list[str]:
    """Return one or two balanced subtitle lines without cutting words."""
    text = clean(value, 180)
    words = text.split()
    if not words:
        return []
    if len(text) <= max_chars or len(words) == 1:
        return [text]

    best: tuple[float, list[str]] | None = None
    for split in range(1, len(words)):
        left = " ".join(words[:split])
        right = " ".join(words[split:])
        longest = max(len(left), len(right))
        overflow = max(0, longest - max_chars)
        score = abs(len(left) - len(right)) + overflow * 8
        candidate = [left, right]
        if best is None or score < best[0]:
            best = (score, candidate)
    return best[1] if best else [text]


def format_ass_subtitle(value: str) -> str:
    # Escape each line independently so ASS's \N line-break control is preserved.
    return r"\N".join(ass_escape(line) for line in subtitle_lines(value))


def materialize_krishna(path: Path) -> Path:
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in ASSET_PARTS)
    payload = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != KRISHNA_SHA256:
        raise RuntimeError(f"krishna_asset_hash_mismatch:{digest}")
    path.write_bytes(payload)
    return path


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        draw.line((0, y, width, y), fill=color)
    return image


def _cover(image: Image.Image, zoom: float = 1.0, x_bias: float = 0.0, y_bias: float = 0.0) -> Image.Image:
    image = image.convert("RGB")
    scale = max(WIDTH / image.width, HEIGHT / image.height) * zoom
    resized = image.resize(
        (max(WIDTH, int(image.width * scale)), max(HEIGHT, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    overflow_x = max(0, resized.width - WIDTH)
    overflow_y = max(0, resized.height - HEIGHT)
    left = int(overflow_x * max(0.0, min(1.0, 0.5 + x_bias * 0.5)))
    top = int(overflow_y * max(0.0, min(1.0, 0.5 + y_bias * 0.5)))
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def _glow(base: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> Image.Image:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    for r in range(radius, 0, -24):
        strength = int(alpha * (1.0 - r / radius) ** 0.6)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, strength))
    layer = layer.filter(ImageFilter.GaussianBlur(max(12, radius // 10)))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def _krishna_scene(source: Image.Image, *, zoom: float, x_bias: float, y_bias: float, tint: tuple[int, int, int], tint_alpha: int, glow_center: tuple[int, int]) -> Image.Image:
    frame = _cover(source, zoom=zoom, x_bias=x_bias, y_bias=y_bias)
    frame = ImageEnhance.Contrast(frame).enhance(1.04)
    frame = ImageEnhance.Sharpness(frame).enhance(1.08)
    tint_layer = Image.new("RGBA", frame.size, (*tint, tint_alpha))
    frame = Image.alpha_composite(frame.convert("RGBA"), tint_layer).convert("RGB")
    return _glow(frame, glow_center, 470, (255, 205, 104), 86)


def _scene_restless_night() -> Image.Image:
    image = _gradient((WIDTH, HEIGHT), (8, 17, 39), (19, 29, 49))
    image = _glow(image, (820, 330), 360, (91, 142, 216), 72)
    draw = ImageDraw.Draw(image)

    # Window + moon.
    draw.rounded_rectangle((655, 135, 990, 690), radius=34, fill=(14, 29, 56), outline=(86, 112, 158), width=5)
    draw.line((820, 140, 820, 688), fill=(66, 91, 133), width=5)
    draw.line((660, 414, 986, 414), fill=(66, 91, 133), width=5)
    draw.ellipse((750, 205, 880, 335), fill=(238, 238, 218))

    # Bed and pillow.
    draw.rounded_rectangle((0, 1160, 1080, 1919), radius=70, fill=(19, 26, 43))
    draw.rounded_rectangle((72, 1120, 480, 1385), radius=85, fill=(43, 51, 69))
    draw.rectangle((0, 1435, 1080, 1920), fill=(26, 31, 46))

    # Restless seated silhouette.
    draw.ellipse((300, 700, 520, 920), fill=(7, 10, 17))
    draw.polygon([(330, 900), (520, 900), (650, 1435), (200, 1435)], fill=(7, 10, 17))
    draw.line((490, 920, 640, 790), fill=(7, 10, 17), width=64)
    draw.ellipse((600, 720, 670, 790), fill=(7, 10, 17))

    # Small phone glow on bedside table.
    image = _glow(image, (830, 1325), 210, (78, 142, 229), 55)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((785, 1230, 875, 1410), radius=18, fill=(25, 30, 42), outline=(104, 145, 206), width=4)
    return image


def _scene_reflection_sunrise() -> Image.Image:
    image = _gradient((WIDTH, HEIGHT), (33, 48, 88), (245, 168, 94))
    image = _glow(image, (800, 710), 420, (255, 198, 96), 105)
    draw = ImageDraw.Draw(image)

    # Sun, river and distant temple skyline.
    draw.ellipse((725, 560, 875, 710), fill=(255, 225, 155))
    draw.rectangle((0, 1010, WIDTH, HEIGHT), fill=(72, 92, 110))
    for y in range(1030, 1640, 75):
        draw.line((0, y, WIDTH, y + 18), fill=(107, 128, 139), width=3)
    draw.rectangle((105, 760, 260, 1015), fill=(31, 39, 55))
    draw.polygon([(75, 760), (182, 620), (290, 760)], fill=(31, 39, 55))
    draw.rectangle((880, 790, 1015, 1015), fill=(35, 42, 55))
    draw.polygon([(850, 790), (948, 660), (1045, 790)], fill=(35, 42, 55))

    # Ghat steps.
    for index in range(6):
        y = 1380 + index * 90
        draw.rectangle((0, y, WIDTH, y + 54), fill=(72 + index * 5, 65 + index * 4, 60 + index * 3))

    # Seated reflective silhouette.
    draw.ellipse((390, 920, 545, 1075), fill=(19, 24, 34))
    draw.polygon([(420, 1050), (550, 1050), (655, 1415), (300, 1415)], fill=(19, 24, 34))
    draw.line((425, 1200, 280, 1370), fill=(19, 24, 34), width=62)
    draw.line((535, 1200, 700, 1370), fill=(19, 24, 34), width=62)

    # Birds.
    draw.arc((160, 400, 235, 445), 200, 340, fill=(35, 42, 60), width=4)
    draw.arc((225, 390, 305, 445), 200, 340, fill=(35, 42, 60), width=4)
    return image


def _scene_phone_down() -> Image.Image:
    image = _gradient((WIDTH, HEIGHT), (92, 49, 29), (24, 26, 32))
    image = _glow(image, (775, 610), 430, (255, 174, 66), 120)
    draw = ImageDraw.Draw(image)

    # Warm tabletop.
    draw.rectangle((0, 1050, WIDTH, HEIGHT), fill=(83, 50, 35))

    # Diya and flame.
    draw.ellipse((690, 1000, 930, 1140), fill=(157, 85, 29))
    draw.polygon([(810, 1010), (755, 910), (815, 800), (865, 920)], fill=(255, 199, 74))
    draw.polygon([(812, 980), (785, 925), (815, 865), (842, 930)], fill=(255, 242, 178))

    # Phone face-down.
    draw.rounded_rectangle((165, 1190, 525, 1750), radius=48, fill=(30, 32, 38), outline=(111, 93, 80), width=6)
    draw.ellipse((315, 1240, 375, 1300), fill=(56, 60, 68))

    # Mala: curved string + beads.
    draw.arc((505, 1140, 1035, 1810), 62, 300, fill=(214, 168, 103), width=7)
    for angle in range(70, 295, 16):
        rad = math.radians(angle)
        cx = 770 + int(255 * math.cos(rad))
        cy = 1470 + int(315 * math.sin(rad))
        draw.ellipse((cx - 15, cy - 15, cx + 15, cy + 15), fill=(222, 174, 104))
    draw.ellipse((735, 1760, 790, 1815), fill=(222, 174, 104))
    draw.line((762, 1810, 762, 1900), fill=(208, 150, 74), width=8)
    return image


def generate_fallback_story_scenes(output_root: Path, mood: str) -> list[Path]:
    """Deterministic five-frame fallback used only by local/CI dry runs."""
    output_root.mkdir(parents=True, exist_ok=True)
    krishna_path = materialize_krishna(output_root / "krishna-source.jpg")
    krishna = Image.open(krishna_path).convert("RGB")

    scenes = [
        _scene_restless_night(),
        _krishna_scene(
            krishna,
            zoom=1.08,
            x_bias=0.08,
            y_bias=-0.10,
            tint=(8, 32, 76),
            tint_alpha=54,
            glow_center=(720, 560),
        ),
        _scene_reflection_sunrise(),
        _scene_phone_down(),
        _krishna_scene(
            krishna,
            zoom=1.26,
            x_bias=0.0,
            y_bias=-0.20,
            tint=(164, 98, 18),
            tint_alpha=45,
            glow_center=(540, 520),
        ),
    ]

    cfg = MOODS[mood]
    paths: list[Path] = []
    for index, scene in enumerate(scenes, start=1):
        graded = ImageEnhance.Color(scene).enhance(max(0.75, min(1.20, cfg["saturation"])))
        graded = ImageEnhance.Brightness(graded).enhance(max(0.90, min(1.08, 1.0 + cfg["brightness"])))
        path = output_root / f"story-scene-{index}.jpg"
        graded.save(path, "JPEG", quality=91, subsampling=0, optimize=True)
        paths.append(path)

    if len(paths) != 5:
        raise RuntimeError("story_scene_count")
    if len({hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}) != 5:
        raise RuntimeError("story_scene_assets_not_unique")
    return paths


def _story_image_prompts(topic: str, mood: str) -> list[str]:
    topic_clean = clean(topic, 120)
    mood_clean = clean(mood, 32)
    style = (
        "premium vertical 9:16 cinematic Indian devotional fine-art realism for a high-end Instagram Reel, "
        "photorealistic yet reverent, lifelike face and anatomy, natural hands, crisp eyes, finely resolved fabric and jewelry, "
        "cinematic depth, controlled highlights, rich shadow detail, clean subject separation, subtle blue and warm gold harmony, "
        "emotionally authentic, tasteful temple photography aesthetic, no text, no subtitles, no watermark, no collage, "
        "no split screen, no poster border, no extra fingers, no distorted hands, no malformed eyes, no low-resolution look"
    )
    person = (
        "the same anonymous adult Indian man in his mid-20s, short dark hair, simple neutral clothing, "
        "shown respectfully and naturally; preserve his facial identity, hairstyle and clothing across human scenes"
    )
    krishna = KRISHNA_VISUAL_GUIDE
    return [
        f"{style}. Scene 1, premium emotional hook frame: {person}, seated quietly on the edge of a bed at night, "
        f"reflecting on {topic_clean}; soft phone glow nearby but not in his hand, moonlight through a window, "
        f"a small traditional Krishna murti with flute and peacock feather beside a warm diya, intimate cinematic framing, "
        f"{mood_clean} emotional tone, uncluttered composition with clear negative space for subtitles.",
        f"{style}. Scene 2, hero devotional portrait: {krishna}. Krishna stands near a moonlit Yamuna-inspired riverside temple, "
        f"holding the bansuri naturally across the body, gentle compassionate gaze toward the viewer, calm blue-gold atmosphere, "
        f"soft temple lamps and distant flowers, spiritual reassurance connected to {topic_clean}, face and hands are the visual priority.",
        f"{style}. Scene 3: {person}, same face, hairstyle and clothing as Scene 1, sitting peacefully on river ghat steps at sunrise, "
        f"phone put away, quietly reflecting on {topic_clean}; soft mist, distant temple silhouettes, restrained hopeful warmth, "
        "natural posture and clean lower-third negative space.",
        f"{style}. Scene 4, close narrative action: natural adult hands placing a smartphone face-down beside a wooden tulsi mala "
        f"and glowing diya, a small traditional Krishna murti softly visible in the background, a simple naam-smaran pause after {topic_clean}; "
        "accurate fingers, realistic objects, warm devotional light, elegant uncluttered composition.",
        f"{style}. Scene 5, devotional resolution: {krishna}. Golden dawn beside a calm river; Krishna holds the flute relaxed in one hand "
        f"while the other hand is raised naturally in a gentle blessing gesture, soft flower petals and distant temple architecture, "
        f"peaceful direct gaze, spacious composition, clear emotional resolution after {topic_clean}, exquisite face, hands and ornaments.",
    ]


def _save_story_frame(raw: bytes, output_root: Path, index: int) -> Path:
    with Image.open(BytesIO(raw)) as image:
        frame = _cover(image.convert("RGB"))
        frame = ImageEnhance.Sharpness(frame).enhance(1.08)
        frame = ImageEnhance.Contrast(frame).enhance(1.02)
        path = output_root / f"story-scene-{index}.jpg"
        frame.save(path, "JPEG", quality=96, subsampling=0, optimize=True)
        return path


def _cloudflare_reference_bytes(reference: Path) -> bytes:
    with Image.open(reference) as image:
        ref = image.convert("RGB")
        ref.thumbnail((504, 504), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        ref.save(buffer, "JPEG", quality=90, optimize=True)
        return buffer.getvalue()


def _cloudflare_error_code(response) -> int | None:
    try:
        payload = response.json()
    except Exception:
        return None
    errors = payload.get("errors") or []
    if not errors:
        return None
    try:
        return int(errors[0].get("code"))
    except Exception:
        return None


def _cloudflare_image_request_once(
    account_id: str,
    api_token: str,
    model: str,
    prompt: str,
    seed: int,
    reference: Path | None = None,
) -> bytes:
    if not account_id or not api_token:
        raise RuntimeError("cloudflare_credentials_missing")

    fields: dict[str, tuple] = {
        "prompt": (None, prompt),
        "width": (None, str(WIDTH)),
        "height": (None, str(HEIGHT)),
        "seed": (None, str(seed)),
        "guidance": (None, "4.0"),
    }
    if reference is not None:
        fields["input_image_0"] = (
            reference.name,
            _cloudflare_reference_bytes(reference),
            "image/jpeg",
        )

    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_token}"},
        files=fields,
        timeout=75,
    )
    if not response.ok:
        code = _cloudflare_error_code(response)
        raise RuntimeError(
            f"cloudflare_{model.rsplit('/', 1)[-1]}_{response.status_code}_code_{code}:"
            f"{response.text[:260]}"
        )
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(
            "cloudflare_unsuccessful:" + json.dumps(payload.get("errors") or payload, ensure_ascii=False)[:260]
        )
    encoded = (payload.get("result") or {}).get("image")
    if not encoded:
        raise RuntimeError("cloudflare_image_missing_payload")
    return base64.b64decode(encoded)


def _is_cloudflare_capacity_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "code_3040" in message or "capacity temporarily exceeded" in message


def _cloudflare_image_request(
    account_id: str,
    api_token: str,
    model: str,
    prompt: str,
    seed: int,
    reference: Path | None = None,
) -> bytes:
    delays = (0, 8, 20)
    last_exc: Exception | None = None

    for attempt, delay in enumerate(delays, start=1):
        if delay:
            print(
                f"Cloudflare capacity retry {attempt}/{len(delays)} for {model.rsplit('/', 1)[-1]} "
                f"after {delay}s.",
                file=sys.stderr,
            )
            time.sleep(delay)
        try:
            return _cloudflare_image_request_once(
                account_id, api_token, model, prompt, seed + attempt - 1, reference
            )
        except requests.Timeout as exc:
            last_exc = exc
            if attempt == len(delays):
                raise RuntimeError(
                    f"cloudflare_{model.rsplit('/', 1)[-1]}_timeout_after_{len(delays)}_attempts"
                ) from exc
            print(
                f"Cloudflare request timed out on attempt {attempt}; retrying.",
                file=sys.stderr,
            )
        except Exception as exc:
            last_exc = exc
            if not _is_cloudflare_capacity_error(exc) or attempt == len(delays):
                raise
            print(
                f"Cloudflare reported temporary capacity exhaustion on attempt {attempt}; retrying.",
                file=sys.stderr,
            )

    raise RuntimeError("cloudflare_retry_exhausted") from last_exc


def _cloudflare_schnell_request(
    account_id: str,
    api_token: str,
    prompt: str,
    seed: int,
) -> bytes:
    model = os.getenv(
        "CLOUDFLARE_IMAGE_MODEL_EMERGENCY",
        "@cf/black-forest-labs/flux-1-schnell",
    ).strip() or "@cf/black-forest-labs/flux-1-schnell"
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": prompt,
            "width": WIDTH,
            "height": HEIGHT,
            "num_steps": 4,
            "seed": seed,
        },
        timeout=75,
    )
    if not response.ok:
        code = _cloudflare_error_code(response)
        raise RuntimeError(
            f"cloudflare_emergency_{response.status_code}_code_{code}:{response.text[:260]}"
        )
    payload = response.json()
    encoded = (payload.get("result") or {}).get("image")
    if not encoded:
        raise RuntimeError("cloudflare_emergency_image_missing_payload")
    return base64.b64decode(encoded)


def _is_cloudflare_content_flag(exc: Exception) -> bool:
    message = str(exc).lower()
    return "code_3030" in message or "code\":3030" in message or "flagged" in message


def _safe_story_prompt(index: int, mood: str) -> str:
    mood_clean = clean(mood, 32) or "peaceful"
    common = (
        "premium vertical 9:16 cinematic Indian devotional fine-art realism, "
        "tasteful and family-friendly, natural anatomy and hands, crisp facial detail, "
        "soft cinematic lighting, elegant blue and warm gold palette, no text, no watermark, "
        "no collage, no split screen, one full-frame scene"
    )
    scenes = {
        1: (
            "an adult Indian man in simple neutral clothing seated quietly beside a window at night, "
            "calm reflective expression, phone resting nearby, small diya and tasteful Krishna idol on a side table"
        ),
        2: (
            "respectful traditional depiction of Lord Krishna with a serene youthful face, traditional blue complexion, "
            "large compassionate eyes, subtle Vaishnava tilak, peacock feather, yellow pitambar, Vaijayanti garland and wooden flute, "
            "exactly two arms, natural hands, beside a moonlit riverside temple, gentle peaceful atmosphere"
        ),
        3: (
            "an adult Indian man in simple neutral clothing sitting peacefully on river ghat steps at sunrise, "
            "phone put away, relaxed reflective posture, soft mist and distant temple silhouettes"
        ),
        4: (
            "close-up of natural adult hands placing a smartphone face-down beside a wooden mala and glowing diya, "
            "clean uncluttered devotional setting, warm realistic light"
        ),
        5: (
            "respectful traditional depiction of Lord Krishna at golden dawn beside a calm river, traditional blue complexion, "
            "serene youthful face, peacock feather, yellow pitambar and Vaijayanti garland, flute relaxed in one hand, "
            "other hand raised naturally in blessing, exactly two arms, spacious peaceful composition"
        ),
    }
    scene = scenes.get(index, scenes[5])
    return f"{common}. Scene {index}: {scene}. Emotional tone: {mood_clean}."


def _cloudflare_scene_request_with_retry(
    account_id: str,
    api_token: str,
    model: str,
    prompt: str,
    seed: int,
    scene_index: int,
    mood: str,
    reference: Path | None = None,
) -> tuple[bytes, str]:
    try:
        return (
            _cloudflare_image_request(
                account_id, api_token, model, prompt, seed, reference
            ),
            model,
        )
    except Exception as exc:
        if _is_cloudflare_capacity_error(exc) or "timeout_after_" in str(exc):
            print(
                f"Cloudflare {model.rsplit('/', 1)[-1]} remained unavailable for scene {scene_index}; "
                "using FLUX.1 Schnell emergency generation.",
                file=sys.stderr,
            )
            return (
                _cloudflare_schnell_request(
                    account_id,
                    api_token,
                    _safe_story_prompt(scene_index, mood),
                    seed + 5000,
                ),
                "@cf/black-forest-labs/flux-1-schnell",
            )
        if not _is_cloudflare_content_flag(exc):
            raise

        print(
            f"Cloudflare content filter flagged scene {scene_index}; retrying without reference.",
            file=sys.stderr,
        )

        try:
            return (
                _cloudflare_image_request(
                    account_id,
                    api_token,
                    model,
                    prompt,
                    seed + 1000,
                    None,
                ),
                model,
            )
        except Exception as retry_exc:
            if _is_cloudflare_capacity_error(retry_exc) or "timeout_after_" in str(retry_exc):
                print(
                    f"Cloudflare capacity unavailable during scene {scene_index} safety retry; "
                    "using FLUX.1 Schnell emergency generation.",
                    file=sys.stderr,
                )
                return (
                    _cloudflare_schnell_request(
                        account_id,
                        api_token,
                        _safe_story_prompt(scene_index, mood),
                        seed + 6000,
                    ),
                    "@cf/black-forest-labs/flux-1-schnell",
                )
            if not _is_cloudflare_content_flag(retry_exc):
                raise

        print(
            f"Cloudflare scene {scene_index} was still flagged; retrying with neutral scene prompt.",
            file=sys.stderr,
        )
        try:
            return (
                _cloudflare_image_request(
                    account_id,
                    api_token,
                    model,
                    _safe_story_prompt(scene_index, mood),
                    seed + 2000,
                    None,
                ),
                model,
            )
        except Exception as safe_exc:
            if _is_cloudflare_capacity_error(safe_exc) or "timeout_after_" in str(safe_exc):
                return (
                    _cloudflare_schnell_request(
                        account_id,
                        api_token,
                        _safe_story_prompt(scene_index, mood),
                        seed + 7000,
                    ),
                    "@cf/black-forest-labs/flux-1-schnell",
                )
            raise



def generate_cloudflare_story_scenes(
    output_root: Path,
    topic: str,
    mood: str,
    account_id: str,
    api_token: str,
) -> tuple[list[Path], str]:
    """Generate five native 1080x1920 frames using one premium 9B hook plus four 4B story frames."""
    if not account_id or not api_token:
        raise RuntimeError("cloudflare_credentials_missing")

    premium_model = os.getenv(
        "CLOUDFLARE_IMAGE_MODEL_PREMIUM",
        "@cf/black-forest-labs/flux-2-klein-9b",
    ).strip() or "@cf/black-forest-labs/flux-2-klein-9b"
    fast_model = os.getenv(
        "CLOUDFLARE_IMAGE_MODEL_FAST",
        "@cf/black-forest-labs/flux-2-klein-4b",
    ).strip() or "@cf/black-forest-labs/flux-2-klein-4b"

    prompts = _story_image_prompts(topic, mood)
    if len(prompts) != 5:
        raise RuntimeError("cloudflare_story_prompt_count")

    seed_base = int(hashlib.sha256(f"{mood}:{topic}".encode("utf-8")).hexdigest()[:8], 16)
    paths: list[Path] = []
    premium_used = True
    emergency_used = False

    for index, prompt in enumerate(prompts, start=1):
        model = premium_model if index == 1 else fast_model
        reference = None
        if index == 3 and len(paths) >= 1:
            reference = paths[0]
        elif index == 5 and len(paths) >= 2:
            reference = paths[1]

        try:
            raw, actual_model = _cloudflare_scene_request_with_retry(
                account_id,
                api_token,
                model,
                prompt,
                seed_base + index,
                index,
                mood,
                reference,
            )
            emergency_used = emergency_used or actual_model.endswith("flux-1-schnell")
        except Exception as exc:
            if index != 1 or model == fast_model:
                raise
            premium_used = False
            print(
                f"Cloudflare premium hook fallback to 4B: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            raw, actual_model = _cloudflare_scene_request_with_retry(
                account_id,
                api_token,
                fast_model,
                prompt,
                seed_base + index,
                index,
                mood,
                reference,
            )
            emergency_used = emergency_used or actual_model.endswith("flux-1-schnell")

        paths.append(_save_story_frame(raw, output_root, index))

    if len(paths) != 5:
        raise RuntimeError("cloudflare_story_scene_count")
    if len({hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}) != 5:
        raise RuntimeError("cloudflare_story_scenes_not_unique")

    if emergency_used:
        mode = "cloudflare_hybrid_with_schnell"
    else:
        mode = "cloudflare_hybrid_9b_4b" if premium_used else "cloudflare_4b"
    return paths, mode


def build_story_scenes(
    output_root: Path,
    topic: str,
    mood: str,
    cloudflare_account_id: str,
    cloudflare_api_token: str,
) -> tuple[list[Path], str]:
    if os.getenv("ORIGINAL_REEL_DRY_RUN") == "1":
        return generate_fallback_story_scenes(output_root, mood), "local_fallback"

    try:
        return generate_cloudflare_story_scenes(
            output_root,
            topic,
            mood,
            cloudflare_account_id,
            cloudflare_api_token,
        )
    except Exception as exc:
        raise RuntimeError(
            "high_quality_image_generation_failed; refusing local low-quality fallback; "
            f"Cloudflare Workers AI failed: {type(exc).__name__}: {exc}"
        ) from exc


def fallback_script(topic: str, mood: str) -> dict:
    topic_clean = clean(topic, 90)
    hooks = {
        "peaceful": f"{topic_clean} के बीच मन को शांत कैसे रखें?",
        "devotional": f"{topic_clean} में भगवान को कैसे याद रखें?",
        "healing": f"{topic_clean} के समय खुद को कैसे संभालें?",
        "motivational": f"{topic_clean} से आगे बढ़ने की शुरुआत कहाँ से करें?",
        "reflective": f"{topic_clean} हमें भीतर से क्या सिखाता है?",
        "joyful": f"{topic_clean} में कृतज्ञता कैसे महसूस करें?",
    }
    return {
        "hook": hooks[mood],
        "line1": "ज़्यादा सोचने से हर बार समाधान नहीं मिलता।",
        "line2": "कई बार मन बस वही चिंता दोहराता रहता है।",
        "line3": "मन को रोकना नहीं, दिशा देना सीखें।",
        "takeaway": "पाँच मिनट फोन दूर रखें और नाम स्मरण करें।",
        "closing": "हर विचार का जवाब देना ज़रूरी नहीं।",
        "caption": f"{topic_clean} पर आज की छोटी-सी devotional reflection. पाँच मिनट शांति, स्मरण और एक छोटा सही कदम। 🙏",
        "hashtags": ["#RadheRadhe", "#Bhakti", "#मनकीशांति"],
    }


def generate_script(topic: str, mood: str, api_key: str) -> dict:
    fallback = fallback_script(topic, mood)
    if not api_key or os.getenv("ORIGINAL_REEL_DRY_RUN") == "1":
        return fallback

    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["hook", "line1", "line2", "line3", "takeaway", "closing", "caption", "hashtags"],
        "properties": {
            "hook": {"type": "string"},
            "line1": {"type": "string"},
            "line2": {"type": "string"},
            "line3": {"type": "string"},
            "takeaway": {"type": "string"},
            "closing": {"type": "string"},
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
        },
    }
    mood_desc = {
        "peaceful": "calm, reassuring, spacious",
        "devotional": "reverent, warm, Krishna-bhakti oriented",
        "healing": "gentle, compassionate, grounded without medical claims",
        "motivational": "uplifting, practical, energetic without hype",
        "reflective": "thoughtful, introspective, contemplative",
        "joyful": "grateful, bright, celebratory but not noisy",
    }[mood]
    prompt = f"""Create an ORIGINAL faceless Hindi devotional Reel about the user's topic.
Topic: {topic}
Mood: {mood_desc}

This is NOT a quote from Premanand Ji or any other teacher. Do not attribute statements to a real person.
Use natural Hindi in Devanagari. Keep it respectful and useful.

The Reel uses FIVE different full-screen story images in this exact visual arc:
1) a restless person awake at night with a subtle Krishna devotional element,
2) Krishna appearing as a calm devotional presence,
3) the same person reflecting alone at sunrise,
4) the person putting the phone aside for a simple devotional practice,
5) a peaceful Krishna blessing/resolution.

Write six text beats as one continuous micro-story. These are ON-SCREEN SUBTITLES with no voice narration.
Each beat must be instantly readable on a phone, use simple natural Hindi, avoid long clauses, and fit comfortably in no more than TWO subtitle lines.
Do not use English words when a natural Hindi alternative exists. The line3 and takeaway beats share image 4, so keep them especially concise and complementary.

Return exactly these fields:
hook: 4-8 Hindi words, specific emotional question/problem, immediate and natural, no vague clickbait.
line1: 6-11 Hindi words; recognition of the viewer's thought pattern, continuing the hook.
line2: 6-11 Hindi words; the realization/turn in the story, not a repetition.
line3: 5-10 Hindi words; grounded spiritual redirection that resolves the tension.
takeaway: 6-11 Hindi words; one concrete phone-down / pause / naam-smaran action.
closing: 4-8 Hindi words; calm memorable resolution, emotionally resonant, no engagement bait.
caption: <=170 characters.
hashtags: exactly 3; include #RadheRadhe or #Bhakti; no #viral/#trending.

No medical diagnosis, guaranteed healing, supernatural promises, invented scripture quotations, or engagement bait."""
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("GROQ_REEL_MODEL", "openai/gpt-oss-20b"),
                "reasoning_effort": "low",
                "max_completion_tokens": 1800,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "original_reel", "strict": True, "schema": schema},
                },
                "messages": [
                    {"role": "system", "content": "Write concise, original Hindi devotional editorial content. Return only the requested schema."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=75,
        )
        if not response.ok:
            raise RuntimeError(f"groq_{response.status_code}")
        payload = response.json()
        if payload.get("choices", [{}])[0].get("finish_reason") == "length":
            raise RuntimeError("groq_truncated")
        data = json.loads(payload["choices"][0]["message"]["content"])
        tags = [("#" + str(x).strip().lstrip("#")) for x in data.get("hashtags", []) if str(x).strip()]
        tags = [x for x in tags if re.fullmatch(r"#[\w\u0900-\u097F]+", x)][:3]
        if len(tags) != 3:
            tags = fallback["hashtags"]
        return {
            "hook": clean(data.get("hook"), 100) or fallback["hook"],
            "line1": clean(data.get("line1"), 170) or fallback["line1"],
            "line2": clean(data.get("line2"), 170) or fallback["line2"],
            "line3": clean(data.get("line3"), 170) or fallback["line3"],
            "takeaway": clean(data.get("takeaway"), 170) or fallback["takeaway"],
            "closing": clean(data.get("closing"), 120) or fallback["closing"],
            "caption": clean(data.get("caption"), 170) or fallback["caption"],
            "hashtags": tags,
        }
    except Exception as exc:
        print(f"original reel editorial fallback: {type(exc).__name__}: {exc}", file=sys.stderr)
        return fallback


def find_font() -> str:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def write_ass(data: dict, path: Path) -> None:
    def event(start: float, end: float, style: str, text: str) -> str:
        def ts(seconds: float) -> str:
            whole = int(seconds)
            centis = int(round((seconds - whole) * 100))
            if centis == 100:
                whole += 1
                centis = 0
            minutes, secs = divmod(whole, 60)
            return f"0:{minutes:02d}:{secs:02d}.{centis:02d}"
        return f"Dialogue: 0,{ts(start)},{ts(end)},{style},,0,0,0,,{format_ass_subtitle(text)}"

    content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,Noto Sans Devanagari,76,&H0037D7FF,&H000000FF,&H00101018,&H70000000,-1,0,0,0,100,100,0.4,0,1,5,2,2,104,104,300,1
Style: Body,Noto Sans Devanagari,62,&H00FFFDF7,&H000000FF,&H00101018,&H70000000,-1,0,0,0,100,100,0.2,0,1,5,2,2,108,108,300,1
Style: Take,Noto Sans Devanagari,64,&H0037D7FF,&H000000FF,&H00101018,&H70000000,-1,0,0,0,100,100,0.2,0,1,5,2,2,108,108,300,1
Style: Close,Noto Sans Devanagari,68,&H00FFFFFF,&H000000FF,&H00101018,&H70000000,-1,0,0,0,100,100,0.3,0,1,5,2,2,108,108,300,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    t0 = 0.0
    t1 = t0 + SCENE_DURATIONS[0]
    t2 = t1 + SCENE_DURATIONS[1]
    t3 = t2 + SCENE_DURATIONS[2]
    t4 = t3 + SCENE_DURATIONS[3]
    t5 = t4 + SCENE_DURATIONS[4]
    action_split = t3 + 2.4
    rows = [
        event(t0, t1, "Hook", data["hook"]),
        event(t1, t2, "Body", data["line1"]),
        event(t2, t3, "Body", data["line2"]),
        event(t3, action_split, "Body", data["line3"]),
        event(action_split, t4, "Take", data["takeaway"]),
        event(t4, t5, "Close", data.get("closing") or "हर विचार का जवाब देना जरूरी नहीं।"),
    ]
    path.write_text(content + "\n".join(rows) + "\n", encoding="utf-8")
def synth_music(path: Path, mood: str) -> None:
    sr = 32000
    frames = int(DURATION * sr)
    tempo = MOODS[mood]["tempo"]
    # D-major / pentatonic palette; this is generated from scratch.
    scale = [293.66, 329.63, 369.99, 440.00, 493.88, 587.33]
    if mood == "reflective":
        scale = [293.66, 349.23, 392.00, 440.00, 523.25]
    if mood == "joyful":
        scale = [329.63, 369.99, 440.00, 493.88, 587.33, 659.25]
    rng = random.Random(f"{mood}:krishna-flute:v1")
    note_len = max(0.7, 1.15 / tempo)
    melody = [rng.choice(scale) for _ in range(int(DURATION / note_len) + 2)]
    pcm = array("h")
    for i in range(frames):
        tt = i / sr
        # tanpura-like drone
        sample = (
            0.032 * math.sin(2 * math.pi * 146.83 * tt)
            + 0.020 * math.sin(2 * math.pi * 220.00 * tt)
            + 0.011 * math.sin(2 * math.pi * 293.66 * tt)
        )
        idx = min(len(melody) - 1, int(tt / note_len))
        local = tt - idx * note_len
        env = min(1.0, local / 0.10, max(0.0, (note_len - local) / 0.20))
        vibrato = 1.0 + 0.0028 * math.sin(2 * math.pi * 5.1 * local)
        freq = melody[idx] * vibrato
        sample += env * (
            0.165 * math.sin(2 * math.pi * freq * local)
            + 0.034 * math.sin(2 * math.pi * 2 * freq * local)
        )
        fade = min(1.0, tt / 0.7, max(0.0, (DURATION - tt) / 1.3))
        sample *= fade
        pcm.append(max(-32767, min(32767, int(sample * 32767))))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def render(scenes: list[Path], ass: Path, music: Path, mood: str, output: Path) -> None:
    """Render five stable full-screen story frames with flute music only and no narration."""
    if len(scenes) != len(SCENE_DURATIONS):
        raise RuntimeError("story_scene_duration_mismatch")

    cfg = MOODS[mood]
    ass_path = str(ass).replace("'", r"\'")
    image_inputs: list[str] = []
    video_filters: list[str] = []

    for index, (scene, duration) in enumerate(zip(scenes, SCENE_DURATIONS)):
        image_inputs.extend(["-i", str(scene)])
        video_filters.append(
            f"[{index}:v]"
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={WIDTH}:{HEIGHT},setsar=1,"
            f"tpad=stop_mode=clone:stop_duration={duration},"
            f"fps=30,trim=duration={duration},setpts=PTS-STARTPTS[v{index}]"
        )

    concat_inputs = "".join(f"[v{index}]" for index in range(len(scenes)))
    video_filters.append(f"{concat_inputs}concat=n={len(scenes)}:v=1:a=0[story]")
    video_filters.append(
        "[story]"
        f"eq=brightness={cfg['brightness']}:saturation={cfg['saturation']},"
        "unsharp=5:5:0.35:5:5:0.0,"
        f"subtitles='{ass_path}':fontsdir='/usr/share/fonts',"
        "format=yuv420p[v]"
    )

    music_index = len(scenes)
    filter_complex = ";".join(video_filters)
    run(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *image_inputs,
        "-i", str(music),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", f"{music_index}:a:0",
        "-t", str(DURATION),
        "-c:v", "libx264", "-preset", "slow", "-crf", "17",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-af", "volume=1.0,alimiter=limit=0.95",
        "-movflags", "+faststart", str(output),
    )

def fit_telegram(path: Path, directory: Path) -> Path:
    if path.stat().st_size <= MAX_TELEGRAM_BYTES:
        return path
    smaller = directory / "original-reel-telegram.mp4"
    run(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
        "-vf", "scale=720:1280:flags=lanczos", "-c:v", "libx264", "-preset", "medium", "-crf", "24",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(smaller),
    )
    if smaller.stat().st_size > MAX_TELEGRAM_BYTES:
        raise RuntimeError("telegram_file_too_large")
    return smaller


def send_text(token: str, chat_id: int, text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}},
        timeout=30,
    ).raise_for_status()


def send_video(token: str, chat_id: int, video: Path, caption: str) -> None:
    with video.open("rb") as handle:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendVideo",
            data={"chat_id": str(chat_id), "caption": caption[:1000], "supports_streaming": "true"},
            files={"video": (video.name, handle, "video/mp4")},
            timeout=180,
        )
    response.raise_for_status()


def main() -> int:
    mood = clean(os.getenv("ORIGINAL_REEL_MOOD"), 24).lower()
    topic = clean(os.getenv("ORIGINAL_REEL_TOPIC"), 140)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_raw = os.getenv("ORIGINAL_REEL_CHAT_ID", "").strip()
    skip_telegram = os.getenv("ORIGINAL_REEL_SKIP_TELEGRAM") == "1"
    if mood not in MOODS:
        raise RuntimeError("invalid_mood")
    if len(topic) < 2:
        raise RuntimeError("invalid_topic")
    if not skip_telegram and (not token or not chat_raw.lstrip("-").isdigit()):
        raise RuntimeError("telegram_configuration_incomplete")
    chat_id = int(chat_raw) if chat_raw.lstrip("-").isdigit() else 0

    output_root = Path(os.getenv("ORIGINAL_REEL_OUTPUT_DIR") or tempfile.mkdtemp(prefix="original-reel-"))
    output_root.mkdir(parents=True, exist_ok=True)
    if not skip_telegram:
        send_text(token, chat_id, f"🎬 Creating your {MOODS[mood]['label'].lower()} Reel about: {topic}\n\nWriting the original Hindi script and five-scene visual story…")

    data = generate_script(topic, mood, os.getenv("GROQ_API_KEY", "").strip())
    scenes, image_mode = build_story_scenes(
        output_root,
        topic,
        mood,
        os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
        os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
    )
    ass = output_root / "reel.ass"
    music = output_root / "music.wav"
    output = output_root / "original-devotional-reel.mp4"
    write_ass(data, ass)
    synth_music(music, mood)
    render(scenes, ass, music, mood, output)
    final = fit_telegram(output, output_root)

    if not skip_telegram:
        hashtags = " ".join(data["hashtags"])
        send_video(token, chat_id, final, f"✅ Original {MOODS[mood]['label']} Story Reel\n\n{data['caption']}\n\n{hashtags}")
        send_text(token, chat_id, "🎵 The Reel uses only original Krishna-flute-inspired devotional music. Voice narration is disabled.")
    print(json.dumps({
        "ok": True,
        "mood": mood,
        "topic": topic,
        "video": str(final),
        "bytes": final.stat().st_size,
        "tts": False,
        "voice": False,
        "story_scenes": len(scenes),
        "image_mode": image_mode,
        "hook": data["hook"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"original reel worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_raw = os.getenv("ORIGINAL_REEL_CHAT_ID", "").strip()
        if token and chat_raw.lstrip("-").isdigit() and os.getenv("ORIGINAL_REEL_SKIP_TELEGRAM") != "1":
            try:
                send_text(token, int(chat_raw), "❌ Original Reel generation failed. Check the GitHub Actions log for the failed stage.")
            except Exception:
                pass
        raise
