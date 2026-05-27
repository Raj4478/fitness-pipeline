"""
Pipeline Runner — runs the fitness pipeline in a subprocess
and streams logs back to the caller.
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_pipeline_async(
    niche: str = "fitness",
    topic: str = "",
    dry_run: bool = False,
) -> dict:
    """
    Run the pipeline in a subprocess.
    Returns dict with status, video_path, hook.
    """
    cmd = [sys.executable, "-m", "src.pipeline", "--niche", niche]
    if topic:
        cmd += ["--topic", topic]
    if dry_run:
        cmd.append("--dry-run")

    logger.info("Running pipeline: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(Path(__file__).parent.parent),
    )

    output_lines = []
    video_path = None
    hook = None

    async for line in proc.stdout:
        line_str = line.decode().strip()
        output_lines.append(line_str)
        logger.info("[pipeline] %s", line_str)

        # Parse video path from log
        if "Render complete:" in line_str:
            video_path = line_str.split("Render complete:")[-1].strip()
        if "Video rendered:" in line_str:
            video_path = line_str.split("Video rendered:")[-1].strip()
        if "hook=" in line_str:
            hook = line_str.split("hook=")[-1].strip()[:80]

    await proc.wait()

    return {
        "status": "success" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "video_path": video_path,
        "hook": hook,
        "log": "\n".join(output_lines[-20:]),  # last 20 lines
    }
