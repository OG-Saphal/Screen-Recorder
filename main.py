"""ScreenRec — entry point.

Performs startup checks (FFmpeg presence, QSV availability), configures
logging, then launches the tkinter UI.
"""

import logging
import logging.handlers
import sys
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — must happen before any other import that logs
# ---------------------------------------------------------------------------

_LOG_FILE = Path(__file__).parent / "screenrec.log"

def _setup_logging() -> None:
    """Configure the root logger with rotating file and console handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler (max 2 MB, 2 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    # Console handler (INFO and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)


_setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deferred imports (logging is now configured)
# ---------------------------------------------------------------------------

from ffmpeg_probe import find_ffmpeg, probe_qsv
from ui.app_window import AppWindow


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------

def _run_startup_checks() -> tuple[Path, bool]:
    """Verify FFmpeg is present and probe for QSV support.

    Shows error dialogs and exits if critical requirements are not met.

    Returns:
        Tuple of (ffmpeg_path, use_qsv).
    """
    # Need a minimal Tk root to show messageboxes before the main window
    _tmp_root = tk.Tk()
    _tmp_root.withdraw()

    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path is None:
        messagebox.showerror(
            "FFmpeg not found",
            "FFmpeg was not found in your PATH or in the application folder.\n\n"
            "Download FFmpeg from https://ffmpeg.org/download.html\n"
            "(get the Windows essentials build) and place ffmpeg.exe in the\n"
            "same folder as this application, then restart ScreenRec.",
        )
        _tmp_root.destroy()
        sys.exit(1)

    logger.info("FFmpeg found: %s", ffmpeg_path)

    use_qsv = probe_qsv(ffmpeg_path)
    if use_qsv:
        logger.info("Intel Quick Sync (h264_qsv) is available — using QSV encoder.")
    else:
        logger.info("QSV not available — falling back to libx264 ultrafast.")

    _tmp_root.destroy()
    return ffmpeg_path, use_qsv


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Application entry point."""
    logger.info("ScreenRec starting up.")

    ffmpeg_path, use_qsv = _run_startup_checks()

    root = tk.Tk()
    root.withdraw()  # hide while building UI

    try:
        app = AppWindow(root, ffmpeg_path=ffmpeg_path, use_qsv=use_qsv)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Failed to initialise AppWindow: %s", exc)
        messagebox.showerror("Startup error", f"ScreenRec failed to start:\n{exc}")
        root.destroy()
        sys.exit(1)

    root.deiconify()

    # Centre window on primary monitor at start
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - root.winfo_width()) // 2
    y = (sh - root.winfo_height()) // 3
    root.geometry(f"+{x}+{y}")

    logger.info("UI ready — entering mainloop.")
    root.mainloop()
    logger.info("ScreenRec exiting.")


if __name__ == "__main__":
    main()
