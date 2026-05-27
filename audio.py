"""Audio device detection, WASAPI loopback, and microphone enumeration."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Known WASAPI loopback device names to try in order
_WASAPI_LOOPBACK_CANDIDATES = [
    "Stereo Mix",
    "What U Hear",
    "Wave Out Mix",
    "Stereo Mixdown",
]

# VB-Audio Virtual Cable fallback name
_VBAUDIO_CABLE = "CABLE Output (VB-Audio Virtual Cable)"


def list_microphone_devices() -> list[str]:
    """Return a list of available microphone (input) device names.

    Uses sounddevice to enumerate input devices. Returns an empty list
    if sounddevice is not available or no input devices are found.

    Returns:
        List of input device name strings.
    """
    try:
        import sounddevice as sd  # type: ignore
        devices = sd.query_devices()
        mics = [d["name"] for d in devices if d["max_input_channels"] > 0]
        logger.info("Found %d microphone device(s).", len(mics))
        return mics
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not enumerate microphone devices: %s", exc)
        return []


def detect_wasapi_loopback() -> Optional[str]:
    """Detect a usable WASAPI loopback device name for system audio capture.

    Tries known Stereo Mix variants first, then VB-Audio Virtual Cable.
    Returns the device name string if found (for use in FFmpeg -i argument),
    or None if no loopback device is detected.

    Returns:
        Device name string or None.
    """
    try:
        import sounddevice as sd  # type: ignore
        devices = sd.query_devices()
        output_names = [d["name"] for d in devices if d["max_input_channels"] > 0]

        for candidate in _WASAPI_LOOPBACK_CANDIDATES:
            for name in output_names:
                if candidate.lower() in name.lower():
                    logger.info("WASAPI loopback device found: %s", name)
                    return name

        # Check for VB-Audio
        for name in output_names:
            if "cable output" in name.lower() or "vb-audio" in name.lower():
                logger.info("VB-Audio Virtual Cable detected: %s", name)
                return name

        logger.warning("No WASAPI loopback device found. System audio will not be captured.")
        return None
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("WASAPI loopback detection failed: %s", exc)
        return None


def build_audio_args(
    system_audio: bool,
    mic_enabled: bool,
    mic_device: Optional[str],
    loopback_device: Optional[str],
) -> list[str]:
    """Build the FFmpeg audio input arguments for the recording command.

    Generates the -f / -i pairs for system audio and microphone inputs.
    If system audio is requested but no loopback device is found, logs a
    warning and skips system audio silently.

    Args:
        system_audio: Whether to capture system audio.
        mic_enabled: Whether to capture microphone audio.
        mic_device: Name of the selected microphone device.
        loopback_device: Name of the WASAPI loopback device (may be None).

    Returns:
        List of FFmpeg argument strings to insert before the output path.
    """
    args: list[str] = []

    if system_audio:
        if loopback_device:
            args += ["-f", "wasapi", "-i", loopback_device]
            logger.debug("System audio: WASAPI device '%s'", loopback_device)
        else:
            logger.warning("System audio requested but no loopback device available; skipping.")

    if mic_enabled and mic_device:
        args += ["-f", "dshow", "-i", f"audio={mic_device}"]
        logger.debug("Microphone: dshow device '%s'", mic_device)

    return args


def get_audio_filter_args(system_audio: bool, mic_enabled: bool, loopback_device: Optional[str]) -> list[str]:
    """Return FFmpeg audio codec / filter arguments.

    When both system audio and mic are active, mix them via amix.
    When only one is active, pass through directly.

    Args:
        system_audio: Whether system audio is enabled.
        mic_enabled: Whether microphone capture is enabled.
        loopback_device: Loopback device (None means system audio is unavailable).

    Returns:
        List of FFmpeg filter/codec argument strings.
    """
    actual_system = system_audio and loopback_device is not None
    actual_mic = mic_enabled

    if actual_system and actual_mic:
        return [
            "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=2",
            "-acodec", "aac", "-b:a", "128k",
        ]
    elif actual_system or actual_mic:
        return ["-acodec", "aac", "-b:a", "128k"]
    else:
        return ["-an"]  # no audio
