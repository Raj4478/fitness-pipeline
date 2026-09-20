from __future__ import annotations

import base64
import hashlib
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
INTRO_DURATION = 1.6
HOOK_DURATION = 3.2
OUTRO_DURATION = 2.8
ASSET_DIRECTORY = Path(__file__).resolve().parent.parent / "assets"
KRISHNA_INTRO_SEGMENTS = (
    ASSET_DIRECTORY / "krishna-intro.00a.b64",
    ASSET_DIRECTORY / "krishna-intro.00b.b64",
    *(ASSET_DIRECTORY / f"krishna-intro.chunk{i:02d}.b64" for i in range(1, 9)),
    ASSET_DIRECTORY / "krishna-intro.09a.b64",
    ASSET_DIRECTORY / "krishna-intro.09b.b64",
)
KRISHNA_INTRO_SHA256 = "2e4b59b4afb465314e510707faa0e96de46641cbb67b4b12990ffb3c4eb66c73"
BANNED_HOOK_PHRASES = (
    "जीवन बदल",
    "जरूर सुन",
    "ज़रूर सुन",
    "अंत तक",
    "हैरान",
    "बहुत सुंदर",
    "हर किसी को",
    "हर भक्त को",
    "ये बात सुन",
    "यह बात सुन",
)


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


def materialize_krishna_intro(directory: Path) -> Path:
    try:
        encoded = "".join(path.read_text(encoding="ascii").strip() for path in KRISHNA_INTRO_SEGMENTS)
        payload = base64.b64decode(encoded, validate=True)
    except Exception as error:
        raise RuntimeError("krishna_intro_asset_invalid") from error
    if hashlib.sha256(payload).hexdigest() != KRISHNA_INTRO_SHA256:
        raise RuntimeError("krishna_intro_asset_checksum_failed")
    output = directory / "krishna-intro.jpg"
    output.write_bytes(payload)
    return output


def hook_is_specific(hook: str) -> bool:
    words = hook.split()
    return (
        4 <= len(words) <= 10
        and not any(phrase in hook for phrase in BANNED_HOOK_PHRASES)
    )


