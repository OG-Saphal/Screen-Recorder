"""FFmpeg presence check and QSV encoder availability probing."""

import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_ffmpeg() -> Path | None:
    """Locate ffmpeg binary: first in PATH, then alongside this script.

    Returns:
        Path to ffmpeg executable, or None if not found.
    """
    # Check PATH
    found = shutil.which("ffmpeg")
    if found:
        logger.info("FFmpeg found in PATH: %s", found)
        return Path(found)

    # Check app directory
    local = Path(__file__).parent / "ffmpeg.exe"
    if local.exists():
        logger.info("FFmpeg found in app directory: %s", local)
        return local

    logger.warning("FFmpeg not found in PATH or app directory.")
    return None


def probe_qsv(ffmpeg_path: Path) -> bool:
    """Test whether Intel Quick Sync Video (h264_qsv) encoder is available.

    Runs a short null-source encode; returns True if exit code is 0.

    Args:
        ffmpeg_path: Path to the ffmpeg executable.

    Returns:
        True if QSV is available, False otherwise.
    """
    cmd = [
        str(ffmpeg_path),
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", "nullsrc=s=64x64:d=1",
        "-vcodec", "h264_qsv",
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        available = result.returncode == 0
        logger.info("QSV probe result: %s (rc=%d)", "available" if available else "unavailable", result.returncode)
        return available
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("QSV probe failed with exception: %s", exc)
        return False


def get_ffmpeg_version(ffmpeg_path: Path) -> str:
    """Return a short FFmpeg version string for display purposes.

    Args:
        ffmpeg_path: Path to the ffmpeg executable.

    Returns:
        Version string like "6.1.1" or "unknown".
    """
    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        # "ffmpeg version 6.1.1 ..."
        parts = first_line.split()
        if len(parts) >= 3:
            return parts[2]
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Could not determine FFmpeg version: %s", exc)
    return "unknown"
