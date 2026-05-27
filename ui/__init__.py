"""Visual style constants for the ScreenRec tkinter UI.

All colors, fonts, and sizing values live here so the rest of the UI code
never contains raw hex strings or magic numbers.
"""

# ------------------------------------------------------------------
# Color palette
# ------------------------------------------------------------------

BG_MAIN = "#1e1e1e"          # Main window background (dark grey)
BG_HEADER = "#161616"        # Header strip background
BG_SECTION = "#252525"       # Section / card background
BG_INPUT = "#2d2d2d"         # Entry / combobox background
BG_BUTTON = "#2d2d2d"        # Normal button background
BG_RECORD_IDLE = "#c0392b"   # Record button when idle (red)
BG_RECORD_ACTIVE = "#e74c3c" # Record button while recording (brighter red)
BG_HOVER = "#383838"         # Hovered element background

FG_PRIMARY = "#f0f0f0"       # Primary text (near-white)
FG_SECONDARY = "#9e9e9e"     # Muted / secondary text
FG_ACCENT = "#e74c3c"        # Accent / error red
FG_SUCCESS = "#2ecc71"       # Success / ready green
FG_WARNING = "#f39c12"       # Warning orange
FG_RECORD_BTN = "#ffffff"    # Text on record button

BORDER_COLOR = "#3a3a3a"     # Subtle border / separator

# ------------------------------------------------------------------
# Fonts  (family, size, weight)
# ------------------------------------------------------------------

FONT_FAMILY = "Segoe UI"      # Falls back to TkDefaultFont on non-Windows
FONT_MONO   = "Consolas"      # Monospaced (timer, filenames)

FONT_HEADER   = (FONT_FAMILY, 12, "bold")
FONT_LABEL    = (FONT_FAMILY, 9)
FONT_LABEL_SM = (FONT_FAMILY, 8)
FONT_MUTED    = (FONT_FAMILY, 8)
FONT_RECORD   = (FONT_FAMILY, 13, "bold")
FONT_TIMER    = (FONT_MONO, 22, "bold")
FONT_STATUS   = (FONT_FAMILY, 8)
FONT_CLOSE    = (FONT_FAMILY, 11, "bold")

# ------------------------------------------------------------------
# Sizing
# ------------------------------------------------------------------

WINDOW_WIDTH  = 320
WINDOW_HEIGHT = 430
HEADER_HEIGHT = 32
PADDING_OUTER = 10   # Outer frame padding
PADDING_INNER = 6    # Inner widget padding
BUTTON_RADIUS = 4    # Corner radius hint (used in descriptions; tk doesn't support natively)

# ------------------------------------------------------------------
# Encoder badge colours
# ------------------------------------------------------------------

ENCODER_QSV_BG   = "#1a3a2a"
ENCODER_QSV_FG   = "#2ecc71"
ENCODER_X264_BG  = "#2a2a1a"
ENCODER_X264_FG  = "#f39c12"

# ------------------------------------------------------------------
# Separator
# ------------------------------------------------------------------

SEP_COLOR = "#333333"
