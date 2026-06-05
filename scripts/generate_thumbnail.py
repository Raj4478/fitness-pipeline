"""
Auto Thumbnail Generator — bold hook text on dark frame.
Extracts best frame from video + overlays hook text.
Output: 1080x1920 vertical thumbnail PNG.
"""

import os
import sys
import logging
import textwrap
import subprocess
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Colors
BG_DARK    = (8, 8, 8)
YELLOW     = (255, 186, 0)
ORANGE     = (255, 100, 0)
WHITE      = (255, 255, 255)
GREY       = (120, 120, 120)

THUMB_W, THUMB_H = 1080, 1920


def extract_best_frame(video_path: Path, out_path: Path) -> bool:
    """Extract frame at 2 seconds from video."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return False
    try:
        result = subprocess.run([
            ffmpeg, "-y",
            "-i", str(video_path),
            "-ss", "2",
            "-vframes", "1",
            "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=increase,"
                   f"crop={THUMB_W}:{THUMB_H}",
            str(out_path)
        ], capture_output=True, timeout=30)
        return result.returncode == 0 and out_path.exists()
    except Exception as e:
        logger.error("Frame extraction failed: %s", e)
        return False


def generate_thumbnail(video_path: str, hook: str, topic: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

    video_path = Path(video_path)
    out_path = video_path.parent / f"thumb_{video_path.stem}.png"
    frame_path = video_path.parent / f"frame_{video_path.stem}.png"

    # Try to extract a frame from video
    has_frame = extract_best_frame(video_path, frame_path)

    if has_frame:
        img = Image.open(frame_path).convert("RGB")
        img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
        # Darken frame for text readability
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(0.45)
        # Slight blur for depth
        img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
    else:
        img = Image.new("RGB", (THUMB_W, THUMB_H), BG_DARK)

    draw = ImageDraw.Draw(img)

    def load_font(size):
        for fp in [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]:
            try:
                from PIL import ImageFont
                return ImageFont.truetype(fp, size)
            except (IOError, OSError):
                continue
        from PIL import ImageFont
        return ImageFont.load_default()

    # ── Top band ──────────────────────────────────────────────────────
    draw.rectangle([0, 0, THUMB_W, 14], fill=YELLOW)

    # ── Channel label ─────────────────────────────────────────────────
    draw.rectangle([0, 40, THUMB_W, 110], fill=(0, 0, 0, 180))
    draw.text((THUMB_W // 2, 75), "FITFACTS.INDIA",
              font=load_font(36), fill=YELLOW, anchor="mm")

    # ── Main hook text — large, bold, centered ────────────────────────
    # Clean hook
    clean_hook = hook.replace('"', '').replace("'", "").strip()
    words = clean_hook.split()

    # Split into 2-3 lines max
    if len(words) <= 4:
        lines = [clean_hook]
    elif len(words) <= 8:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = textwrap.wrap(clean_hook, width=14)[:3]

    # Dark semi-transparent box behind text
    box_h = len(lines) * 130 + 60
    box_y = THUMB_H // 2 - box_h // 2 - 60
    draw.rectangle([30, box_y, THUMB_W - 30, box_y + box_h],
                   fill=(0, 0, 0))
    # Left accent strip
    draw.rectangle([30, box_y, 44, box_y + box_h], fill=YELLOW)

    # Draw each line
    y = box_y + 30
    for i, line in enumerate(lines):
        color = YELLOW if i == 0 else WHITE
        # Stroke
        for dx in [-3, 3]:
            for dy in [-3, 3]:
                draw.text((THUMB_W // 2 + dx, y + dy), line.upper(),
                          font=load_font(110), fill=(0, 0, 0), anchor="mm")
        draw.text((THUMB_W // 2, y), line.upper(),
                  font=load_font(110), fill=color, anchor="mm")
        y += 120

    # ── Fact badge ────────────────────────────────────────────────────
    draw.rounded_rectangle([THUMB_W // 2 - 180, THUMB_H - 280,
                             THUMB_W // 2 + 180, THUMB_H - 200],
                           radius=40, fill=ORANGE)
    draw.text((THUMB_W // 2, THUMB_H - 240), "🔥 SCIENCE FACT",
              font=load_font(38), fill=WHITE, anchor="mm")

    # ── Topic label ───────────────────────────────────────────────────
    topic_clean = topic.replace("_", " ").title()
    draw.text((THUMB_W // 2, THUMB_H - 140), f"#{topic_clean}",
              font=load_font(32), fill=GREY, anchor="mm")

    # ── Bottom bar ────────────────────────────────────────────────────
    draw.rectangle([0, THUMB_H - 14, THUMB_W, THUMB_H], fill=YELLOW)

    img.save(str(out_path), "PNG")
    logger.info("Thumbnail saved: %s", out_path)

    # Cleanup frame
    if frame_path.exists():
        frame_path.unlink()

    return out_path


def main():
    video_path = os.environ.get("VIDEO_PATH", "")
    hook = os.environ.get("VIDEO_HOOK", "Fitness Fact!")
    topic = os.environ.get("VIDEO_TOPIC", "fitness")

    if not video_path or not Path(video_path).exists():
        logger.error("VIDEO_PATH not set or not found: %s", video_path)
        sys.exit(1)

    thumb = generate_thumbnail(video_path, hook, topic)
    print(str(thumb))


if __name__ == "__main__":
    main()
