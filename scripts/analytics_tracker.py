"""
Analytics Tracker — fetches daily YouTube stats and sends to Telegram.
Runs daily to show CTR, views, avg view duration, subscribers gained.
"""

import os
import sys
import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def send_telegram(token: str, chat_id: str, msg: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": msg}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error("Telegram send failed: %s", e)


def format_num(n) -> str:
    if n is None:
        return "N/A"
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "")

    if not token or not chat_id:
        logger.error("Telegram credentials missing")
        sys.exit(1)

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
            client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
            client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
        )

        youtube = build("youtube", "v3", credentials=creds)
        yt_analytics = build("youtubeAnalytics", "v2", credentials=creds)

        # ── Channel stats ──────────────────────────────────────────────
        channel_resp = youtube.channels().list(
            part="statistics,snippet",
            mine=True
        ).execute()

        channel = channel_resp["items"][0]
        stats = channel["statistics"]
        channel_name = channel["snippet"]["title"]

        total_subs = format_num(stats.get("subscriberCount", 0))
        total_views = format_num(stats.get("viewCount", 0))
        total_videos = stats.get("videoCount", 0)

        # ── Analytics for last 7 days ──────────────────────────────────
        today = datetime.now(IST).date()
        week_ago = today - timedelta(days=7)
        yesterday = today - timedelta(days=1)

        analytics_resp = yt_analytics.reports().query(
            ids="channel==MINE",
            startDate=str(week_ago),
            endDate=str(yesterday),
            metrics="views,estimatedMinutesWatched,averageViewDuration,"
                    "subscribersGained,subscribersLost,likes,shares,comments",
            dimensions="day",
            sort="day",
        ).execute()

        rows = analytics_resp.get("rows", [])

        if rows:
            # Last 7 days totals
            total_7d_views = sum(int(r[1]) for r in rows)
            total_7d_subs = sum(int(r[4]) for r in rows)
            total_7d_subs_lost = sum(int(r[5]) for r in rows)
            total_7d_likes = sum(int(r[6]) for r in rows)
            total_7d_shares = sum(int(r[7]) for r in rows)
            avg_duration = sum(float(r[3]) for r in rows) / len(rows)

            # Yesterday only
            yesterday_row = rows[-1] if rows else None
            yd_views = int(yesterday_row[1]) if yesterday_row else 0
            yd_subs = int(yesterday_row[4]) if yesterday_row else 0

            # Best day this week
            best_row = max(rows, key=lambda r: int(r[1]))
            best_date = best_row[0]
            best_views = int(best_row[1])
        else:
            total_7d_views = total_7d_subs = total_7d_likes = 0
            total_7d_shares = total_7d_subs_lost = 0
            avg_duration = 0
            yd_views = yd_subs = best_views = 0
            best_date = str(yesterday)

        # ── Top 3 recent videos ────────────────────────────────────────
        videos_resp = youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            order="date",
            maxResults=5,
        ).execute()

        video_ids = [item["id"]["videoId"] for item in videos_resp.get("items", [])]

        top_videos_info = ""
        if video_ids:
            vids_resp = youtube.videos().list(
                part="statistics,snippet",
                id=",".join(video_ids[:5]),
            ).execute()

            vids = sorted(
                vids_resp.get("items", []),
                key=lambda v: int(v["statistics"].get("viewCount", 0)),
                reverse=True
            )[:3]

            lines = []
            for v in vids:
                title = v["snippet"]["title"][:40]
                views = format_num(v["statistics"].get("viewCount", 0))
                likes = format_num(v["statistics"].get("likeCount", 0))
                lines.append(f"  • {views} views | {likes} likes | {title}")
            top_videos_info = "\n".join(lines)

        # ── Build Telegram message ─────────────────────────────────────
        now_ist = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")

        msg = (
            f"📊 YOUTUBE ANALYTICS REPORT\n"
            f"{'='*35}\n"
            f"🕐 {now_ist}\n"
            f"📺 Channel: {channel_name}\n\n"
            f"━━━ CHANNEL TOTAL ━━━\n"
            f"👥 Subscribers: {total_subs}\n"
            f"👁 Total Views: {total_views}\n"
            f"🎬 Total Videos: {total_videos}\n\n"
            f"━━━ LAST 7 DAYS ━━━\n"
            f"👁 Views: {format_num(total_7d_views)}\n"
            f"👥 Subs Gained: +{total_7d_subs} | Lost: -{total_7d_subs_lost}\n"
            f"❤️ Likes: {format_num(total_7d_likes)}\n"
            f"🔗 Shares: {format_num(total_7d_shares)}\n"
            f"⏱ Avg Duration: {int(avg_duration)}s\n\n"
            f"━━━ YESTERDAY ━━━\n"
            f"👁 Views: {format_num(yd_views)}\n"
            f"👥 Subs: +{yd_subs}\n\n"
            f"━━━ BEST DAY THIS WEEK ━━━\n"
            f"📅 {best_date}: {format_num(best_views)} views\n\n"
            f"━━━ TOP 5 RECENT VIDEOS ━━━\n"
            f"{top_videos_info}\n\n"
            f"{'='*35}\n"
            f"Target: 10M views in 90 days for monetization 🎯"
        )

        send_telegram(token, chat_id, msg)
        logger.info("Analytics report sent to Telegram ✅")

    except Exception as e:
        logger.error("Analytics fetch failed: %s", e)
        # Send error notification
        send_telegram(token, chat_id,
            f"❌ Analytics fetch failed\nError: {str(e)[:200]}\n"
            f"Check YouTube credentials in GitHub Secrets")
        sys.exit(1)


if __name__ == "__main__":
    main()
