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

        # ── Top videos with per-video RETENTION metrics ───────────────
        # View count alone is misleading — a video with 1000 views at 20%
        # retention is worse than 500 views at 60% retention because the
        # algorithm uses retention to decide whether to keep distributing.
        # YouTube Analytics API supports per-video averageViewDuration and
        # averageViewPercentage via dimensions=video.
        video_ids = [item["id"]["videoId"] for item in videos_resp.get("items", [])]

        top_videos_info = ""
        retention_by_video = {}

        if video_ids:
            # Fetch view counts and titles
            vids_resp = youtube.videos().list(
                part="statistics,snippet",
                id=",".join(video_ids[:10]),
            ).execute()

            # Fetch per-video retention from Analytics API
            try:
                retention_resp = yt_analytics.reports().query(
                    ids="channel==MINE",
                    startDate=str(week_ago),
                    endDate=str(yesterday),
                    metrics="views,averageViewDuration,averageViewPercentage",
                    dimensions="video",
                    sort="-views",
                    maxResults=10,
                ).execute()

                for row in retention_resp.get("rows", []):
                    vid_id = row[0]
                    retention_by_video[vid_id] = {
                        "views": int(row[1]),
                        "avg_duration": float(row[2]),
                        "avg_pct": float(row[3]),
                    }
            except Exception as e:
                logger.warning("Per-video retention fetch failed: %s", e)

            vids = sorted(
                vids_resp.get("items", []),
                key=lambda v: int(v["statistics"].get("viewCount", 0)),
                reverse=True,
            )[:5]

            lines = []
            for v in vids:
                vid_id = v["id"]
                title = v["snippet"]["title"][:35]
                views = format_num(v["statistics"].get("viewCount", 0))
                likes = format_num(v["statistics"].get("likeCount", 0))

                ret = retention_by_video.get(vid_id, {})
                if ret:
                    avg_dur = int(ret.get("avg_duration", 0))
                    avg_pct = ret.get("avg_pct", 0)
                    ret_str = f"{avg_dur}s ({avg_pct:.0f}%)"
                else:
                    ret_str = "N/A"

                lines.append(
                    f"  • {views} views | {likes}❤️ | ⏱{ret_str}\n"
                    f"    {title}"
                )
            top_videos_info = "\n".join(lines)

        # ── Topic performance summary ──────────────────────────────────
        # Map video titles back to topics by keyword matching so you can
        # see which content buckets are retaining viewers vs getting swiped.
        TOPIC_KEYWORDS = {
            "protein": "protein myths",
            "vitamin": "vitamin d deficiency",
            "sleep": "sleep & muscle",
            "sugar": "sugar-free drinks",
            "walking": "walking vs running",
            "creatine": "creatine",
            "fasting": "intermittent fasting",
            "gym": "gym myths",
            "cardio": "cardio vs weights",
            "stress": "stress & belly fat",
            "overtraining": "overtraining",
            "morning": "morning vs evening",
            "hydration": "hydration",
            "bmi": "bmi myths",
            "processed": "processed food",
            "gut": "gut health",
            "yoga": "yoga science",
            "sitting": "sitting disease",
            "cold water": "cold water myth",
            "indian diet": "indian diet",
        }

        topic_perf_lines = []
        for vid_id, ret in sorted(
            retention_by_video.items(),
            key=lambda x: x[1].get("avg_pct", 0),
            reverse=True
        )[:5]:
            # Find matching video title
            vid_title = next(
                (v["snippet"]["title"].lower()
                 for v in vids_resp.get("items", []) if v["id"] == vid_id),
                "",
            )
            topic_label = next(
                (label for kw, label in TOPIC_KEYWORDS.items() if kw in vid_title),
                vid_title[:25] or vid_id,
            )
            avg_pct = ret.get("avg_pct", 0)
            avg_dur = int(ret.get("avg_duration", 0))
            views = format_num(ret.get("views", 0))
            emoji = "🔥" if avg_pct >= 50 else "✅" if avg_pct >= 30 else "⚠️"
            topic_perf_lines.append(
                f"  {emoji} {topic_label}: {avg_pct:.0f}% ret | {avg_dur}s | {views} views"
            )

        topic_perf_section = ""
        if topic_perf_lines:
            topic_perf_section = (
                f"\n━━━ TOPIC RETENTION (best→worst) ━━━\n"
                + "\n".join(topic_perf_lines)
                + "\n🔥=50%+ ✅=30-49% ⚠️=<30%\n"
            )

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
            f"━━━ TOP 5 VIDEOS (views + retention) ━━━\n"
            f"{top_videos_info}"
            f"{topic_perf_section}\n"
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
