"""Main ScreenRec application window — all widgets, layout, and event wiring."""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Optional
import logging

from ui.styles import (
    BG_MAIN, BG_HEADER, BG_SECTION, BG_INPUT, BG_BUTTON,
    BG_RECORD_IDLE, BG_RECORD_ACTIVE, BG_HOVER,
    FG_PRIMARY, FG_SECONDARY, FG_ACCENT, FG_SUCCESS, FG_WARNING, FG_RECORD_BTN,
    BORDER_COLOR, SEP_COLOR,
    FONT_FAMILY, FONT_MONO,
    FONT_HEADER, FONT_LABEL, FONT_LABEL_SM, FONT_MUTED,
    FONT_RECORD, FONT_TIMER, FONT_STATUS, FONT_CLOSE,
    WINDOW_WIDTH, WINDOW_HEIGHT, HEADER_HEIGHT,
    PADDING_OUTER, PADDING_INNER,
    ENCODER_QSV_BG, ENCODER_QSV_FG, ENCODER_X264_BG, ENCODER_X264_FG,
)
from capture import detect_monitors, MonitorInfo, take_screenshot
from recorder import Recorder, RecordingOptions, RecorderState
from audio import list_microphone_devices, detect_wasapi_loopback
from hotkeys import HotkeyManager, HOTKEY_RECORD, HOTKEY_PAUSE, HOTKEY_SCREENSHOT
from utils import format_timer, format_file_size, truncate_path, default_output_folder, generate_screenshot_filename, ensure_output_folder
from ffmpeg_probe import find_ffmpeg, probe_qsv

logger = logging.getLogger(__name__)

# Quality preset definitions: (label, fps, width, height, qsv_quality, x264_crf, x264_preset)
QUALITY_PRESETS = {
    "light":    ("Light — 720p · 24fps",    24, 1280, 720,  26, 28, "ultrafast"),
    "balanced": ("Balanced — 720p · 30fps", 30, 1280, 720,  23, 26, "ultrafast"),
    "high":     ("High — 1080p · 30fps",    30, 1920, 1080, 20, 24, "superfast"),
}


