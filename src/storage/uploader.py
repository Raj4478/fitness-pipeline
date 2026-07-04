"""
Media Uploader — GitHub Releases
Uploads video/audio files as GitHub Release assets.
Free, no abuse policy, 2GB per file limit, permanent URLs.

Flow:
  1. Check if a release for today exists, create if not
  2. Upload file as release asset
  3. Return public download URL
"""

import logging
import json
import urllib.request
import urllib.error
import base64
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
GITHUB_API = "https://api.github.com"


class MediaUploader:
    def __init__(self, settings):
        self.token = os.getenv("GH_UPLOAD_TOKEN", os.getenv("GITHUB_TOKEN", ""))
        self.repo  = os.getenv("GITHUB_REPOSITORY", "Raj4478/fitness-pipeline")
        if not self.token:
            raise ValueError(
                "GH_UPLOAD_TOKEN not set — add it to GitHub Secrets. "
                "Create a token at github.com/settings/tokens with 'repo' scope."
            )

    def _api(self, method: str, path: str, data: dict = None,
             headers_extra: dict = None) -> dict:
        url = f"{GITHUB_API}{path}"
        payload = json.dumps(data).encode() if data else None
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        if headers_extra:
            headers.update(headers_extra)

        req = urllib.request.Request(
            url, data=payload, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            logger.error("GitHub API %s %s → %d: %s", method, path, e.code, body[:200])
            raise Exception(f"GitHub API error {e.code}: {body[:200]}")

    def _get_or_create_release(self) -> dict:
        """Get today's release or create it."""
        today = datetime.now(IST).strftime("%Y-%m-%d")
        tag   = f"assets-{today}"

        # Try to get existing release
        try:
            release = self._api("GET", f"/repos/{self.repo}/releases/tags/{tag}")
            logger.info("Using existing release: %s", tag)
            return release
        except Exception:
            pass

        # Create new release
        logger.info("Creating new release: %s", tag)
        release = self._api("POST", f"/repos/{self.repo}/releases", {
            "tag_name":         tag,
            "name":             f"Assets {today}",
            "body":             f"Auto-generated assets for {today}",
            "draft":            False,
            "prerelease":       True,
            "target_commitish": "master",
        })
        return release

    def _upload_asset(self, release: dict, file_path: Path) -> str:
        """Upload a file as a release asset. Returns download URL."""
        upload_url = release["upload_url"].replace("{?name,label}", "")
        file_name  = file_path.name
        file_size  = file_path.stat().st_size

        logger.info("Uploading %s (%.1f MB) to GitHub Release...",
                    file_name, file_size / (1024 * 1024))

        # Determine content type
        ext = file_path.suffix.lower()
        content_type = {
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".webm": "video/webm",
        }.get(ext, "application/octet-stream")

        url = f"{upload_url}?name={file_name}"
        headers = {
            "Authorization": f"token {self.token}",
            "Content-Type":  content_type,
            "Accept":        "application/vnd.github.v3+json",
        }

        with open(file_path, "rb") as f:
            data = f.read()

        req = urllib.request.Request(
            url, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode())
                download_url = result["browser_download_url"]
                logger.info("Uploaded: %s", download_url)
                return download_url
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise Exception(f"Upload failed {e.code}: {body[:200]}")

    async def upload_video(self, video_path: Path, cleanup: bool = False) -> str:
        """Upload MP4 to GitHub Release. Returns public download URL."""
        release = self._get_or_create_release()
        url = self._upload_asset(release, video_path)

        if cleanup:
            try:
                video_path.unlink()
            except OSError:
                pass

        return url

    async def upload_audio(self, audio_path: Path) -> str:
        """Upload audio to GitHub Release. Returns public download URL."""
        release = self._get_or_create_release()
        url = self._upload_asset(release, audio_path)

        try:
            audio_path.unlink()
        except OSError:
            pass

        return url