def transcript_topic(transcript: str) -> dict:
    topics = (
        (("चिंता", "फिक्र", "परेशान"), {
            "hook": "चिंता के समय मन को कैसे संभालें?",
            "takeaway": "सीख: चिंता बढ़े तो मन को भगवान के स्मरण में टिकाकर धैर्य रखने का अभ्यास करें।",
            "caption": "Premanand Ji Maharaj की इस वाणी में चिंता के समय मन को संभालने की सरल सीख सुनिए। 🙏",
            "hashtags": ["#मनकीशांति", "#भक्ति"],
        }),
        (("क्रोध", "गुस्सा"), {
            "hook": "गुस्सा आते ही मन को कैसे संभालें?",
            "takeaway": "सीख: क्रोध के क्षण में प्रतिक्रिया रोककर मन को शांत करने का अभ्यास करें।",
            "caption": "Premanand Ji Maharaj की इस वाणी में क्रोध के समय सही भाव बनाए रखने की सीख सुनिए। 🙏",
            "hashtags": ["#क्रोध", "#मनकीशांति"],
        }),
        (("अपमान", "बेइज्जती"), {
            "hook": "अपमान होने पर हमें क्या करना चाहिए?",
            "takeaway": "सीख: अपमान के समय तुरंत प्रतिक्रिया देने के बजाय धैर्य और विनम्रता बनाए रखें।",
            "caption": "Premanand Ji Maharaj की इस वाणी में अपमान के समय धैर्य रखने की सीख सुनिए। 🙏",
            "hashtags": ["#धैर्य", "#भक्ति"],
        }),
        (("दुख", "दुःख", "उदासी"), {
            "hook": "दुख के समय मन को कैसे संभालें?",
            "takeaway": "सीख: दुख में भी स्मरण, धैर्य और सही दृष्टि बनाए रखने का अभ्यास करें।",
            "caption": "Premanand Ji Maharaj की इस वाणी में दुख के समय मन को स्थिर रखने की सीख सुनिए। 🙏",
            "hashtags": ["#मनकीशांति", "#आध्यात्म"],
        }),
        (("विश्वास", "भरोसा"), {
            "hook": "भगवान पर भरोसा कैसे मजबूत करें?",
            "takeaway": "सीख: कठिन परिस्थिति में भी विश्वास को अभ्यास और स्मरण से मजबूत करें।",
            "caption": "Premanand Ji Maharaj की इस वाणी में भगवान पर विश्वास मजबूत करने की सीख सुनिए। 🙏",
            "hashtags": ["#विश्वास", "#भक्ति"],
        }),
        (("भक्ति",), {
            "hook": "सच्ची भक्ति की पहचान क्या है?",
            "takeaway": "सीख: भक्ति केवल शब्दों में नहीं, भाव और आचरण में भी दिखाई देनी चाहिए।",
            "caption": "Premanand Ji Maharaj की इस वाणी में सच्ची भक्ति के भाव को समझिए। 🙏",
            "hashtags": ["#भक्ति", "#राधेराधे"],
        }),
        (("नाम जप", "नामजप", "जप"), {
            "hook": "नाम जप में मन कैसे लगाया जाए?",
            "takeaway": "सीख: नाम जप में नियमितता रखें और भटकते मन को बार-बार प्रेम से वापस लाएँ।",
            "caption": "Premanand Ji Maharaj की इस वाणी में नाम जप में मन लगाने की सीख सुनिए। 🙏",
            "hashtags": ["#नामजप", "#भक्ति"],
        }),
        (("मोह", "आसक्ति"), {
            "hook": "मोह और आसक्ति से कैसे बचें?",
            "takeaway": "सीख: आसक्ति को पहचानकर विवेक, स्मरण और सही दृष्टि से मन को संतुलित रखें।",
            "caption": "Premanand Ji Maharaj की इस वाणी में मोह और आसक्ति को समझने की सीख सुनिए। 🙏",
            "hashtags": ["#वैराग्य", "#आध्यात्म"],
        }),
        (("प्रेम", "रिश्त"), {
            "hook": "रिश्तों में सही भाव कैसे रखा जाए?",
            "takeaway": "सीख: रिश्तों में अपेक्षा से अधिक करुणा, सम्मान और सही भाव को महत्व दें।",
            "caption": "Premanand Ji Maharaj की इस वाणी में रिश्तों में सही भाव रखने की सीख सुनिए। 🙏",
            "hashtags": ["#प्रेम", "#जीवनसीख"],
        }),
        (("मन", "शांति"), {
            "hook": "मन को स्थिर और शांत कैसे रखें?",
            "takeaway": "सीख: मन भटके तो उसे बार-बार स्मरण, धैर्य और सही विचार की ओर लौटाएँ।",
            "caption": "Premanand Ji Maharaj की इस वाणी में मन को शांत और स्थिर रखने की सीख सुनिए। 🙏",
            "hashtags": ["#मनकीशांति", "#भक्ति"],
        }),
    )
    for terms, editorial in topics:
        if any(term in transcript for term in terms):
            return editorial
    return {
        "hook": "कठिन समय में सही भाव कैसे रखा जाए?",
        "takeaway": "सीख: परिस्थिति कठिन हो तो भी प्रतिक्रिया से पहले मन को शांत कर सही भाव बनाए रखें।",
        "caption": "Premanand Ji Maharaj की इस वाणी से कठिन समय में सही भाव बनाए रखने की सीख समझिए। 🙏",
        "hashtags": ["#जीवनसीख", "#भक्ति"],
    }


def transcript_fallback_hook(transcript: str) -> str:
    return str(transcript_topic(transcript)["hook"])


