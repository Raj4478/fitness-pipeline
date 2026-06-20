"""
Local Video Renderer — ffmpeg, styled captions, background music, outro card.
No segfaults. No ImageMagick. No PIL.
"""

import asyncio
import logging, math, re, textwrap, uuid, subprocess, shutil
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
OUTRO_DURATION = 1.3

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
                     bg_music_path=None, topic="", subject="", target_duration=None):
        return await asyncio.to_thread(
            self._render_sync,
            template_id,
            hook_text,
            body_text,
            video_url,
            audio_url,
            bg_music_path,
            topic,
            subject,
            target_duration,
        )

    def _render_sync(self, template_id, hook_text, body_text, video_url, audio_url,
                     bg_music_path=None, topic="", subject="", target_duration=None):
        rid = uuid.uuid4().hex[:10]
        logger.info("LocalRenderer [%s] starting render", rid)

        footage = self._download_file(video_url, ".mp4", "footage")
        audio = self._resolve_audio(audio_url, rid)
        dur = self._get_duration(audio)
        if target_duration and target_duration < dur:
            dur = target_duration
            logger.info("[%s] Duration capped to %.1fs (target)", rid, dur)
        else:
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

        # Use topic as filename — sanitize for filesystem
        import re as _re
        safe_topic = _re.sub(r"[^a-zA-Z0-9]+", "_", (subject or topic).strip().lower())[:40]
        safe_topic = safe_topic.strip("_") or "video"
        out = OUTPUT_DIR / f"{safe_topic}_{rid[:6]}.mp4"
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

        # ── Hook — FULL SCREEN prominent, visible from FRAME 1 ──────────
        # Critical: shows text before sound kicks in (sound-off viewers)
        hook_dur = min(5.0, voice_dur * 0.40)
        hook_lines = textwrap.wrap(hook_text, width=18) or [hook_text]
        hook_line_h = HOOK_FONT_SIZE + 16
        hook_total_h = len(hook_lines) * hook_line_h + 50
        hook_box_y = TARGET_H // 2 - hook_total_h // 2 - 80

        # Full-width dark box CENTER of screen
        filters.append(
            f"drawbox=x=0:y={hook_box_y - 20}:w={TARGET_W}:h={hook_total_h + 40}"
            f":color=black@0.78:t=fill:enable='between(t,0,{hook_dur:.2f})'"
        )
        # Yellow left accent strip
        filters.append(
            f"drawbox=x=0:y={hook_box_y - 20}:w=14:h={hook_total_h + 40}"
            f":color=#FFE234@1:t=fill:enable='between(t,0,{hook_dur:.2f})'"
        )
        hook_text_y = hook_box_y + 15
        for i, line in enumerate(hook_lines):
            y = hook_text_y + i * hook_line_h
            filters.append(
                f"drawtext=fontfile='{font}':text='{self._clean(line)}'"
                f":fontsize={HOOK_FONT_SIZE}:fontcolor=#FFE234"
                f":borderw=3:bordercolor=black"
                f":x=(w-text_w)/2:y={y}"
                f":enable='between(t,0,{hook_dur:.2f})'"
            )

        # ── Caption timing — Whisper-synced when available ──────────────
        # Uses body_text (Roman Hinglish) for the on-screen text, but times
        # each chunk against actual transcribed speech segments instead of
        # an even time-slice, so captions don't drift from the spoken audio
        # on longer or unevenly-paced narration.
        segments = self._transcribe_audio(audio)
        if segments:
            captions = self._segments_to_caption_timing(segments, hook_dur, voice_dur, body_text)
            logger.info("Caption timing: %d chunks (Whisper-synced)", len(captions))
        else:
            captions = self._build_even_captions(body_text, hook_dur, voice_dur)
            logger.info("Caption timing: %d chunks (even distribution fallback)", len(captions))

        cap_y = int(TARGET_H * CAPTION_Y_POSITION)
        cap_line_h = CAPTION_FONT_SIZE + 12

        for cap in captions:
            ts = cap["start"]
            te = cap["end"]
            chunk = cap["text"]
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

        # ── Loop trigger — last 1.5 seconds shows hook again (drives replays) ──
        loop_start = max(0, voice_dur - 1.5)
        loop_enable = f"between(t,{loop_start:.2f},{voice_dur:.2f})"
        loop_lines = textwrap.wrap(hook_text, width=22) or [hook_text]
        loop_y = TARGET_H // 2 - 60
        filters.append(
            f"drawbox=x=0:y={loop_y - 20}:w={TARGET_W}:h={len(loop_lines) * 70 + 40}"
            f":color=black@0.7:t=fill:enable='{loop_enable}'"
        )
        for i, line in enumerate(loop_lines):
            filters.append(
                f"drawtext=fontfile='{font}':text='{self._clean(line)}'"
                f":fontsize=54:fontcolor=white"
                f":borderw=3:bordercolor=black"
                f":x=(w-text_w)/2:y={loop_y + i * 68}"
                f":enable='{loop_enable}'"
            )

        # ── Loop trigger — last 1.5s shows hook again (drives replays) ────
        loop_start = max(0, voice_dur - 1.5)
        loop_lines = textwrap.wrap(hook_text, width=22) or [hook_text]
        loop_enable = f"between(t,{loop_start:.2f},{voice_dur:.2f})"
        loop_box_h = len(loop_lines) * 72 + 40
        loop_box_y = TARGET_H // 2 - loop_box_h // 2
        filters.append(
            f"drawbox=x=0:y={loop_box_y}:w={TARGET_W}:h={loop_box_h}"
            f":color=black@0.75:t=fill:enable='{loop_enable}'"
        )
        for i, line in enumerate(loop_lines):
            filters.append(
                f"drawtext=fontfile='{font}':text='{self._clean(line)}'"
                f":fontsize=54:fontcolor=white"
                f":borderw=3:bordercolor=black"
                f":x=(w-text_w)/2:y={loop_box_y + 20 + i * 70}"
                f":enable='{loop_enable}'"
            )

        # ── Outro card (last OUTRO_DURATION seconds) ───────────────────
        # Translucent overlay over STILL-PLAYING footage (not a full black
        # cut to dead air) — keeps motion on screen during the CTA so the
        # watch-through percentage isn't spent on a static frame.
        outro_start = voice_dur
        outro_enable = f"between(t,{outro_start:.2f},{total_dur:.2f})"

        filters.append(
            f"drawbox=x=0:y=0:w={TARGET_W}:h={TARGET_H}"
            f":color=black@0.55:t=fill:enable='{outro_enable}'"
        )
        # Text branding below logo
        outro_texts = [
            ("Follow for more", TARGET_H // 2 + 280, "white", 48),
            ("Save this video", TARGET_H // 2 + 360, "#FFE234", 40),
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

        # ── Check for logo ─────────────────────────────────────────────
        logo_path = Path("assets/logo.png")
        has_logo = logo_path.exists()
        if has_logo:
            logger.info("Logo found: %s", logo_path)

        # ── Build ffmpeg command with optional music + logo ────────────
        if music_path and Path(music_path).exists():
            logger.info("Mixing background music: %s", music_path)
            if has_logo:
                # video + audio + music + logo
                logo_size = 500
                logo_x = (TARGET_W - logo_size) // 2
                logo_y = TARGET_H // 2 - 250
                cmd = [
                    "-y",
                    "-i", str(video),
                    "-i", str(audio),
                    "-i", str(music_path),
                    "-i", str(logo_path),
                    "-filter_complex",
                    f"[1:a]apad=whole_dur={total_dur}[voice];"
                    f"[2:a]aloop=loop=-1:size=2e+09,atrim=duration={total_dur},"
                    f"volume={BG_MUSIC_VOLUME}[music];"
                    f"[voice][music]amix=inputs=2:duration=first[aout];"
                    f"[0:v]{vf}[vtxt];"
                    f"[3:v]scale={logo_size}:{logo_size}[logo];"
                    f"[vtxt][logo]overlay={logo_x}:{logo_y}:enable='between(t,{outro_start:.2f},{total_dur:.2f})'[vout]",
                    "-map", "[vout]",
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
            if has_logo:
                # video + audio + logo only
                logo_size = 500
                logo_x = (TARGET_W - logo_size) // 2
                logo_y = TARGET_H // 2 - 250
                cmd = [
                    "-y",
                    "-i", str(video),
                    "-i", str(audio),
                    "-i", str(logo_path),
                    "-filter_complex",
                    f"[0:v]{vf}[vtxt];"
                    f"[2:v]scale={logo_size}:{logo_size}[logo];"
                    f"[vtxt][logo]overlay={logo_x}:{logo_y}:enable='between(t,{outro_start:.2f},{total_dur:.2f})'[vout]",
                    "-map", "[vout]",
                    "-map", "1:a",
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
        """
        Find a Latin font for Roman Hinglish captions.
        Captions use body text (Roman script) — no Devanagari needed.
        Priority: Bold fonts first for better readability.
        """
        candidates = [
            # Windows bold fonts
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/verdanab.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            # Linux (GitHub Actions)
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        for f in candidates:
            if Path(f).exists():
                logger.info("Using font: %s", f)
                return f.replace("\\", "/").replace("C:/", "C\\:/")
        raise RuntimeError("No font found.")


    def _transcribe_audio(self, audio_path: Path) -> list[dict]:
        """Transcribe audio using Groq Whisper. Returns segments with timestamps."""
        import os, httpx
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            logger.warning("GROQ_API_KEY not set — using fallback timing")
            return []
        try:
            logger.info("Transcribing with Groq Whisper...")
            with open(audio_path, "rb") as f:
                audio_data = f.read()
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, audio_data, "audio/mpeg")},
                    data={
                        "model": "whisper-large-v3-turbo",
                        "response_format": "verbose_json",
                        "language": "hi",
                    },
                )
                resp.raise_for_status()
                segments = resp.json().get("segments", [])
                logger.info("Whisper: %d segments transcribed", len(segments))
                return segments
        except Exception as e:
            logger.warning("Whisper failed: %s — using fallback", e)
            return []

    def _segments_to_caption_timing(
        self, segments: list[dict], hook_dur: float,
        voice_dur: float, body_text: str
    ) -> list[dict]:
        """
        Use Whisper segments for TIMING only.
        Use body_text (Roman Hinglish) for CAPTION TEXT.
        This gives perfectly synced Roman captions.
        """
        if not segments:
            return self._fallback_timing(body_text, hook_dur, voice_dur)

        # Get timestamps from Whisper segments (after hook)
        valid_segs = [
            s for s in segments
            if float(s.get("end", 0)) > hook_dur
        ]
        if not valid_segs:
            return self._fallback_timing(body_text, hook_dur, voice_dur)

        # Split Roman body_text into chunks
        roman_chunks = self._caption_chunks(body_text)
        if not roman_chunks:
            return self._fallback_timing(body_text, hook_dur, voice_dur)

        # Map Roman chunks to Whisper time segments
        total_segs = len(valid_segs)
        total_chunks = len(roman_chunks)
        captions = []

        for i, chunk in enumerate(roman_chunks):
            # Map chunk index to segment proportionally
            seg_idx = min(int(i * total_segs / total_chunks), total_segs - 1)
            seg = valid_segs[seg_idx]
            seg_start = float(seg.get("start", hook_dur))
            seg_end = float(seg.get("end", voice_dur))

            # Smooth timing — divide segment evenly among chunks mapped to it
            chunks_in_seg = max(1, round(total_chunks / total_segs))
            chunk_pos = i % chunks_in_seg
            chunk_dur = (seg_end - seg_start) / chunks_in_seg
            t_start = max(hook_dur, seg_start + chunk_pos * chunk_dur)
            t_end = min(voice_dur, t_start + chunk_dur)

            captions.append({
                "text": chunk,
                "start": t_start,
                "end": t_end,
            })

        # The proportional seg_idx/chunk_pos mapping above has no built-in
        # guarantee against overlap — chunk_pos cycles by global chunk
        # index, not by position within its mapped segment, so it drifts
        # out of sync whenever Whisper segment durations are uneven (which
        # real transcription output always has). Enforce a hard invariant
        # afterward: captions must be strictly chronological with no
        # overlap, same guarantee _build_even_captions provides.
        return self._enforce_monotonic(captions, hook_dur, voice_dur)

    def _enforce_monotonic(
        self, captions: list[dict], hook_dur: float, voice_dur: float,
        min_duration: float = 0.15,
    ) -> list[dict]:
        """Clamp a caption list so each entry starts no earlier than the
        previous one ends, guaranteeing no visual overlap regardless of
        how the upstream timing was computed. Never moves a start time
        backward to 'rescue' a caption that has no room left — that would
        violate the very invariant this exists to enforce. Captions that
        don't fit are dropped instead."""
        fixed = []
        prev_end = hook_dur
        for cap in captions:
            start = max(cap["start"], prev_end)
            if start >= voice_dur:
                break  # no room left for this or any later caption
            end = min(voice_dur, max(start + min_duration, cap["end"]))
            if end <= start:
                continue  # no room for this one specifically — skip it
            fixed.append({"text": cap["text"], "start": start, "end": end})
            prev_end = end
        return fixed

    def _fallback_timing(
        self, body_text: str, hook_dur: float, voice_dur: float
    ) -> list[dict]:
        """Fallback: distribute captions by character weight."""
        chunks = self._caption_chunks(body_text)
        if not chunks:
            return []
        available = max(1.0, voice_dur - hook_dur)
        total_weight = sum(max(8, len(c)) for c in chunks)
        captions = []
        cursor = hook_dur
        for chunk in chunks:
            dur = available * (max(8, len(chunk)) / total_weight)
            captions.append({
                "text": chunk,
                "start": cursor,
                "end": min(voice_dur, cursor + dur),
            })
            cursor += dur
        return captions

    def _build_even_captions(
        self, body_text: str, hook_dur: float, voice_dur: float
    ) -> list[dict]:
        """
        Build captions with guaranteed no-overlap timing.
        Simple approach: split body into chunks, divide time evenly.
        Each caption ends exactly when next one starts.

        Returns list of {text, start, end}.
        """
        import re

        # Clean body text — remove any Devanagari characters
        roman_text = re.sub(r'[ऀ-ॿ]+', '', body_text).strip()
        roman_text = re.sub(r'\s+', ' ', roman_text)

        if not roman_text:
            roman_text = body_text  # fallback to original

        # Split into sentences first
        sentences = re.split(r'(?<=[.!?])\s+', roman_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Break long sentences into shorter chunks (max 7 words)
        chunks = []
        for sentence in sentences:
            words = sentence.split()
            if len(words) <= 7:
                chunks.append(sentence)
            else:
                # Split into 6-word groups
                for i in range(0, len(words), 6):
                    chunk = " ".join(words[i:i+6])
                    if chunk:
                        chunks.append(chunk)

        if not chunks:
            return []

        # Distribute evenly across available time
        available = max(1.0, voice_dur - hook_dur)
        chunk_dur = available / len(chunks)

        captions = []
        for i, chunk in enumerate(chunks):
            t_start = hook_dur + i * chunk_dur
            t_end = hook_dur + (i + 1) * chunk_dur  # exactly when next starts
            t_end = min(t_end, voice_dur)

            captions.append({
                "text": chunk,
                "start": round(t_start, 3),
                "end": round(t_end, 3),
            })

        logger.debug("Built %d caption chunks, %.1fs each", len(chunks), chunk_dur)
        return captions

    def _caption_chunks(self, text: str) -> list[str]:
        """Split captions into readable sentence/phrase chunks."""
        text = re.sub(r"\s+", " ", text.strip())
        if not text:
            return []

        sentences = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+", text)
            if part.strip()
        ]
        chunks = []
        for sentence in sentences:
            if len(sentence) <= 54:
                chunks.append(sentence)
                continue

            words = sentence.split()
            current = []
            for word in words:
                candidate = " ".join(current + [word])
                if current and len(candidate) > 46:
                    chunks.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                chunks.append(" ".join(current))
        return chunks

    def _to_roman_hinglish(self, text: str) -> str:
        """
        If text contains Devanagari, use Roman Hinglish body_text instead.
        Captions should always be Roman script for readability on screen.
        This is called when building caption filters.
        """
        # Check if text has Devanagari characters
        has_devanagari = any('\u0900' <= c <= '\u097F' for c in text)
        if has_devanagari:
            # Return empty — caller should use roman body_text instead
            return ""
        return text

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