class AppWindow:
    """The main ScreenRec floating window.

    Builds the full UI, wires all events, manages the Recorder instance,
    and handles hotkey callbacks via tkinter.after() for thread safety.
    """

    def __init__(self, root: tk.Tk, ffmpeg_path: Path, use_qsv: bool) -> None:
        """Construct and display the application window.

        Args:
            root: The Tk root window.
            ffmpeg_path: Verified path to the ffmpeg executable.
            use_qsv: Whether QSV was detected at startup.
        """
        self.root = root
        self.ffmpeg_path = ffmpeg_path
        self.use_qsv = use_qsv

        self._monitors: list[MonitorInfo] = []
        self._selected_monitor: Optional[MonitorInfo] = None
        self._output_folder: Path = default_output_folder()
        self._quality_key: str = "light"
        self._blink_state: bool = True
        self._blink_job = None
        self._hotkeys = HotkeyManager()

        self.recorder = Recorder(on_status_change=self._on_recorder_status)

        self._setup_window()
        self._build_ui()
        self._refresh_monitors()
        self._refresh_mic_list()
        self._update_status_bar_idle()
        self._register_hotkeys()

        ensure_output_folder(self._output_folder)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        """Configure root Tk window properties."""
        self.root.title("ScreenRec")
        self.root.configure(bg=BG_MAIN)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(False, False)
        self.root.wm_attributes("-topmost", True)
        self.root.overrideredirect(True)  # remove native title bar

        # Drag support
        self._drag_x = 0
        self._drag_y = 0

    # ------------------------------------------------------------------
    # Full UI build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create all widgets and pack them into the window."""
        self._build_header()
        self._build_separator()
        self._build_monitor_row()
        self._build_quality_row()
        self._build_audio_row()
        self._build_output_row()
        self._build_record_section()
        self._build_status_bar()
        self._build_hotkeys_section()

    def _build_header(self) -> None:
        """Build the draggable header strip with title and close button."""
        self._header = tk.Frame(
            self.root, bg=BG_HEADER, height=HEADER_HEIGHT, cursor="fleur"
        )
        self._header.pack(fill="x")
        self._header.pack_propagate(False)

        title = tk.Label(
            self._header, text="⏺  ScreenRec",
            bg=BG_HEADER, fg=FG_PRIMARY,
            font=FONT_HEADER, padx=10,
        )
        title.pack(side="left", pady=0)

        close_btn = tk.Button(
            self._header, text="×",
            bg=BG_HEADER, fg=FG_SECONDARY,
            font=FONT_CLOSE,
            relief="flat", bd=0,
            activebackground=FG_ACCENT, activeforeground=FG_PRIMARY,
            cursor="hand2", padx=8,
            command=self._on_close,
        )
        close_btn.pack(side="right", pady=0)

        # Bind drag to header and title
        for widget in (self._header, title):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)

    def _build_separator(self) -> None:
        """Add a 1px separator line below the header."""
        sep = tk.Frame(self.root, bg=SEP_COLOR, height=1)
        sep.pack(fill="x")

    def _build_monitor_row(self) -> None:
        """Build the monitor selector dropdown with a refresh button."""
        frame = tk.Frame(self.root, bg=BG_MAIN, padx=PADDING_OUTER)
        frame.pack(fill="x", pady=(8, 2))

        tk.Label(
            frame, text="Record screen:",
            bg=BG_MAIN, fg=FG_SECONDARY, font=FONT_LABEL,
        ).pack(anchor="w")

        row = tk.Frame(frame, bg=BG_MAIN)
        row.pack(fill="x", pady=(2, 0))

        self._monitor_var = tk.StringVar()
        self._monitor_combo = ttk.Combobox(
            row, textvariable=self._monitor_var,
            state="readonly", font=FONT_LABEL,
            width=28,
        )
        self._monitor_combo.pack(side="left", fill="x", expand=True)
        self._monitor_combo.bind("<<ComboboxSelected>>", self._on_monitor_selected)

        refresh_btn = tk.Button(
            row, text="↺",
            bg=BG_BUTTON, fg=FG_PRIMARY, font=(FONT_FAMILY, 10, "bold"),
            relief="flat", cursor="hand2", padx=6, pady=1,
            command=self._refresh_monitors,
        )
        refresh_btn.pack(side="left", padx=(4, 0))

        self._style_combobox()

    def _build_quality_row(self) -> None:
        """Build the quality preset radio buttons."""
        frame = tk.Frame(self.root, bg=BG_MAIN, padx=PADDING_OUTER)
        frame.pack(fill="x", pady=(6, 2))

        tk.Label(
            frame, text="Quality:",
            bg=BG_MAIN, fg=FG_SECONDARY, font=FONT_LABEL,
        ).pack(anchor="w")

        self._quality_var = tk.StringVar(value="light")

        presets = [
            ("light",    "Light — 720p · 24fps",     ""),
            ("balanced", "Balanced — 720p · 30fps",   "  recommended"),
            ("high",     "High — 1080p · 30fps",      "  may stutter"),
        ]
        for key, label_text, note in presets:
            row = tk.Frame(frame, bg=BG_MAIN)
            row.pack(anchor="w", pady=1)

            rb = tk.Radiobutton(
                row, text=label_text,
                variable=self._quality_var, value=key,
                bg=BG_MAIN, fg=FG_PRIMARY, font=FONT_LABEL,
                selectcolor=BG_SECTION, activebackground=BG_MAIN,
                relief="flat", cursor="hand2",
                command=self._on_quality_changed,
            )
            rb.pack(side="left")

            if note:
                color = FG_SUCCESS if "recommended" in note else FG_WARNING
                tk.Label(
                    row, text=note,
                    bg=BG_MAIN, fg=color, font=FONT_MUTED,
                ).pack(side="left")

    def _build_audio_row(self) -> None:
        """Build the system audio and microphone toggle checkboxes."""
        frame = tk.Frame(self.root, bg=BG_MAIN, padx=PADDING_OUTER)
        frame.pack(fill="x", pady=(6, 2))

        tk.Label(
            frame, text="Audio:",
            bg=BG_MAIN, fg=FG_SECONDARY, font=FONT_LABEL,
        ).pack(anchor="w")

        self._sys_audio_var = tk.BooleanVar(value=True)
        sys_check = tk.Checkbutton(
            frame, text="System audio",
            variable=self._sys_audio_var,
            bg=BG_MAIN, fg=FG_PRIMARY, font=FONT_LABEL,
            selectcolor=BG_SECTION, activebackground=BG_MAIN,
            relief="flat", cursor="hand2",
        )
        sys_check.pack(anchor="w", pady=1)

        self._mic_var = tk.BooleanVar(value=False)
        mic_row = tk.Frame(frame, bg=BG_MAIN)
        mic_row.pack(anchor="w", fill="x")

        mic_check = tk.Checkbutton(
            mic_row, text="Microphone",
            variable=self._mic_var,
            bg=BG_MAIN, fg=FG_PRIMARY, font=FONT_LABEL,
            selectcolor=BG_SECTION, activebackground=BG_MAIN,
            relief="flat", cursor="hand2",
            command=self._on_mic_toggled,
        )
        mic_check.pack(side="left", pady=1)

        self._mic_device_var = tk.StringVar()
        self._mic_combo = ttk.Combobox(
            mic_row, textvariable=self._mic_device_var,
            state="readonly", font=FONT_LABEL_SM, width=20,
        )
        self._mic_combo.pack(side="left", padx=(4, 0))
        self._mic_combo.pack_forget()  # hidden until mic checkbox ticked

    def _build_output_row(self) -> None:
        """Build the output folder path label and Browse button."""
        frame = tk.Frame(self.root, bg=BG_MAIN, padx=PADDING_OUTER)
        frame.pack(fill="x", pady=(6, 2))

        tk.Label(
            frame, text="Save to:",
            bg=BG_MAIN, fg=FG_SECONDARY, font=FONT_LABEL,
        ).pack(anchor="w")

        row = tk.Frame(frame, bg=BG_MAIN)
        row.pack(fill="x", pady=(2, 0))

        self._path_label = tk.Label(
            row,
            text=truncate_path(self._output_folder),
            bg=BG_INPUT, fg=FG_SECONDARY, font=FONT_LABEL_SM,
            anchor="w", padx=6, pady=3, relief="flat",
        )
        self._path_label.pack(side="left", fill="x", expand=True)

        browse_btn = tk.Button(
            row, text="Browse…",
            bg=BG_BUTTON, fg=FG_PRIMARY, font=FONT_LABEL,
            relief="flat", cursor="hand2", padx=6, pady=2,
            command=self._on_browse,
        )
        browse_btn.pack(side="left", padx=(4, 0))

    def _build_record_section(self) -> None:
        """Build the large Record button and live timer."""
        frame = tk.Frame(self.root, bg=BG_MAIN, padx=PADDING_OUTER)
        frame.pack(fill="x", pady=(8, 2))

        self._record_btn = tk.Button(
            frame,
            text="● Start Recording",
            bg=BG_RECORD_IDLE, fg=FG_RECORD_BTN,
            font=FONT_RECORD, relief="flat", cursor="hand2",
            padx=10, pady=8,
            command=self._on_record_toggle,
        )
        self._record_btn.pack(fill="x")

        self._timer_label = tk.Label(
            frame, text="",
            bg=BG_MAIN, fg=FG_SECONDARY, font=FONT_TIMER,
        )
        self._timer_label.pack(pady=(4, 0))

    def _build_status_bar(self) -> None:
        """Build the single-line status bar at the bottom."""
        sep = tk.Frame(self.root, bg=SEP_COLOR, height=1)
        sep.pack(fill="x", pady=(6, 0))

        self._status_frame = tk.Frame(self.root, bg=BG_MAIN, padx=PADDING_OUTER)
        self._status_frame.pack(fill="x", pady=(3, 2))

        self._status_label = tk.Label(
            self._status_frame, text="",
            bg=BG_MAIN, fg=FG_SECONDARY, font=FONT_STATUS,
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True)

        self._encoder_badge = tk.Label(
            self._status_frame, text="",
            bg=ENCODER_QSV_BG, fg=ENCODER_QSV_FG, font=FONT_STATUS,
            padx=5, pady=1,
        )
        self._encoder_badge.pack(side="right")

    def _build_hotkeys_section(self) -> None:
        """Build the collapsible hotkeys info section."""
        sep = tk.Frame(self.root, bg=SEP_COLOR, height=1)
        sep.pack(fill="x", pady=(2, 0))

        self._hotkeys_visible = tk.BooleanVar(value=False)
        toggle_row = tk.Frame(self.root, bg=BG_MAIN, padx=PADDING_OUTER)
        toggle_row.pack(fill="x")

        self._hotkeys_toggle_btn = tk.Button(
            toggle_row, text="▶ Hotkeys",
            bg=BG_MAIN, fg=FG_SECONDARY, font=FONT_MUTED,
            relief="flat", cursor="hand2", anchor="w",
            command=self._toggle_hotkeys,
        )
        self._hotkeys_toggle_btn.pack(fill="x", pady=(2, 0))

        self._hotkeys_frame = tk.Frame(self.root, bg=BG_SECTION, padx=PADDING_OUTER, pady=4)
        # Not packed initially — shown on toggle

        rows = [
            (HOTKEY_RECORD.upper(),     "Start / Stop recording"),
            (HOTKEY_PAUSE.upper(),      "Pause / Resume"),
            (HOTKEY_SCREENSHOT.upper(), "Save screenshot"),
        ]
        for key, action in rows:
            row = tk.Frame(self._hotkeys_frame, bg=BG_SECTION)
            row.pack(fill="x", pady=1)
            tk.Label(
                row, text=key,
                bg=BG_SECTION, fg=FG_ACCENT, font=(FONT_MONO, 8, "bold"), width=5,
            ).pack(side="left")
            tk.Label(
                row, text=action,
                bg=BG_SECTION, fg=FG_SECONDARY, font=FONT_MUTED,
            ).pack(side="left")

    # ------------------------------------------------------------------
    # Monitor helpers
    # ------------------------------------------------------------------

    def _refresh_monitors(self) -> None:
        """Re-detect connected monitors and update the dropdown."""
        self._monitors = detect_monitors()
        labels = [m.label for m in self._monitors]
        self._monitor_combo["values"] = labels
        if self._monitors:
            self._monitor_combo.current(0)
            self._selected_monitor = self._monitors[0]
        logger.debug("Monitors refreshed: %d found.", len(self._monitors))

    def _on_monitor_selected(self, _event=None) -> None:
        """Handle monitor dropdown selection change."""
        idx = self._monitor_combo.current()
        if 0 <= idx < len(self._monitors):
            self._selected_monitor = self._monitors[idx]

    # ------------------------------------------------------------------
    # Quality helpers
    # ------------------------------------------------------------------

    def _on_quality_changed(self) -> None:
        """Update the stored quality key when a radio button is clicked."""
        self._quality_key = self._quality_var.get()

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    def _refresh_mic_list(self) -> None:
        """Populate the microphone dropdown with available input devices."""
        mics = list_microphone_devices()
        self._mic_combo["values"] = mics
        if mics:
            self._mic_combo.current(0)

    def _on_mic_toggled(self) -> None:
        """Show/hide the microphone device dropdown based on checkbox state."""
        if self._mic_var.get():
            self._mic_combo.pack(side="left", padx=(4, 0))
        else:
            self._mic_combo.pack_forget()

    # ------------------------------------------------------------------
    # Output folder
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        """Open a folder picker dialog to change the output directory."""
        folder = filedialog.askdirectory(
            title="Select output folder",
            initialdir=str(self._output_folder),
        )
        if folder:
            self._output_folder = Path(folder)
            self._path_label.config(text=truncate_path(self._output_folder))
            ensure_output_folder(self._output_folder)

    # ------------------------------------------------------------------
    # Record button
    # ------------------------------------------------------------------

    def _on_record_toggle(self) -> None:
        """Handle the Record/Stop button click."""
        state = self.recorder.status.state
        if state == RecorderState.IDLE:
            self._start_recording()
        elif state in (RecorderState.RECORDING, RecorderState.PAUSED):
            self.recorder.stop()

    def _start_recording(self) -> None:
        """Build RecordingOptions and start the recorder."""
        if not self._selected_monitor:
            messagebox.showwarning("No monitor", "Please select a monitor to record.")
            return

        ensure_output_folder(self._output_folder)

        preset_key = self._quality_var.get()
        _label, fps, w, h, qsv_q, x264_crf, x264_preset = QUALITY_PRESETS[preset_key]

        mic_device = None
        if self._mic_var.get():
            mic_device = self._mic_device_var.get() or None

        opts = RecordingOptions(
            monitor=self._selected_monitor,
            fps=fps,
            target_width=w,
            target_height=h,
            use_qsv=self.use_qsv,
            qsv_quality=qsv_q,
            x264_crf=x264_crf,
            x264_preset=x264_preset,
            system_audio=self._sys_audio_var.get(),
            mic_enabled=self._mic_var.get(),
            mic_device=mic_device,
            output_folder=self._output_folder,
            ffmpeg_path=self.ffmpeg_path,
        )
        self.recorder.start(opts)

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------

    def _register_hotkeys(self) -> None:
        """Register global hotkeys, routing callbacks through tkinter.after."""
        self._hotkeys.register(
            on_record_toggle=lambda: self.root.after(0, self._on_record_toggle),
            on_pause_toggle=lambda: self.root.after(0, self._on_pause_toggle_hotkey),
            on_screenshot=lambda: self.root.after(0, self._on_screenshot_hotkey),
        )

    def _on_pause_toggle_hotkey(self) -> None:
        """Pause/resume handler invoked via F10 hotkey."""
        if self.recorder.status.state in (RecorderState.RECORDING, RecorderState.PAUSED):
            self.recorder.toggle_pause()

    def _on_screenshot_hotkey(self) -> None:
        """Screenshot handler invoked via F11 hotkey."""
        if not self._selected_monitor:
            return
        filename = generate_screenshot_filename()
        path = self._output_folder / filename
        ensure_output_folder(self._output_folder)
        threading.Thread(
            target=self._do_screenshot,
            args=(path,),
            daemon=True,
        ).start()

    def _do_screenshot(self, path: Path) -> None:
        """Take screenshot on background thread and update status bar.

        Args:
            path: Output path for the PNG file.
        """
        success = take_screenshot(self._selected_monitor, path)
        if success:
            self.root.after(0, lambda: self._set_status(f"Screenshot → {path.name}", FG_SUCCESS))
        else:
            self.root.after(0, lambda: self._set_status("Screenshot failed.", FG_ACCENT))

    # ------------------------------------------------------------------
    # Recorder status callback
    # ------------------------------------------------------------------

    def _on_recorder_status(self) -> None:
        """Called by Recorder on status changes — schedules UI refresh on main thread."""
        self.root.after(0, self._refresh_ui_from_status)

    def _refresh_ui_from_status(self) -> None:
        """Update all UI elements to reflect the current recorder status."""
        status = self.recorder.status
        state = status.state

        if status.error_message:
            self._set_status(status.error_message, FG_ACCENT)
            status.error_message = ""  # consume

        if state == RecorderState.IDLE:
            self._record_btn.config(
                text="● Start Recording",
                bg=BG_RECORD_IDLE,
            )
            self._timer_label.config(text="")
            self._cancel_blink()
            self._update_status_bar_idle()

        elif state == RecorderState.RECORDING:
            self._record_btn.config(
                text="■ Stop Recording",
                bg=BG_RECORD_ACTIVE,
            )
            elapsed = format_timer(status.elapsed_seconds)
            self._timer_label.config(text=elapsed, fg=FG_PRIMARY)
            size_str = format_file_size(status.file_size_bytes)
            self._set_status(f"Recording · {size_str}", FG_PRIMARY)

        elif state == RecorderState.PAUSED:
            self._record_btn.config(
                text="■ Stop Recording",
                bg=BG_RECORD_ACTIVE,
            )
            elapsed = format_timer(status.elapsed_seconds)
            self._timer_label.config(text=elapsed)
            self._set_status("Paused", FG_WARNING)
            self._start_blink()

        elif state == RecorderState.STOPPING:
            self._record_btn.config(text="Saving…", bg=BG_BUTTON)
            self._set_status("Saving…", FG_SECONDARY)
            self._cancel_blink()

        # Show saved filename once idle with output
        if state == RecorderState.IDLE and status.output_file:
            self._set_status(f"Saved · {status.output_file.name}", FG_SUCCESS)
            status.output_file = None  # consume

    def _update_status_bar_idle(self) -> None:
        """Set the idle status bar message with encoder info."""
        encoder = "QSV" if self.use_qsv else "x264 fallback"
        self._set_status(f"Ready · {encoder}", FG_SECONDARY)
        if self.use_qsv:
            self._encoder_badge.config(text="QSV", bg=ENCODER_QSV_BG, fg=ENCODER_QSV_FG)
        else:
            self._encoder_badge.config(text="x264", bg=ENCODER_X264_BG, fg=ENCODER_X264_FG)

    def _set_status(self, text: str, color=None) -> None:
        """Update the status label text and colour.

        Args:
            text: Message to display.
            color: Foreground colour string (defaults to FG_SECONDARY).
        """
        self._status_label.config(
            text=text,
            fg=color if color else FG_SECONDARY,
        )

    # ------------------------------------------------------------------
    # Blink (pause indicator)
    # ------------------------------------------------------------------

    def _start_blink(self) -> None:
        """Start the slow blink animation on the timer label (pause indicator)."""
        if self._blink_job is None:
            self._blink()

    def _blink(self) -> None:
        """Toggle timer label visibility every 800ms while paused."""
        if self.recorder.status.state != RecorderState.PAUSED:
            return
        self._blink_state = not self._blink_state
        color = FG_PRIMARY if self._blink_state else BG_MAIN
        self._timer_label.config(fg=color)
        self._blink_job = self.root.after(800, self._blink)

    def _cancel_blink(self) -> None:
        """Cancel the blink animation and restore timer label colour."""
        if self._blink_job:
            self.root.after_cancel(self._blink_job)
            self._blink_job = None
        self._timer_label.config(fg=FG_PRIMARY)

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------

    def _on_drag_start(self, event: tk.Event) -> None:
        """Record cursor position at drag start.

        Args:
            event: Tkinter mouse press event.
        """
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag_motion(self, event: tk.Event) -> None:
        """Move the window as the user drags.

        Args:
            event: Tkinter mouse motion event.
        """
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # Hotkeys toggle
    # ------------------------------------------------------------------

    def _toggle_hotkeys(self) -> None:
        """Expand or collapse the hotkeys info panel."""
        if self._hotkeys_visible.get():
            self._hotkeys_frame.pack_forget()
            self._hotkeys_toggle_btn.config(text="▶ Hotkeys")
            self._hotkeys_visible.set(False)
        else:
            self._hotkeys_frame.pack(fill="x", padx=PADDING_OUTER, pady=(0, 4))
            self._hotkeys_toggle_btn.config(text="▼ Hotkeys")
            self._hotkeys_visible.set(True)

    # ------------------------------------------------------------------
    # Combobox theming
    # ------------------------------------------------------------------

    def _style_combobox(self) -> None:
        """Apply dark theme styles to ttk.Combobox widgets."""
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_BUTTON,
            foreground=FG_PRIMARY,
            selectbackground=BG_SECTION,
            selectforeground=FG_PRIMARY,
            bordercolor=BORDER_COLOR,
            arrowcolor=FG_SECONDARY,
        )

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        """Handle the close button — stop any active recording first."""
        if self.recorder.status.state in (RecorderState.RECORDING, RecorderState.PAUSED):
            if not messagebox.askyesno(
                "Stop recording?",
                "A recording is in progress. Stop and exit?",
            ):
                return
            self.recorder.stop()

        self._hotkeys.unregister()
        self.root.after(200, self.root.destroy)