def fallback_editorial(transcript: str, media_key: str) -> dict:
    topic = transcript_topic(transcript)
    fallback_tags = video_hashtags(media_key)
    return {
        "hook": clean(topic["hook"], 90),
        "takeaway": clean(topic["takeaway"], 170),
        "caption": clean(topic["caption"], 170),
        "hashtags": normalize_hashtags(topic["hashtags"], fallback_tags),
    }


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
    fallback = fallback_editorial(transcript, media_key)
    prompt = f"""Create an editorial layer for a devotional Instagram Reel using a source clip of Premanand Ji Maharaj.
Use only the supplied transcript as factual context. Do not invent or misquote him.

The Reel ALWAYS opens with a premium Krishna card that already says:
"आज का संदेश"
"प्रेमानंद जी महाराज की वाणी"

The hook appears immediately AFTER that card, over the first seconds of the real source clip.
Therefore the hook must CONTINUE the intro naturally. It must not repeat the intro or sound like another generic introduction.

Return JSON only with exactly: hook, takeaway, caption, hashtags.

HOOK RULES:
- Hindi Devanagari, 4-10 words.
- Pick ONE concrete problem, question, tension, or teaching actually present in the transcript.
- Prefer a natural question a viewer genuinely wants answered.
- Use a specific concept from the clip only when the transcript supports it.
- Never use generic praise, vague curiosity bait, or "watch till end".
- Forbidden styles include: "ये बात जीवन बदल देगी", "हर किसी को ये सुनना चाहिए", "बहुत सुंदर संदेश", "अंत तक देखें", "ज़रूर सुनें", "हैरान रह जाएंगे".

TAKEAWAY RULES:
- Hindi Devanagari, 8-20 words.
- Practical and faithful to the transcript.
- Clearly editorial summary, not a fabricated direct quote.

CAPTION RULES:
- Hindi/Hinglish, maximum 170 characters.
- Accurately describe the actual teaching in this clip.

HASHTAGS:
- Exactly 3.
- One must be #PremanandJiMaharaj.
- The other two must match the actual topic.
- No #viral, #trending, #explorepage.

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

    def request_editorial(request_prompt: str) -> dict:
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
                        "content": "Return only the requested structured editorial data. Keep wording respectful, specific, and grounded in the transcript.",
                    },
                    {"role": "user", "content": request_prompt},
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
        return json.loads(payload["choices"][0]["message"]["content"])

    # Editorial generation improves specificity when available, but it is not a
    # hard dependency. Download + transcription + rendering must still succeed
    # if the model refuses, times out, emits invalid JSON, or has a transient API error.
    try:
        data = request_editorial(prompt)
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError) as error:
        print(f"editorial fallback activated: {type(error).__name__}: {error}", file=sys.stderr)
        return fallback

    hook = clean(data.get("hook"), 90)
    if not hook_is_specific(hook):
        try:
            retry_data = request_editorial(
                prompt
                + f'\n\nThe previous hook "{hook}" was rejected as vague or too long. '
                  "Rewrite it as a concrete 4-10 word Hindi question tied to one specific idea in the transcript."
            )
            retry_hook = clean(retry_data.get("hook"), 90)
            if hook_is_specific(retry_hook):
                data = retry_data
                hook = retry_hook
        except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError) as error:
            print(f"editorial hook retry skipped: {type(error).__name__}: {error}", file=sys.stderr)

    if not hook_is_specific(hook):
        hook = fallback["hook"]

    fallback_tags = video_hashtags(media_key)
    return {
        "hook": hook,
        "takeaway": clean(data.get("takeaway"), 170) or fallback["takeaway"],
        "caption": clean(data.get("caption"), 170) or fallback["caption"],
        "hashtags": normalize_hashtags(data.get("hashtags"), fallback_tags)
        if data.get("hashtags")
        else fallback["hashtags"],
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
    intro_image = materialize_krishna_intro(directory)
    ass = directory / "captions.ass"
    hook = directory / "hook.txt"
    takeaway = directory / "takeaway.txt"
    intro, main, outro, output = [
        directory / name
        for name in ("intro.mp4", "main.mp4", "outro.mp4", "instagram-ready.mp4")
    ]
    write_ass(segments, ass)
    hook.write_text(wrap(editorial["hook"], 24), encoding="utf-8")
    takeaway.write_text(wrap(editorial["takeaway"], 27), encoding="utf-8")

    # Premium fixed identity card: the approved Krishna artwork already contains
    # "आज का संदेश" and "प्रेमानंद जी महाराज की वाणी".
    ffmpeg(
        "-y",
        "-loop", "1",
        "-framerate", "30",
        "-i", str(intro_image),
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-vf",
        (
            "scale=720:1280:flags=lanczos,"
            "fade=t=in:st=0:d=0.18,"
            f"fade=t=out:st={INTRO_DURATION - 0.28:.2f}:d=0.28"
        ),
        "-t", str(INTRO_DURATION),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "96k",
        "-ar", "44100",
        "-ac", "2",
        str(intro),
    )

    ass_path = str(ass).replace("'", r"\'")
    hook_path = str(hook).replace("'", r"\'")
    # The dynamic hook is deliberately placed on the real clip, after the Krishna
    # identity card, so the two screens read as one coherent thought.
    vf = (
        "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=30,"
        f"subtitles='{ass_path}',"
        f"drawtext=fontfile='{font}':text='Premanand Ji Maharaj • source clip':"
        "fontcolor=white@0.90:fontsize=22:x=(w-text_w)/2:y=30:"
        "box=1:boxcolor=0x061426@0.48:boxborderw=8,"
        f"drawbox=x=42:y=92:w=636:h=226:color=0x071426@0.76:t=fill:enable='between(t,0,{HOOK_DURATION})',"
        f"drawbox=x=42:y=92:w=636:h=226:color=0xD9B75F@0.95:t=3:enable='between(t,0,{HOOK_DURATION})',"
        f"drawtext=fontfile='{font}':textfile='{hook_path}':fontcolor=0xFFF2CF:"
        "fontsize=46:line_spacing=12:x=(w-text_w)/2:y=205-(text_h/2):"
        "shadowcolor=black@0.85:shadowx=2:shadowy=2:"
        f"enable='between(t,0,{HOOK_DURATION})'"
    )
    ffmpeg(
        "-y", "-i", str(video),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "24",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        str(main),
    )

    takeaway_path = str(takeaway).replace("'", r"\'")
    # Reuse the Krishna visual language for the takeaway instead of dropping to a
    # plain black card, keeping the Reel visually cohesive from first frame to last.
    outro_vf = (
        "scale=720:1280:flags=lanczos,"
        "boxblur=4:1,eq=brightness=-0.34:saturation=0.72,"
        "drawbox=x=34:y=300:w=652:h=500:color=0x061426@0.78:t=fill,"
        "drawbox=x=34:y=300:w=652:h=500:color=0xD9B75F@0.92:t=3,"
        f"drawtext=fontfile='{font}':text='आज की सीख':fontcolor=0xE7C46A:"
        "fontsize=34:x=(w-text_w)/2:y=350,"
        f"drawtext=fontfile='{font}':textfile='{takeaway_path}':fontcolor=0xFFF2CF:"
        "fontsize=42:line_spacing=13:x=(w-text_w)/2:y=505-(text_h/2):"
        "shadowcolor=black@0.9:shadowx=2:shadowy=2,"
        f"drawtext=fontfile='{font}':text='राधे राधे':fontcolor=0xE7C46A:"
        "fontsize=40:x=(w-text_w)/2:y=690,"
        f"fade=t=out:st={OUTRO_DURATION - 0.30:.2f}:d=0.30"
    )
    ffmpeg(
        "-y",
        "-loop", "1",
        "-framerate", "30",
        "-i", str(intro_image),
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", outro_vf,
        "-t", str(OUTRO_DURATION),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "96k",
        "-ar", "44100",
        "-ac", "2",
        str(outro),
    )

    ffmpeg(
        "-y",
        "-i", str(intro),
        "-i", str(main),
        "-i", str(outro),
        "-filter_complex",
        "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[v][a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "25",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "112k",
        "-movflags", "+faststart",
        str(output),
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
                    send_text(token, chat_id, "✨ Added the Krishna intro card, a transcript-specific hook on the source clip, synced subtitles, attribution and a styled takeaway outro. Review it before posting and only reuse footage you have permission to use.")
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
