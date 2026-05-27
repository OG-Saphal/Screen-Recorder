"""Utility helpers: filename generation, folder management, timer formatting."""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_video_filename() -> str:
    """Generate a timestamped output filename for a video recording.

    Returns:
        Filename string like 'gameplay_2024-01-15_14-32-05.mp4'.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"gameplay_{ts}.mp4"


def generate_temp_filename() -> str:
    """Generate a timestamped temp filename for the intermediate MKV.

    Returns:
        Filename string like 'tmp_2024-01-15_14-32-05.mkv'.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"tmp_{ts}.mkv"


def generate_screenshot_filename() -> str:
    """Generate a timestamped filename for a PNG screenshot.

    Returns:
        Filename string like 'screenshot_2024-01-15_14-32-05.png'.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"screenshot_{ts}.png"


def ensure_output_folder(folder: Path) -> bool:
    """Create the output folder (including parents) if it does not exist.

    Args:
        folder: Desired output directory path.

    Returns:
        True on success, False if creation fails.
    """
    try:
        folder.mkdir(parents=True, exist_ok=True)
        logger.info("Output folder ready: %s", folder)
        return True
    except OSError as exc:
        logger.error("Could not create output folder %s: %s", folder, exc)
        return False


def format_timer(total_seconds: int) -> str:
    """Format an integer number of seconds as HH:MM:SS.

    Args:
        total_seconds: Elapsed time in whole seconds.

    Returns:
        String formatted as 'HH:MM:SS'.
    """
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_file_size(byte_count: int) -> str:
    """Format a byte count as a human-readable size string.

    Args:
        byte_count: Size in bytes.

    Returns:
        String like '142 MB' or '1.3 GB'.
    """
    if byte_count < 1024:
        return f"{byte_count} B"
    kb = byte_count / 1024
    if kb < 1024:
        return f"{kb:.0f} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


def truncate_path(path: Path, max_chars: int = 38) -> str:
    """Truncate a path string for display in a narrow UI label.

    Args:
        path: Full filesystem path.
        max_chars: Maximum display character count.

    Returns:
        Shortened string like 'C:\\Users\\...\\ScreenRec\\'.
    """
    s = str(path)
    if len(s) <= max_chars:
        return s
    keep = max_chars - 4
    return s[:keep // 2] + "..." + s[-(keep - keep // 2):]


def default_output_folder() -> Path:
    """Return the default output folder path for the current user.

    Returns:
        Path pointing to C:\\Users\\<username>\\Videos\\ScreenRec\\.
    """
    import os
    videos = Path(os.path.expanduser("~")) / "Videos" / "ScreenRec"
    return videos
