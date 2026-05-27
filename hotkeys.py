"""Global hotkey registration and dispatching via the keyboard library.

Hotkeys work even when Unity (or any other app) is in fullscreen mode.
"""

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Default hotkey bindings
HOTKEY_RECORD = "f9"
HOTKEY_PAUSE = "f10"
HOTKEY_SCREENSHOT = "f11"


class HotkeyManager:
    """Registers and manages global hotkeys for the recorder application.

    All callbacks are invoked on the keyboard library's background thread.
    Callbacks must be thread-safe (e.g., use tkinter.after for UI updates).

    Attributes:
        on_record_toggle: Callback for F9 (start/stop recording).
        on_pause_toggle: Callback for F10 (pause/resume recording).
        on_screenshot: Callback for F11 (take screenshot).
    """

    def __init__(self) -> None:
        """Initialise the manager with no callbacks registered."""
        self.on_record_toggle: Optional[Callable[[], None]] = None
        self.on_pause_toggle: Optional[Callable[[], None]] = None
        self.on_screenshot: Optional[Callable[[], None]] = None
        self._registered = False
        self._lock = threading.Lock()

    def register(
        self,
        on_record_toggle: Callable[[], None],
        on_pause_toggle: Callable[[], None],
        on_screenshot: Callable[[], None],
    ) -> bool:
        """Register global hotkeys with the given callbacks.

        Args:
            on_record_toggle: Called when F9 is pressed.
            on_pause_toggle: Called when F10 is pressed.
            on_screenshot: Called when F11 is pressed.

        Returns:
            True if registration succeeded, False otherwise.
        """
        try:
            import keyboard  # type: ignore

            with self._lock:
                if self._registered:
                    self._unregister_all(keyboard)

                self.on_record_toggle = on_record_toggle
                self.on_pause_toggle = on_pause_toggle
                self.on_screenshot = on_screenshot

                keyboard.add_hotkey(HOTKEY_RECORD, self._safe_record, suppress=False)
                keyboard.add_hotkey(HOTKEY_PAUSE, self._safe_pause, suppress=False)
                keyboard.add_hotkey(HOTKEY_SCREENSHOT, self._safe_screenshot, suppress=False)

                self._registered = True
                logger.info(
                    "Global hotkeys registered: %s=record, %s=pause, %s=screenshot",
                    HOTKEY_RECORD, HOTKEY_PAUSE, HOTKEY_SCREENSHOT,
                )
                return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to register hotkeys: %s", exc)
            return False

    def unregister(self) -> None:
        """Unregister all hotkeys registered by this manager."""
        try:
            import keyboard  # type: ignore
            with self._lock:
                self._unregister_all(keyboard)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to unregister hotkeys: %s", exc)

    def _unregister_all(self, keyboard_module) -> None:
        """Internal: remove all hotkey bindings.

        Args:
            keyboard_module: The imported keyboard module.
        """
        try:
            keyboard_module.remove_hotkey(HOTKEY_RECORD)
        except KeyError:
            pass
        try:
            keyboard_module.remove_hotkey(HOTKEY_PAUSE)
        except KeyError:
            pass
        try:
            keyboard_module.remove_hotkey(HOTKEY_SCREENSHOT)
        except KeyError:
            pass
        self._registered = False

    def _safe_record(self) -> None:
        """Invoke the record-toggle callback, catching any exception."""
        if self.on_record_toggle:
            try:
                self.on_record_toggle()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Record hotkey callback error: %s", exc)

    def _safe_pause(self) -> None:
        """Invoke the pause-toggle callback, catching any exception."""
        if self.on_pause_toggle:
            try:
                self.on_pause_toggle()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Pause hotkey callback error: %s", exc)

    def _safe_screenshot(self) -> None:
        """Invoke the screenshot callback, catching any exception."""
        if self.on_screenshot:
            try:
                self.on_screenshot()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Screenshot hotkey callback error: %s", exc)
