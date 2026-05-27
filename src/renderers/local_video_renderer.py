"""
Local Video Renderer — ffmpeg, styled captions, background music, outro card.
No segfaults. No ImageMagick. No PIL.
"""

import logging, math, textwrap, uuid, subprocess, shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import requests

logger = logging.getLogger(__name__)
OUTPUT_DIR = Path("tmp/videos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR = Path("music")
TARGET_W, TARGET_H, FPS = 1080, 1920, 30
CAPTION_FONT_SIZE = 58
HOOK_FONT_SIZE = 68
CAPTION_Y_POSITION = 0.72
HOOK_Y_POSITION = 0.10
WORDS_PER_CAPTION = 5
BG_MUSIC_VOLUME = 0.08
OUTRO_DURATION = 3.0

# Topic → music mood map
TOPIC_MUSIC_MAP = {
    "workout": "hype", "gym": "hype", "training": "hype",
    "cardio": "hype", "running": "hype", "exercise": "hype",
    "sleep": "calm", "stress": "calm", "yoga": "calm",
    "walking": "calm", "gut": "calm", "diet": "calm",
    "protein": "motivational", "myth": "motivational",
    "fat": "motivational", "weight": "motivational",
}

@dataclass
class RenderResult:
    render_id: str
    video_url: str
    width: int
    height: int
    duration: float

def _get_ffmpeg():
    ff = shutil.which("ffmpeg")
    if ff: return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("ffmpeg not found.")

class LocalVideoRenderer:
    def __init__(self, settings):
        self.settings = settings
        self._ffmpeg = _get_ffmpeg()
        logger.info("Using ffmpeg: %s", self._ffmpeg)

    async def render(self, template_id, hook_text, body_text, video_url, audio_url,
                     bg_music_path=None, topic=""):
        rid = uuid.uuid4().hex[:10]
        logger.info("LocalRenderer [%s] starting render", rid)

        footage = self._download_file(video_url, ".mp4", "footage")
        audio = self._resolve_audio(audio_url, rid)
        dur = self._get_duration(audio)
        logger.info("[%s] Audio duration: %.1fs", rid, dur)

        cropped = OUTPUT_DIR / f"crop_{rid}.mp4"
        self._crop(footage, cropped)
        logger.info("[%s] Cropped to vertical", rid)

        total_dur = dur + OUTRO_DURATION
        looped = OUTPUT_DIR / f"loop_{rid}.mp4"
        self._loop(cropped, looped, total_dur)
        logger.info("[%s] Looped footage %.1fs", rid, total_dur)

        # Find background music
        music_path = bg_music_path or self._find_music(topic)

        out = OUTPUT_DIR / f"video_{rid}.mp4"
        self._burn_all(looped, audio, hook_text, body_text, dur, total_dur, music_path, out)
        logger.info("[%s] Render complete: %s", rid, out)

        self._cleanup([footage, cropped, looped])
        return RenderResult(rid, str(out), TARGET_W, TARGET_H, total_dur)

    # ── ffmpeg core ops ────────────────────────────────────────────────

    def _crop(self, src, dst):
        vf = (f"crop='if(gt(iw/ih,9/16),ih*9/16,iw)':'if(gt(iw/ih,9/16),ih,iw*16/9)',"
              f"scale={TARGET_W}:{TARGET_H}:flags=lanczos")
        self._ff(["-y","-i",str(src),"-vf",vf,"-an","-c:v","libx264","-preset","fast","-crf","23",str(dst)])

    def _loop(self, src, dst, dur):
        cd = self._get_duration(src)
        loops = max(1, math.ceil(dur / cd))
        self._ff(["-y","-stream_loop",str(loops),"-i",str(src),"-t",str(dur),"-c","copy",str(dst)])

    def _burn_all(self, video, audio, hook_text, body_text, voice_dur, total_dur, music_path, out):
        """
        Single ffmpeg pass:
        - Styled captions with background box
        - Outro card (last 3 seconds)
        - Background music mixed with voiceover
        """
        font = self._find_font()
        filters = []

        # ── Captions ───────────────────────────────────────────────────
        hook_dur = min(4.0, voice_dur * 0.15)
        hook_clean = self._clean(hook_text)
        hook_lines = textwrap.wrap(hook_text, width=22) or [hook_text]
        hook_line_h = HOOK_FONT_SIZE + 10
        hook_box_h = len(hook_lines) * hook_line_h + 30
        hook_box_y = int(TARGET_H * HOOK_Y_POSITION)
        hook_text_y = hook_box_y + 15

        filters.append(
            f"drawbox=x=40:y={hook_box_y}:w={TARGET_W-80}:h={hook_box_h}"
            f":color=black@0.6:t=fill:enable='between(t,0,{hook_dur:.2f})'"
        )
        for i, line in enumerate(hook_lines):
            y = hook_text_y + i * hook_line_h
            filters.append(
                f"drawtext=fontfile='{font}':text='{self._clean(line)}'"
                f":fontsize={HOOK_FONT_SIZE}:fontcolor=#FFE234"
                f":borderw=2:bordercolor=black@0.8"
                f":x=(w-text_w)/2:y={y}"
                f":enable='between(t,0,{hook_dur:.2f})'"
            )

        words = body_text.split()
        if words:
            chunks = [" ".join(words[i:i+WORDS_PER_CAPTION])
                      for i in range(0, len(words), WORDS_PER_CAPTION)]
            chunk_dur = (voice_dur - hook_dur) / len(chunks)
            cap_y = int(TARGET_H * CAPTION_Y_POSITION)
            cap_line_h = CAPTION_FONT_SIZE + 12

            for i, chunk in enumerate(chunks):
                ts = hook_dur + i * chunk_dur
                te = ts + chunk_dur
                enable = f"between(t,{ts:.3f},{te:.3f})"
                lines = textwrap.wrap(chunk, width=24) or [chunk]
                box_h = len(lines) * cap_line_h + 40
                box_y = cap_y - 20

                filters.append(
                    f"drawbox=x=30:y={box_y}:w={TARGET_W-60}:h={box_h}"
                    f":color=black@0.6:t=fill:enable='{enable}'"
                )
                for j, line in enumerate(lines):
                    y = cap_y + j * cap_line_h
                    filters.append(
                        f"drawtext=fontfile='{font}':text='{self._clean(line)}'"
                        f":fontsize={CAPTION_FONT_SIZE}:fontcolor=white"
                        f":borderw=2:bordercolor=black@0.9"
                        f":x=(w-text_w)/2:y={y}"
                        f":enable='{enable}'"
                    )

        # ── Outro card (last OUTRO_DURATION seconds) ───────────────────
        outro_start = voice_dur
        outro_enable = f"between(t,{outro_start:.2f},{total_dur:.2f})"

        # Full black overlay for outro
        filters.append(
            f"drawbox=x=0:y=0:w={TARGET_W}:h={TARGET_H}"
            f":color=black@0.85:t=fill:enable='{outro_enable}'"
        )
        # Channel branding lines
        outro_texts = [
            ("DAILY FITNESS FACTS", TARGET_H // 2 - 120, "#FFE234", 62),
            ("Follow for more", TARGET_H // 2 - 30, "white", 48),
            ("Save this video", TARGET_H // 2 + 50, "white", 40),
        ]
        for text, y, color, size in outro_texts:
            filters.append(
                f"drawtext=fontfile='{font}':text='{text}'"
                f":fontsize={size}:fontcolor={color}"
                f":borderw=2:bordercolor=black"
                f":x=(w-text_w)/2:y={y}"
                f":enable='{outro_enable}'"
            )

        vf = ",".join(filters)

        # ── Build ffmpeg command with optional music ───────────────────
        if music_path and Path(music_path).exists():
            logger.info("Mixing background music: %s", music_path)
            cmd = [
                "-y",
                "-i", str(video),
                "-i", str(audio),
                "-i", str(music_path),
                "-filter_complex",
                f"[1:a]apad=whole_dur={total_dur}[voice];"
                f"[2:a]aloop=loop=-1:size=2e+09,atrim=duration={total_dur},"
                f"volume={BG_MUSIC_VOLUME}[music];"
                f"[voice][music]amix=inputs=2:duration=first[aout]",
                "-vf", vf,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(total_dur),
                str(out)
            ]
        else:
            cmd = [
                "-y",
                "-i", str(video),
                "-i", str(audio),
                "-vf", vf,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(total_dur),
                str(out)
            ]
        self._ff(cmd)

    def _find_music(self, topic: str) -> Optional[str]:
        """Find matching music file from music/ folder."""
        if not MUSIC_DIR.exists():
            return None
        topic_lower = topic.lower()
        mood = "motivational"
        for keyword, m in TOPIC_MUSIC_MAP.items():
            if keyword in topic_lower:
                mood = m
                break
        # Try mood-specific first, then any mp3
        for pattern in [f"{mood}*.mp3", "*.mp3"]:
            matches = list(MUSIC_DIR.glob(pattern))
            if matches:
                logger.info("Background music: %s (mood=%s)", matches[0].name, mood)
                return str(matches[0])
        return None

    def _find_font(self):
        for f in [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/verdana.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if Path(f).exists():
                return f.replace("\\", "/").replace("C:/", "C\\:/")
        raise RuntimeError("No font found.")

    def _clean(self, text):
        for ch in ["'", ":", "\\", "[", "]", "=", ",", "%", '"', "{", "}"]:
            text = text.replace(ch, " ")
        return text.strip()

    def _ff(self, args):
        cmd = [self._ffmpeg] + args
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-600:]}")

    def _get_duration(self, path):
        fp = shutil.which("ffprobe") or str(Path(self._ffmpeg).parent / "ffprobe")
        try:
            r = subprocess.run(
                [fp, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True)
            return float(r.stdout.strip())
        except Exception:
            from moviepy.editor import AudioFileClip
            c = AudioFileClip(str(path)); d = c.duration; c.close(); return d

    def _download_file(self, url, suffix, label):
        p = OUTPUT_DIR / f"tmp_{uuid.uuid4().hex[:8]}{suffix}"
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(p, "wb") as f:
            for chunk in r.iter_content(1024 * 256): f.write(chunk)
        return p

    def _resolve_audio(self, url, rid):
        if url.startswith("http"):
            return self._download_file(url, ".mp3", "audio")
        p = Path(url)
        if not p.exists(): raise FileNotFoundError(f"Audio not found: {url}")
        return p

    def _cleanup(self, paths):
        for p in paths:
            try:
                if p and Path(p).exists(): Path(p).unlink()
            except Exception:
                pass
