# ScreenRec

A lightweight screen recorder for Windows 10, built in Python. Designed specifically for low-powered machines where OBS Studio causes lag during gameplay. ScreenRec captures your screen using `mss` (zero GPU overhead) and encodes via FFmpeg, using Intel Quick Sync Video (h264_qsv) when available or falling back to `libx264 ultrafast` automatically. Output is crash-safe (recorded to MKV first, then remuxed to MP4 on stop). The UI is a small always-on-top floating window that stays out of your way.

---



---

## FFmpeg Setup

FFmpeg is not bundled with ScreenRec. You must download and place it manually.

**Step 1 — Download**

Go to: https://ffmpeg.org/download.html

Click **Windows builds by BtbN** (or gyan.dev) and download the **ffmpeg-release-essentials** zip (e.g. `ffmpeg-6.1.1-essentials_build.zip`).

**Step 2 — Extract**

Unzip the archive. Inside you will find a `bin\` folder containing `ffmpeg.exe`, `ffplay.exe`, and `ffprobe.exe`.

**Step 3 — Place ffmpeg.exe**

Copy **only** `ffmpeg.exe` into the same folder as `main.py` (or `ScreenRec.exe` if using the built executable).

Alternatively, add the `bin\` folder to your system PATH:
1. Open Start → search "Environment Variables"
2. Under System Variables, select **Path** → Edit → New
3. Paste the full path to the `bin\` folder (e.g. `C:\tools\ffmpeg\bin`)
4. Click OK and restart any open terminals

ScreenRec will automatically find `ffmpeg.exe` in either location.

---

## Installation

```bat
pip install -r requirements.txt
```

> **Note:** `pyaudio` may require a pre-built wheel on some systems.  
> If `pip install pyaudio` fails, try:  
> `pip install pipwin && pipwin install pyaudio`

---

## Running the App

```bat
python main.py
```

On first launch, ScreenRec will:
1. Verify that `ffmpeg.exe` is accessible (exits with a dialog if not found)
2. Probe for Intel Quick Sync availability
3. Open the floating recorder window

---

## System Audio Recording

ScreenRec captures system audio via **WASAPI loopback** (the same method used by professional screen recorders). This requires the **Stereo Mix** device to be enabled in Windows.

**To enable Stereo Mix:**
1. Right-click the speaker icon in the taskbar → **Sounds**
2. Go to the **Recording** tab
3. Right-click anywhere → **Show Disabled Devices**
4. Right-click **Stereo Mix** → **Enable**
5. Click OK

**If Stereo Mix is not available** on your audio hardware (common on laptops with Realtek codecs that have disabled it), install **VB-Audio Virtual Cable** as a free alternative:

- Download: https://vb-audio.com/Cable/
- After install, set your default playback device to "CABLE Input" in Windows Sound settings
- ScreenRec will detect the Virtual Cable automatically

---

## Hotkeys

| Key | Action |
|---|---|
| **F9** | Start / Stop recording |
| **F10** | Pause / Resume recording |
| **F11** | Save a PNG screenshot of the selected monitor |

Hotkeys work globally — even when Unity or another app is in fullscreen mode.

---

## Quality Presets

| Preset | Resolution | FPS | Notes |
|---|---|---|---|
| Light | 720p | 24 | Default — minimum CPU/disk impact |
| Balanced | 720p | 30 | Recommended for most sessions |
| High | 1080p | 30 | May cause stutter on very low-end hardware |

---

## Building the .exe

To produce a portable single-file executable that requires no Python installation:

1. Make sure `ffmpeg.exe` is in the project folder.
2. Optionally place an `icon.ico` in the project folder (the build script references it).
3. Run:

```bat
build.bat
```

The output will be at `dist\ScreenRec.exe`. Copy it along with `ffmpeg.exe` to any Windows 10 machine — no installer needed.

> If you do not have an `icon.ico`, edit `build.bat` and remove the `--icon=icon.ico` line before running.

---

## Troubleshooting

### "FFmpeg not found" dialog at startup
- Confirm `ffmpeg.exe` is in the same folder as `main.py` / `ScreenRec.exe`, or is on your PATH.
- Open a command prompt and type `ffmpeg -version` to verify PATH detection.

### QSV not detected — using x264 fallback
- Intel Quick Sync requires a 4th-generation (Haswell) or newer Intel CPU.
- Ensure Intel graphics drivers are up to date (download from https://www.intel.com/content/www/us/en/support/detect.html).
- If you are running in a VM, QSV passthrough is usually not supported; x264 fallback will be used automatically.

### No system audio recorded
- Follow the Stereo Mix setup instructions above.
- Check that Stereo Mix is not muted in the Windows Volume Mixer.
- As an alternative, install VB-Audio Virtual Cable (see above).

### Black frames / no video in output
- Confirm the correct monitor is selected in the dropdown.
- Try the "↺ Refresh" button to re-detect monitors after a display change.
- Some fullscreen exclusive (non-borderless) games cannot be captured by mss. Switch Unity to **Windowed** or **Borderless Windowed** mode in its display settings.

### Recording failed / FFmpeg crashed mid-recording
- Check `screenrec.log` in the app folder for detailed FFmpeg error output.
- If QSV fails mid-encode, restart the app — ScreenRec will re-probe and fall back to x264 automatically.
- The partial `.mkv` file is preserved in your output folder when FFmpeg crashes — you may be able to open it in VLC.

### "OSError" or write errors during recording
- This usually means the output folder became unavailable (e.g. a USB drive was removed).
- Set the output folder to a local drive (e.g. `C:\Users\<you>\Videos\ScreenRec\`) for reliability.

---

## Project Structure

```
screenrec/
├── main.py              # Entry point — startup checks, launches UI
├── recorder.py          # Recording thread, FFmpeg process management
├── capture.py           # mss screen capture loop
├── audio.py             # Audio device detection, WASAPI loopback setup
├── hotkeys.py           # Global hotkey registration and handling
├── ui/
│   ├── app_window.py    # Main tkinter window, layout, all widgets
│   └── styles.py        # Color constants, font sizes, widget style config
├── utils.py             # Filename generator, folder creator, timer formatter
├── ffmpeg_probe.py      # FFmpeg presence check, QSV availability probe
├── requirements.txt
├── README.md
└── build.bat            # PyInstaller build script
```

---

## License

MIT — free to use, modify, and distribute.
