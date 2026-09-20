from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from yt_dlp.utils import DownloadError

from download_youtube import (
    MAX_TELEGRAM_BYTES,
    BLOCKED_AVAILABILITY,
    download_at_height,
    inspect_media,
    send_text,
    send_video,
    validate_url,
    video_hashtags,
)

GROQ_TRANSCRIBE_MODEL = os.getenv("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3-turbo")
GROQ_EDITOR_MODEL = os.getenv("GROQ_EDITOR_MODEL", "openai/gpt-oss-20b")
TRANSFORM_MAX_SECONDS = int(os.getenv("TRANSFORM_MAX_DURATION_SECONDS", "180"))


def ffmpeg(*args: str) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        raise RuntimeError(f"ffmpeg_failed:{proc.stderr[-1200:]}")


def extract_audio(video: Path, audio: Path) -> None:
    ffmpeg("-y", "-i", str(video), "-vn", "-ar", "16000", "-ac", "1", "-c:a", "flac", str(audio))


def transcribe(audio: Path, api_key: str) -> dict:
    with audio.open("rb") as handle:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio.name, handle, "audio/flac")},
            data={
                "model": GROQ_TRANSCRIBE_MODEL,
                "response_format": "verbose_json",
                "language": "hi",
                "temperature": "0",
            },
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    if not str(payload.get("text") or "").strip():
        raise RuntimeError("transcript_empty")
    return payload


def clean(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit].rstrip()


def normalize_hashtags(value: object, fallback: str) -> list[str]:
    tags: list[str] = []
    if isinstance(value, list):
        for raw in value:
            tag = re.sub(r"[^\w\u0900-\u097F]", "", str(raw).lstrip("#"), flags=re.UNICODE)
            if tag:
                tags.append(f"#{tag}")
    tags = list(dict.fromkeys(tags))
    if "#PremanandJiMaharaj" not in tags:
        tags.insert(0, "#PremanandJiMaharaj")
    for tag in fallback.split():
        if len(tags) >= 3:
            break
        if tag not in tags:
            tags.append(tag)
    return tags[:3]


