"""Recording orchestration: FFmpeg process management, capture thread, remux."""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

from audio import build_audio_args, get_audio_filter_args, detect_wasapi_loopback
from capture import CaptureLoop, MonitorInfo
from utils import generate_video_filename, generate_temp_filename, format_file_size

logger = logging.getLogger(__name__)


class RecorderState(Enum):
    """Possible states of the recording engine."""

    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()
    STOPPING = auto()


@dataclass
class RecordingOptions:
    """All parameters needed to start a recording session.

    Attributes:
        monitor: Which monitor to capture.
        fps: Target frame rate.
        target_width: Output frame width after scaling.
        target_height: Output frame height after scaling.
        use_qsv: True to use h264_qsv; False to use libx264 ultrafast.
        qsv_quality: QSV global_quality value.
        x264_crf: libx264 CRF value.
        x264_preset: libx264 preset name.
        system_audio: Capture system audio via WASAPI loopback.
        mic_enabled: Capture microphone audio.
        mic_device: Name of the microphone device (or None).
        output_folder: Directory to write recordings to.
        ffmpeg_path: Path to the ffmpeg executable.
    """

    monitor: MonitorInfo
    fps: int
    target_width: int
    target_height: int
    use_qsv: bool
    qsv_quality: int
    x264_crf: int
    x264_preset: str
    system_audio: bool
    mic_enabled: bool
    mic_device: Optional[str]
    output_folder: Path
    ffmpeg_path: Path


@dataclass
class RecorderStatus:
    """Live status data exposed to the UI.

    Attributes:
        state: Current recorder state.
        elapsed_seconds: Seconds elapsed since recording started (frozen while paused).
        output_file: Final output file path (set after successful stop).
        file_size_bytes: Current size of the temp MKV file.
        error_message: Non-empty string if an error occurred.
    """

    state: RecorderState = RecorderState.IDLE
    elapsed_seconds: int = 0
    output_file: Optional[Path] = None
    file_size_bytes: int = 0
    error_message: str = ""


