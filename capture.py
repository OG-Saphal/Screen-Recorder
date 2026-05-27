"""Screen capture loop using mss.

Grabs frames at a target frame rate and writes raw BGR bytes to a queue
or directly to an FFmpeg stdin pipe.
"""

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MonitorInfo:
    """Represents a connected monitor's geometry and a human-readable label.

    Attributes:
        index: mss monitor index (1-based; index 0 is the virtual full-desktop).
        left: Left edge pixel coordinate.
        top: Top edge pixel coordinate.
        width: Monitor width in pixels.
        height: Monitor height in pixels.
        label: Human-readable name shown in the UI dropdown.
    """

    index: int
    left: int
    top: int
    width: int
    height: int
    label: str


def detect_monitors() -> list[MonitorInfo]:
    """Detect all connected monitors using mss.

    Monitor at index 0 in mss is the combined virtual desktop; we skip it.
    Primary monitor (index 1) is labelled 'Laptop', others 'HDMI'.

    Returns:
        List of MonitorInfo instances, one per physical monitor.
    """
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            monitors = []
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    continue  # skip virtual desktop
                if i == 1:
                    label = f"Screen {i} — {mon['width']}×{mon['height']} (Laptop)"
                else:
                    label = f"Screen {i} — {mon['width']}×{mon['height']} (HDMI)"
                monitors.append(
                    MonitorInfo(
                        index=i,
                        left=mon["left"],
                        top=mon["top"],
                        width=mon["width"],
                        height=mon["height"],
                        label=label,
                    )
                )
            logger.info("Detected %d monitor(s).", len(monitors))
            return monitors
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Monitor detection failed: %s", exc)
        return []


class CaptureLoop:
    """Continuously captures frames from a monitor and writes to an FFmpeg pipe.

    The loop runs in a daemon thread.  Use the threading.Event objects to
    control recording state from the main thread.

    Attributes:
        stop_event: Set this to terminate the capture loop.
        pause_event: Set this to pause (frames are dropped while set).
        error_message: Set to a non-empty string if the loop exits with an error.
    """

    def __init__(
        self,
        monitor: MonitorInfo,
        fps: int,
        target_width: int,
        target_height: int,
        ffmpeg_stdin,
        on_frame_written: Optional[callable] = None,
        on_error: Optional[callable] = None,
    ) -> None:
        """Initialise the capture loop.

        Args:
            monitor: The MonitorInfo to capture.
            fps: Target frames per second.
            target_width: Output frame width (resize applied if needed).
            target_height: Output frame height.
            ffmpeg_stdin: Writable binary stream (FFmpeg process stdin).
            on_frame_written: Optional callback invoked after each frame write.
            on_error: Optional callback(error_msg: str) called on fatal error.
        """
        self.monitor = monitor
        self.fps = fps
        self.target_width = target_width
        self.target_height = target_height
        self.ffmpeg_stdin = ffmpeg_stdin
        self.on_frame_written = on_frame_written
        self.on_error = on_error

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.error_message: str = ""

        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the capture loop in a background daemon thread."""
        self.stop_event.clear()
        self.pause_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="CaptureLoop")
        self._thread.start()
        logger.info(
            "Capture started: monitor=%d, fps=%d, size=%dx%d",
            self.monitor.index, self.fps, self.target_width, self.target_height,
        )

    def stop(self) -> None:
        """Signal the capture loop to stop and wait for the thread to finish."""
        self.stop_event.set()
        self.pause_event.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Capture loop stopped.")

    def pause(self) -> None:
        """Pause frame capture (frames are skipped while paused)."""
        self.pause_event.set()
        logger.debug("Capture paused.")

    def resume(self) -> None:
        """Resume frame capture after a pause."""
        self.pause_event.clear()
        logger.debug("Capture resumed.")

    def _run(self) -> None:
        """Main capture loop body — runs on the background thread."""
        try:
            import mss  # type: ignore
            import cv2  # type: ignore  # noqa: F401 — needed for resize

            interval = 1.0 / self.fps
            needs_resize = (
                self.target_width != self.monitor.width
                or self.target_height != self.monitor.height
            )

            mon_rect = {
                "left": self.monitor.left,
                "top": self.monitor.top,
                "width": self.monitor.width,
                "height": self.monitor.height,
            }

            with mss.mss() as sct:
                while not self.stop_event.is_set():
                    frame_start = time.perf_counter()

                    if self.pause_event.is_set():
                        time.sleep(0.033)
                        continue

                    try:
                        raw = sct.grab(mon_rect)
                    except Exception as grab_exc:  # pylint: disable=broad-except
                        logger.error("mss grab failed: %s", grab_exc)
                        self.error_message = f"Monitor capture failed: {grab_exc}"
                        if self.on_error:
                            self.on_error(self.error_message)
                        break

                    # Convert BGRA → BGR (drop alpha channel)
                    img = np.array(raw)[:, :, :3]

                    if needs_resize:
                        import cv2 as _cv2
                        img = _cv2.resize(
                            img,
                            (self.target_width, self.target_height),
                            interpolation=_cv2.INTER_LINEAR,
                        )

                    try:
                        self.ffmpeg_stdin.write(img.tobytes())
                        self.ffmpeg_stdin.flush()
                    except OSError as write_exc:
                        logger.error("FFmpeg stdin write failed: %s", write_exc)
                        self.error_message = f"Output write error: {write_exc}"
                        if self.on_error:
                            self.on_error(self.error_message)
                        break

                    if self.on_frame_written:
                        try:
                            self.on_frame_written()
                        except Exception:  # pylint: disable=broad-except
                            pass

                    # Sleep for remaining frame budget
                    elapsed = time.perf_counter() - frame_start
                    sleep_time = interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Unhandled error in capture loop: %s", exc)
            self.error_message = str(exc)
            if self.on_error:
                self.on_error(self.error_message)
        finally:
            logger.debug("Capture thread exiting.")


def take_screenshot(monitor: MonitorInfo, output_path: Path) -> bool:
    """Capture a single PNG screenshot of the given monitor.

    Args:
        monitor: The MonitorInfo describing which monitor to capture.
        output_path: Full path where the PNG file should be saved.

    Returns:
        True on success, False on failure.
    """
    try:
        import mss  # type: ignore
        from PIL import Image  # type: ignore

        mon_rect = {
            "left": monitor.left,
            "top": monitor.top,
            "width": monitor.width,
            "height": monitor.height,
        }

        with mss.mss() as sct:
            raw = sct.grab(mon_rect)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            img.save(str(output_path), format="PNG")

        logger.info("Screenshot saved: %s", output_path)
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Screenshot failed: %s", exc)
        return False