def make_editorial(transcript: str, title: str, media_key: str, api_key: str) -> dict:
    prompt = f"""Create an editorial layer for a devotional Instagram Reel using a source clip of Premanand Ji Maharaj.
Use only the supplied transcript as factual context. Do not invent or misquote him. Avoid clickbait.
Return JSON only with exactly: hook, takeaway, caption, hashtags.

hook: Hindi Devanagari, 5-12 words, specific to this clip.
takeaway: Hindi Devanagari, 8-22 words, clearly an editorial takeaway rather than a direct quote.
caption: Hindi/Hinglish, maximum 170 characters, accurately describes the clip.
hashtags: exactly 3 relevant hashtags; one must be #PremanandJiMaharaj; no #viral/#trending/#explorepage.

Source title: {title[:300]}
Transcript:
{transcript[:12000]}
"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["hook", "takeaway", "caption", "hashtags"],
        "properties": {
            "hook": {"type": "string"},
            "takeaway": {"type": "string"},
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
        },
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_EDITOR_MODEL,
            "reasoning_effort": "low",
            "max_completion_tokens": 2200,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "reel_editorial",
                    "strict": True,
                    "schema": schema,
                },
            },
            "messages": [
                {
                    "role": "system",
                    "content": "Return only the requested structured editorial data. Keep wording respectful and grounded in the transcript.",
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=90,
    )
    if not response.ok:
        raise RuntimeError(
            f"groq_editor_failed:{response.status_code}:{response.text[:800]}"
        )
    payload = response.json()
    if payload.get("choices", [{}])[0].get("finish_reason") == "length":
        raise RuntimeError("groq_editor_truncated")
    data = json.loads(payload["choices"][0]["message"]["content"])
    fallback = video_hashtags(media_key)
    return {
        "hook": clean(data.get("hook"), 90) or "आज की इस बात को ध्यान से सुनिए",
        "takeaway": clean(data.get("takeaway"), 170) or "सीख: इस बात पर मनन करें और इसे सही जगह अपने जीवन में लागू करें।",
        "caption": clean(data.get("caption"), 170) or "Premanand Ji Maharaj की इस बात का सार सुनिए और अपने जीवन से जोड़कर समझिए। 🙏",
        "hashtags": normalize_hashtags(data.get("hashtags"), fallback),
    }


def ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    return f"{int(seconds // 3600)}:{int((seconds % 3600) // 60):02d}:{seconds % 60:05.2f}"


def ass_escape(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def write_ass(segments: list[dict], path: Path) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Noto Sans Devanagari,42,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,3,0,2,52,52,125,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    rows = []
    for segment in segments:
        text = ass_escape(segment.get("text"))
        if not text:
            continue
        start = float(segment.get("start") or 0)
        end = max(start + 0.35, float(segment.get("end") or start + 1))
        rows.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}")
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def wrap(text: str, width: int) -> str:
    words, lines, current = text.split(), [], []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:3])


def font_path() -> str:
    for candidate in (
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("devanagari_font_missing")


def render(video: Path, segments: list[dict], editorial: dict, directory: Path) -> Path:
    font = font_path()
    ass = directory / "captions.ass"
    hook = directory / "hook.txt"
    takeaway = directory / "takeaway.txt"
    intro, main, outro, output = [directory / name for name in ("intro.mp4", "main.mp4", "outro.mp4", "instagram-ready.mp4")]
    write_ass(segments, ass)
    hook.write_text(wrap(editorial["hook"], 24), encoding="utf-8")
    takeaway.write_text(wrap(editorial["takeaway"], 27), encoding="utf-8")

    ffmpeg(
        "-y", "-f", "lavfi", "-i", "color=c=0x171717:s=720x1280:d=2.2:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", f"drawtext=fontfile='{font}':textfile='{hook}':fontcolor=white:fontsize=52:line_spacing=14:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.25:boxborderw=26",
        "-t", "2.2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2", str(intro),
    )

    ass_path = str(ass).replace("'", r"\'")
    vf = (
        "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=30,"
        f"subtitles='{ass_path}',"
        f"drawtext=fontfile='{font}':text='Premanand Ji Maharaj • source clip':fontcolor=white@0.88:fontsize=24:"
        "x=(w-text_w)/2:y=42:box=1:boxcolor=black@0.42:boxborderw=9"
    )
    ffmpeg(
        "-y", "-i", str(video), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(main),
    )

    ffmpeg(
        "-y", "-f", "lavfi", "-i", "color=c=0x171717:s=720x1280:d=3:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", (
            f"drawtext=fontfile='{font}':textfile='{takeaway}':fontcolor=white:fontsize=44:line_spacing=14:"
            "x=(w-text_w)/2:y=(h-text_h)/2-50:box=1:boxcolor=black@0.25:boxborderw=24,"
            f"drawtext=fontfile='{font}':text='राधे राधे':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=h-230"
        ),
        "-t", "3", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2", str(outro),
    )

    ffmpeg(
        "-y", "-i", str(intro), "-i", str(main), "-i", str(outro),
        "-filter_complex", "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "112k", "-movflags", "+faststart", str(output),
    )
    return output


def fit_for_telegram(video: Path, directory: Path) -> Path:
    if video.stat().st_size <= MAX_TELEGRAM_BYTES:
        return video
    smaller = directory / "instagram-ready-small.mp4"
    ffmpeg(
        "-y", "-i", str(video), "-vf", "scale=540:960:force_original_aspect_ratio=decrease",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "29", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(smaller),
    )
    if smaller.stat().st_size > MAX_TELEGRAM_BYTES:
        raise RuntimeError("telegram_size_limit")
    return smaller


def transform(source: Path, info: dict, media_key: str, directory: Path, api_key: str) -> tuple[Path, dict]:
    audio = directory / "speech.flac"
    extract_audio(source, audio)
    transcript = transcribe(audio, api_key)
    editorial = make_editorial(str(transcript["text"]), str(info.get("title") or ""), media_key, api_key)
    video = render(source, transcript.get("segments") or [], editorial, directory)
    return fit_for_telegram(video, directory), editorial


def main() -> int:
    url = os.getenv("MEDIA_URL", os.getenv("YOUTUBE_URL", "")).strip()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    max_duration = int(os.getenv("DOWNLOAD_MAX_DURATION_SECONDS", "900"))

    if not token or not re.fullmatch(r"\d+", chat_id):
        print("worker configuration incomplete", file=sys.stderr)
        return 2

    try:
        provider = validate_url(url)
        if not groq_key:
            raise RuntimeError("groq_api_key_missing")
        send_text(token, chat_id, f"🎬 {provider} received. Creating an Instagram-ready edited Reel…")
        info = inspect_media(url)
        availability = str(info.get("availability") or "").lower()
        if availability in BLOCKED_AVAILABILITY:
            raise RuntimeError("access_restricted_video")
        if info.get("is_live"):
            raise RuntimeError("live_stream_not_supported")
        duration = int(info.get("duration") or 0)
        if duration and duration > max_duration:
            raise RuntimeError("video_too_long")
        if duration and duration > TRANSFORM_MAX_SECONDS:
            raise RuntimeError("video_too_long_for_transform")

        with tempfile.TemporaryDirectory(prefix="telegram-transform-") as temp:
            directory = Path(temp)
            last_error: Exception | None = None
            for height in (720, 480, 360):
                try:
                    for item in directory.iterdir():
                        if item.is_file():
                            item.unlink()
                    source = download_at_height(url, directory, height, provider)
                    send_text(token, chat_id, "📝 Transcribing the speech and generating a clip-specific hook, takeaway and caption…")
                    result, editorial = transform(source, info, url, directory, groq_key)
                    hashtags = " ".join(editorial["hashtags"])
                    send_video(token, chat_id, result, f"✅ Instagram-ready edit\n\n{editorial['caption']}\n\n{hashtags}", hashtags)
                    send_text(token, chat_id, "✨ Added an original opening hook, synced subtitles, source attribution and a clip-specific takeaway. Review it before posting and only reuse footage you have permission to use.")
                    return 0
                except DownloadError as error:
                    last_error = error
                    continue
                except RuntimeError as error:
                    last_error = error
                    if str(error) in {"telegram_size_limit", "download_output_missing"}:
                        continue
                    raise
            raise last_error or RuntimeError("download_failed")
    except Exception as error:
        reason = str(error)
        messages = {
            "video_too_long": "The video exceeds the configured download duration limit.",
            "video_too_long_for_transform": f"The editor currently handles clips up to {TRANSFORM_MAX_SECONDS // 60} minutes. Send a shorter Reel/clip.",
            "live_stream_not_supported": "Live streams are not supported.",
            "access_restricted_video": "Private, members-only, premium or sign-in-gated media is not supported.",
            "groq_api_key_missing": "GROQ_API_KEY is missing from the GitHub Actions secrets.",
            "telegram_size_limit": "The transformed Reel could not be kept under Telegram’s 50 MB bot upload limit.",
            "invalid_media_url": "Only supported public YouTube URLs and Instagram Reel URLs can be processed.",
        }
        try:
            send_text(token, chat_id, f"❌ {messages.get(reason, 'The Reel transformation failed. Check the GitHub Actions log for the failed stage.')}")
        except Exception:
            pass
        print(f"transform worker failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
