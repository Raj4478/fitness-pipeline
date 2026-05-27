# Fitness Content Pipeline 🏋️

Automated Instagram Reels pipeline for Indian fitness education content.

## What it does
- Fetches real health/fitness news daily (Google News RSS)
- Generates viral Hinglish scripts — fact-based, myth-busting (not gym ads)
- ElevenLabs voiceover in natural Hindi voice
- Pexels fitness B-roll footage
- ffmpeg renders final vertical 1080x1920 MP4
- Auto-publishes via Buffer

## Run
```bash
python -m src.pipeline --niche fitness --topic "protein myths" --dry-run
```

## Stack
- Groq (free LLM) → script
- ElevenLabs → voiceover  
- Pexels API → footage
- ffmpeg → render
- Buffer → publish
- GitHub Actions → daily automation
