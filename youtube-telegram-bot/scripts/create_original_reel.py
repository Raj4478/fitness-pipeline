#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DURATION = 19.2
WIDTH = 1080
HEIGHT = 1920
SCENE_DURATIONS = (2.8, 3.0, 3.0, 3.3, 3.8, 3.3)
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


def wrap_words(value: str, width: int = 26) -> str:
    words = clean(value, 240).split()
    if not words:
        return ""
    lines, line = [], []
    size = 0
    for word in words:
        next_size = size + len(word) + (1 if line else 0)
        if line and next_size > width:
            lines.append(" ".join(line))
            line = [word]
            size = len(word)
        else:
            line.append(word)
            size = next_size
    if line:
        lines.append(" ".join(line))
    return r"\N".join(lines[:3])


def materialize_krishna(path: Path) -> Path:
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in ASSET_PARTS)
    payload = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(payload).hexdigest() != KRISHNA_SHA256:
        raise RuntimeError("krishna_asset_checksum_failed")
    path.write_bytes(payload)
    return path


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
        "line1": "मन को बदलने की शुरुआत अक्सर परिस्थिति से नहीं, अपनी प्रतिक्रिया को देखने से होती है।",
        "line2": "कुछ क्षण रुककर साँस और नाम स्मरण पर ध्यान दें, फिर अगला छोटा सही कदम चुनें।",
        "line3": "हर विचार को तुरंत सच मानना जरूरी नहीं; मन को दिशा देना भी एक अभ्यास है।",
        "takeaway": "आज पाँच मिनट फोन अलग रखकर शांत होकर नाम स्मरण करें।",
        "closing": "हर विचार का जवाब देना जरूरी नहीं।",
        "narration": "जब मन किसी बात में उलझ जाए, हर विचार के पीछे भागना जरूरी नहीं। पाँच मिनट रुकिए, फोन अलग रखिए, साँस सामान्य होने दीजिए और नाम स्मरण कीजिए। फिर केवल अगला छोटा सही कदम चुनिए।",
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
        "required": ["hook", "line1", "line2", "line3", "takeaway", "closing", "narration", "caption", "hashtags"],
        "properties": {
            "hook": {"type": "string"},
            "line1": {"type": "string"},
            "line2": {"type": "string"},
            "line3": {"type": "string"},
            "takeaway": {"type": "string"},
            "closing": {"type": "string"},
            "narration": {"type": "string"},
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

Return exactly these fields:
hook: 5-11 words, specific question/problem, strong from frame 1, no vague clickbait.
line1, line2, line3: 10-22 Hindi words each, each must add a different useful thought.
takeaway: 8-16 words, concrete action the viewer can try today.
closing: 5-12 Hindi words, memorable and shareable, emotionally resonant, no engagement bait.
narration: 32-42 Hindi words, smooth spoken script that fits a 19-second Reel and matches the on-screen ideas.
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
            "narration": clean(data.get("narration"), 420) or fallback["narration"],
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
        return f"Dialogue: 0,{ts(start)},{ts(end)},{style},,0,0,0,,{ass_escape(wrap_words(text))}"

    content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,Noto Sans Devanagari,78,&H00F4E7C8,&H000000FF,&H00101824,&H82050A12,-1,0,0,0,100,100,0,0,3,4,1,5,78,78,0,1
Style: Body,Noto Sans Devanagari,58,&H00FFF8EA,&H000000FF,&H00101824,&H88050A12,-1,0,0,0,100,100,0,0,3,4,1,5,92,92,0,1
Style: Take,Noto Sans Devanagari,62,&H00F4E7C8,&H000000FF,&H00101824,&H88050A12,-1,0,0,0,100,100,0,0,3,4,1,5,86,86,0,1
Style: Close,Noto Sans Devanagari,68,&H00FFFFFF,&H000000FF,&H00101824,&H88050A12,-1,0,0,0,100,100,0,0,3,4,1,5,86,86,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    t0 = 0.0
    t1 = t0 + SCENE_DURATIONS[0]
    t2 = t1 + SCENE_DURATIONS[1]
    t3 = t2 + SCENE_DURATIONS[2]
    t4 = t3 + SCENE_DURATIONS[3]
    t5 = t4 + SCENE_DURATIONS[4]
    t6 = t5 + SCENE_DURATIONS[5]
    rows = [
        event(t0, t1, "Hook", data["hook"]),
        event(t1, t2, "Body", data["line1"]),
        event(t2, t3, "Body", data["line2"]),
        event(t3, t4, "Body", data["line3"]),
        event(t4, t5, "Take", data["takeaway"]),
        event(t5, t6, "Close", data.get("closing") or "हर विचार का जवाब देना जरूरी नहीं।"),
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
            0.040 * math.sin(2 * math.pi * 146.83 * tt)
            + 0.026 * math.sin(2 * math.pi * 220.00 * tt)
            + 0.014 * math.sin(2 * math.pi * 293.66 * tt)
        )
        idx = min(len(melody) - 1, int(tt / note_len))
        local = tt - idx * note_len
        env = min(1.0, local / 0.10, max(0.0, (note_len - local) / 0.20))
        vibrato = 1.0 + 0.0028 * math.sin(2 * math.pi * 5.1 * local)
        freq = melody[idx] * vibrato
        sample += env * (
            0.095 * math.sin(2 * math.pi * freq * local)
            + 0.018 * math.sin(2 * math.pi * 2 * freq * local)
        )
        fade = min(1.0, tt / 0.7, max(0.0, (DURATION - tt) / 1.3))
        sample *= fade
        pcm.append(max(-32767, min(32767, int(sample * 32767))))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


async def make_tts(text: str, output: Path) -> bool:
    if os.getenv("ORIGINAL_REEL_SKIP_TTS") == "1":
        return False
    try:
        import edge_tts
        voice = os.getenv("ORIGINAL_REEL_TTS_VOICE", "hi-IN-MadhurNeural")
        await edge_tts.Communicate(text, voice=voice, rate="+4%", volume="-2%").save(str(output))
        return output.exists() and output.stat().st_size > 1000
    except Exception as exc:
        print(f"tts fallback to text-only: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def render(background: Path, ass: Path, music: Path, narration: Path | None, mood: str, output: Path) -> None:
    """Render the approved stable style: no zoompan, no shake, no blur filler, no crossfades."""
    cfg = MOODS[mood]
    ass_path = str(ass).replace("'", r"\'")
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={WIDTH}:{HEIGHT},"
        f"eq=brightness={cfg['brightness']}:saturation={cfg['saturation']},"
        "unsharp=5:5:0.35:5:5:0.0,"
        f"subtitles='{ass_path}':fontsdir='/usr/share/fonts',"
        "format=yuv420p"
    )
    if narration:
        run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", "30", "-i", str(background),
            "-i", str(narration), "-i", str(music),
            "-filter_complex",
            "[1:a]volume=1.10,highpass=f=90[n];"
            "[2:a]volume=0.18[m];"
            "[n][m]amix=inputs=2:duration=longest:dropout_transition=2,"
            f"afade=t=out:st={DURATION - 0.8}:d=0.8[a]",
            "-vf", video_filter,
            "-map", "0:v:0", "-map", "[a]",
            "-t", str(DURATION),
            "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", str(output),
        )
    else:
        run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", "30", "-i", str(background),
            "-i", str(music),
            "-vf", video_filter,
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", str(DURATION),
            "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
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
        send_text(token, chat_id, f"🎬 Creating your {MOODS[mood]['label'].lower()} Reel about: {topic}\n\nWriting the original Hindi script, narration and visual sequence…")

    data = generate_script(topic, mood, os.getenv("GROQ_API_KEY", "").strip())
    background = materialize_krishna(output_root / "krishna.jpg")
    ass = output_root / "reel.ass"
    music = output_root / "music.wav"
    narration = output_root / "narration.mp3"
    output = output_root / "original-devotional-reel.mp4"
    write_ass(data, ass)
    synth_music(music, mood)
    has_tts = asyncio.run(make_tts(data["narration"], narration))
    render(background, ass, music, narration if has_tts else None, mood, output)
    final = fit_telegram(output, output_root)

    if not skip_telegram:
        hashtags = " ".join(data["hashtags"])
        send_video(token, chat_id, final, f"✅ Original {MOODS[mood]['label']} Reel\n\n{data['caption']}\n\n{hashtags}")
        send_text(token, chat_id, "🎵 Music is generated specifically for this Reel in a Krishna-flute-inspired devotional style. No downloaded commercial soundtrack was used.")
    print(json.dumps({
        "ok": True,
        "mood": mood,
        "topic": topic,
        "video": str(final),
        "bytes": final.stat().st_size,
        "tts": has_tts,
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
