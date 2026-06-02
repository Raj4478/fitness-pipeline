"""
Video Asset Fetcher — Pexels API
Topic-aware curated queries for fitness content.
Falls back to LLM-generated query if topic not in map.
Tries multiple queries until HD portrait footage found.
"""

import logging
import random
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# ── Curated Pexels queries per fitness topic ───────────────────────────────────
TOPIC_QUERY_MAP = {
    "protein":          ["athlete eating meal", "bodybuilder food prep", "gym nutrition"],
    "protein myths":    ["bodybuilder eating food", "muscle food healthy", "athlete meal prep"],
    "vitamin d":        ["sunlight morning outdoor", "person sun exposure", "morning sunrise fitness"],
    "vitamin":          ["healthy supplements pills", "morning sunlight person", "nutrition health"],
    "sleep":            ["person sleeping bed", "night sleep rest", "bedroom sleeping"],
    "sleep muscle":     ["athlete sleeping recovery", "person sleeping night", "muscle recovery rest"],
    "walking":          ["person walking outdoor", "morning walk park", "walking fitness"],
    "running":          ["person running outdoor", "athlete running track", "morning run fitness"],
    "cardio":           ["person running gym", "cardio workout treadmill", "fitness cardio"],
    "gym":              ["gym workout weights", "man lifting weights gym", "bodybuilder training"],
    "workout":          ["intense gym workout", "man exercise weights", "gym training session"],
    "training":         ["athlete training gym", "weight training man", "gym workout intense"],
    "weight":           ["weight loss transformation", "person exercising gym", "fitness workout"],
    "fat":              ["body fat fitness", "weight loss exercise", "gym workout intense"],
    "intermittent":     ["empty plate clock", "fasting food table", "meal timing food"],
    "fasting":          ["empty plate morning", "clock food fasting", "intermittent fasting"],
    "sugar":            ["sugar food unhealthy", "person avoiding sugar", "healthy vs unhealthy food"],
    "sugar free":       ["diet drink soda", "sugar free beverage", "unhealthy drink"],
    "stress":           ["stressed person office", "meditation calm man", "stress relief yoga"],
    "gut":              ["healthy food gut", "probiotic food bowl", "digestive health food"],
    "bmi":              ["body measurement fitness", "person scale weight", "fitness measurement"],
    "creatine":         ["supplement powder gym", "athlete supplement drink", "gym pre workout"],
    "hydration":        ["person drinking water", "athlete water bottle", "hydration fitness"],
    "overtraining":     ["tired athlete rest", "exhausted gym person", "muscle fatigue rest"],
    "yoga":             ["yoga poses outdoor", "man yoga meditation", "yoga fitness calm"],
    "sitting":          ["person sitting desk office", "office worker chair", "sedentary lifestyle"],
    "morning workout":  ["morning gym workout", "sunrise exercise outdoor", "early morning fitness"],
    "evening workout":  ["evening gym workout", "night fitness training", "gym after work"],
    "processed food":   ["junk food unhealthy", "processed food packaging", "fast food unhealthy"],
}

FALLBACK_QUERIES = [
    "gym workout intense",
    "fitness training man",
    "athlete exercise outdoor",
    "bodybuilder gym weights",
]


@dataclass
class VideoAsset:
    url: str
    width: int
    height: int
    duration: int


class VideoAssetFetcher:
    def __init__(self, settings):
        self.settings = settings

    async def fetch(self, topic: str, visual_query: str = "") -> VideoAsset:
        """
        Fetch portrait fitness footage.
        Priority: curated topic map → LLM visual_query → fallback queries.
        """
        queries = self._get_queries(topic, visual_query)

        async with httpx.AsyncClient(timeout=15) as client:
            for query in queries:
                try:
                    asset = await self._search_pexels(client, query)
                    if asset:
                        logger.info("Video asset fetched: %s (query='%s')", asset.url, query)
                        return asset
                except Exception as e:
                    logger.warning("Pexels query '%s' failed: %s", query, e)

        raise RuntimeError(f"No portrait video found for topic='{topic}' after trying {len(queries)} queries")

    def _get_queries(self, topic: str, visual_query: str) -> list[str]:
        """Build ordered list of queries to try."""
        queries = []

        # 1. Curated map — most precise
        topic_lower = topic.lower()
        for key, q_list in TOPIC_QUERY_MAP.items():
            if key in topic_lower:
                queries.extend(q_list)
                break

        # 2. LLM-generated query
        if visual_query and visual_query not in queries:
            queries.append(visual_query)

        # 3. Fallback — always works
        queries.extend(FALLBACK_QUERIES)

        return queries

    async def _search_pexels(self, client: httpx.AsyncClient, query: str) -> VideoAsset | None:
        resp = await client.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": self.settings.pexels_api_key},
            params={
                "query": query,
                "orientation": "portrait",
                "size": "large",
                "per_page": 10,
            },
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])

        # Filter: prefer HD portrait videos with good duration
        for video in videos:
            for vf in video.get("video_files", []):
                w, h = vf.get("width", 0), vf.get("height", 0)
                dur = video.get("duration", 0)
                # Portrait + at least 8 seconds + reasonable resolution
                if h > w and dur >= 8 and w >= 360:
                    return VideoAsset(
                        url=vf["link"],
                        width=w,
                        height=h,
                        duration=dur,
                    )
        return None
