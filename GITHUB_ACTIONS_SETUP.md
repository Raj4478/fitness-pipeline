# GitHub Actions Setup Guide

## Step 1 — Add Secrets to GitHub

Go to: `github.com/Raj4478/fitness-pipeline → Settings → Secrets → Actions → New secret`

Add these one by one:

| Secret Name | Value |
|-------------|-------|
| `GROQ_API_KEY` | your Groq key |
| `GEMINI_API_KEY` | your Gemini key |
| `ELEVENLABS_API_KEY` | your primary ElevenLabs key |
| `ELEVENLABS_API_KEY_2` | your second ElevenLabs key |
| `ELEVENLABS_API_KEY_3` | your third ElevenLabs key |
| `ELEVENLABS_VOICE_ID` | czQ9pLzjRaF61EAYjcPC |
| `PEXELS_API_KEY` | your Pexels key |
| `TELEGRAM_BOT_TOKEN` | your bot token |
| `TELEGRAM_ALLOWED_USER_ID` | 1349298892 |

## Step 2 — Schedule

Videos auto-generate at:
- 9:00 AM IST
- 1:00 PM IST  
- 9:00 PM IST

## Step 3 — Manual Trigger

Go to: `Actions → Daily FitFacts Video Generator → Run workflow`

## Step 4 — What You Receive on Telegram

For each video:
1. Notification message with filename
2. The MP4 video file
3. Caption + hashtags (ready to copy-paste for Instagram)