class Recorder:
    """Manages the full lifecycle of a screen recording session.

    Spawns an FFmpeg subprocess, feeds it frames via a CaptureLoop, handles
    pause/resume, and remuxes MKV → MP4 on stop.  All heavy work runs in
    daemon threads; the UI is never blocked.

    Attributes:
        status: Live RecorderStatus object read by the UI.
        on_status_change: Optional callback invoked whenever status changes.
    """

    def __init__(self, on_status_change: Optional[Callable[[], None]] = None) -> None:
        """Initialise recorder with no active session.

        Args:
            on_status_change: Zero-argument callback invoked on status updates.
        """
        self.status = RecorderStatus()
        self.on_status_change = on_status_change

        self._options: Optional[RecordingOptions] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._capture_loop: Optional[CaptureLoop] = None
        self._temp_path: Optional[Path] = None
        self._final_path: Optional[Path] = None
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_timer = threading.Event()
        self._loopback_device: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, options: RecordingOptions) -> bool:
        """Begin a recording session.

        Args:
            options: All recording parameters.

        Returns:
            True if the session started successfully, False on error.
        """
        if self.status.state != RecorderState.IDLE:
            logger.warning("start() called while not IDLE (state=%s)", self.status.state)
            return False

        self._options = options
        self.status = RecorderStatus()

        # Detect system audio loopback device
        if options.system_audio:
            self._loopback_device = detect_wasapi_loopback()
        else:
            self._loopback_device = None

        # Prepare file paths
        temp_name = generate_temp_filename()
        final_name = generate_video_filename()
        self._temp_path = options.output_folder / temp_name
        self._final_path = options.output_folder / final_name

        # Build and launch FFmpeg
        cmd = self._build_ffmpeg_command(options)
        logger.info("FFmpeg command: %s", " ".join(str(a) for a in cmd))

        try:
            self._ffmpeg_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as exc:
            self._set_error(f"Could not launch FFmpeg: {exc}")
            return False

        # Start FFmpeg stderr logger
        threading.Thread(
            target=self._log_ffmpeg_stderr,
            args=(self._ffmpeg_proc,),
            daemon=True,
            name="FFmpegStderr",
        ).start()

        # Start capture loop
        self._capture_loop = CaptureLoop(
            monitor=options.monitor,
            fps=options.fps,
            target_width=options.target_width,
            target_height=options.target_height,
            ffmpeg_stdin=self._ffmpeg_proc.stdin,
            on_error=self._handle_capture_error,
        )
        self._capture_loop.start()

        # Start elapsed timer
        self._stop_timer.clear()
        self._timer_thread = threading.Thread(
            target=self._run_timer, daemon=True, name="RecordTimer"
        )
        self._timer_thread.start()

        self.status.state = RecorderState.RECORDING
        self._notify()
        logger.info("Recording started → temp: %s", self._temp_path)
        return True

    def stop(self) -> None:
        """Stop the current recording session and remux MKV to MP4.

        Runs synchronously in a daemon thread so the UI is not blocked.
        """
        if self.status.state not in (RecorderState.RECORDING, RecorderState.PAUSED):
            return

        self.status.state = RecorderState.STOPPING
        self._notify()

        threading.Thread(target=self._do_stop, daemon=True, name="RecorderStop").start()

    def pause(self) -> None:
        """Pause the active recording (frame capture stops; timer freezes)."""
        if self.status.state != RecorderState.RECORDING:
            return
        if self._capture_loop:
            self._capture_loop.pause()
        self.status.state = RecorderState.PAUSED
        self._notify()
        logger.info("Recording paused.")

    def resume(self) -> None:
        """Resume a paused recording."""
        if self.status.state != RecorderState.PAUSED:
            return
        if self._capture_loop:
            self._capture_loop.resume()
        self.status.state = RecorderState.RECORDING
        self._notify()
        logger.info("Recording resumed.")

    def toggle_pause(self) -> None:
        """Toggle between RECORDING and PAUSED states."""
        if self.status.state == RecorderState.RECORDING:
            self.pause()
        elif self.status.state == RecorderState.PAUSED:
            self.resume()

    def toggle_record(self, options: Optional[RecordingOptions] = None) -> None:
        """Start recording (if idle) or stop (if recording/paused).

        Args:
            options: Required when starting; ignored when stopping.
        """
        if self.status.state == RecorderState.IDLE:
            if options:
                self.start(options)
        elif self.status.state in (RecorderState.RECORDING, RecorderState.PAUSED):
            self.stop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_ffmpeg_command(self, opts: RecordingOptions) -> list:
        """Construct the full FFmpeg command list.

        Args:
            opts: Recording options.

        Returns:
            List of strings/Paths forming the FFmpeg command.
        """
        w, h = opts.target_width, opts.target_height
        cmd = [
            str(opts.ffmpeg_path),
            "-y",
            "-hide_banner",
            "-loglevel", "warning",
            # Video input from stdin pipe
            "-f", "rawvideo",
            "-pixel_format", "bgr24",
            "-video_size", f"{w}x{h}",
            "-framerate", str(opts.fps),
            "-i", "pipe:0",
        ]

        # Audio inputs
        audio_input_args = build_audio_args(
            system_audio=opts.system_audio,
            mic_enabled=opts.mic_enabled,
            mic_device=opts.mic_device,
            loopback_device=self._loopback_device,
        )
        cmd += audio_input_args

        # Video encoder
        if opts.use_qsv:
            cmd += [
                "-vcodec", "h264_qsv",
                "-global_quality", str(opts.qsv_quality),
                "-look_ahead", "0",
            ]
        else:
            cmd += [
                "-vcodec", "libx264",
                "-preset", opts.x264_preset,
                "-crf", str(opts.x264_crf),
            ]

        # Audio codec / filter
        audio_codec_args = get_audio_filter_args(
            system_audio=opts.system_audio,
            mic_enabled=opts.mic_enabled,
            loopback_device=self._loopback_device,
        )
        cmd += audio_codec_args

        # Output container
        cmd += ["-f", "matroska", str(self._temp_path)]
        return cmd

    def _do_stop(self) -> None:
        """Internal: stop capture, wait for FFmpeg, remux MKV → MP4."""
        try:
            # Stop capture
            if self._capture_loop:
                self._capture_loop.stop()

            # Stop timer
            self._stop_timer.set()

            # Close FFmpeg stdin and wait
            if self._ffmpeg_proc and self._ffmpeg_proc.stdin:
                try:
                    self._ffmpeg_proc.stdin.close()
                except OSError:
                    pass
            if self._ffmpeg_proc:
                try:
                    self._ffmpeg_proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self._ffmpeg_proc.kill()
                    self._ffmpeg_proc.wait()

                if self._ffmpeg_proc.returncode != 0:
                    # Check if QSV failed mid-encode → retry with x264
                    if self._options and self._options.use_qsv:
                        logger.warning("FFmpeg QSV encode failed (rc=%d); attempting x264 fallback restart is not possible at stop time.", self._ffmpeg_proc.returncode)
                    self._set_error(
                        f"Recording failed — FFmpeg crashed (rc={self._ffmpeg_proc.returncode}). "
                        f"Partial file may be in: {self._temp_path}"
                    )
                    self.status.state = RecorderState.IDLE
                    self._notify()
                    return

            # Remux MKV → MP4
            if self._temp_path and self._temp_path.exists() and self._final_path:
                success = self._remux(self._temp_path, self._final_path, self._options.ffmpeg_path)
                if success:
                    try:
                        self._temp_path.unlink()
                    except OSError as exc:
                        logger.warning("Could not delete temp MKV: %s", exc)
                    self.status.output_file = self._final_path
                    logger.info("Recording saved to: %s", self._final_path)
                else:
                    self._set_error(f"Remux failed. Partial file: {self._temp_path}")
            else:
                self._set_error("Temp MKV file not found after recording.")

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error during recording stop: %s", exc)
            self._set_error(str(exc))
        finally:
            self.status.state = RecorderState.IDLE
            self._notify()

    def _remux(self, src: Path, dst: Path, ffmpeg_path: Path) -> bool:
        """Remux an MKV file into an MP4 container (copy, no re-encode).

        Args:
            src: Path to the source MKV file.
            dst: Destination MP4 path.
            ffmpeg_path: Path to the ffmpeg executable.

        Returns:
            True on success, False on failure.
        """
        cmd = [
            str(ffmpeg_path),
            "-y",
            "-hide_banner",
            "-loglevel", "warning",
            "-i", str(src),
            "-codec", "copy",
            str(dst),
        ]
        logger.info("Remuxing: %s → %s", src, dst)
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode != 0:
                logger.error("Remux failed (rc=%d): %s", result.returncode, result.stderr.decode(errors="replace"))
                return False
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Remux exception: %s", exc)
            return False

    def _run_timer(self) -> None:
        """Increment elapsed_seconds every second while recording or paused.

        Freezes while state is PAUSED.
        """
        while not self._stop_timer.is_set():
            time.sleep(1)
            if self.status.state == RecorderState.RECORDING:
                self.status.elapsed_seconds += 1
                # Update file size
                if self._temp_path and self._temp_path.exists():
                    try:
                        self.status.file_size_bytes = self._temp_path.stat().st_size
                    except OSError:
                        pass
                self._notify()

    def _handle_capture_error(self, error_msg: str) -> None:
        """Invoked by the capture loop on a fatal capture error.

        Args:
            error_msg: Description of the error.
        """
        logger.error("Capture error: %s", error_msg)
        self._set_error(error_msg)
        # Trigger a graceful stop
        if self.status.state in (RecorderState.RECORDING, RecorderState.PAUSED):
            self.stop()

    def _set_error(self, message: str) -> None:
        """Set an error message in the status object.

        Args:
            message: Human-readable error description.
        """
        self.status.error_message = message
        logger.error("Recorder error: %s", message)
        self._notify()

    def _notify(self) -> None:
        """Invoke the on_status_change callback if registered."""
        if self.on_status_change:
            try:
                self.on_status_change()
            except Exception:  # pylint: disable=broad-except
                pass

    @staticmethod
    def _log_ffmpeg_stderr(proc: subprocess.Popen) -> None:
        """Read and log FFmpeg stderr output until the process ends.

        Args:
            proc: The running FFmpeg subprocess.
        """
        try:
            for line in proc.stderr:
                decoded = line.decode(errors="replace").rstrip()
                if decoded:
                    logger.debug("[ffmpeg] %s", decoded)
        except Exception:  # pylint: disable=broad-except
            pass
