"""User settings for the Expedition price checker. Edit freely."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- Hotkeys (key names as understood by the `keyboard` library) ---
SCAN_HOTKEY = "f8"
# Briefly outlines the scan area in red so you can line it up. None disables it.
SHOW_REGION_HOTKEY = "f7"

# --- Screen / scan area ---
# Monitor the game runs on: "middle" (middle of the monitors sorted left to
# right), "primary", or a 0-based index into that left-to-right order.
MONITOR = "middle"
# Scan area in pixels, relative to the game monitor's top-left corner:
# (left, top, right, bottom). Covers the six fully visible reward rows but not
# the half-visible last one. It spans the whole row width because long names
# (e.g. "1x Warding Rune of Reinforcement") run under the rune icons' columns;
# the AI is told to ignore the icons.
SCAN_REGION = (56, 286, 552, 754)

# Save every scanned image (useful while tuning SCAN_REGION).
SAVE_SCREENSHOTS = True
SCREENSHOT_DIR = BASE_DIR / "screenshots"

# --- AI transcription ---
API_KEY_PATH = BASE_DIR.parent / "secrets" / "claude_api_key.txt"
MODEL = "claude-haiku-4-5"
# "Support: Healing Runes" -> "Healing Runes". The full text is still tried
# first, so a manual price entry may use either form.
STRIP_TEXT_BEFORE_COLON = True

# --- Prices ---
LEAGUE = "Forbidden Rites" #"Runes of Aldur"
PRICES_FILE = BASE_DIR / "data" / "prices.json"
MANUAL_PRICES_FILE = BASE_DIR / "manual_prices.txt"
# Rewards worth at least this much (whole stack) get highlighted.
# Units: div / ex / chaos, e.g. "0.5 div" or "100 ex".
HIGHLIGHT_THRESHOLD = "50 ex"
# 0-1 similarity needed to accept a slightly misread name. Names whose numbers
# differ (e.g. "Level 11" vs "Level 12") never fuzzy-match.
FUZZY_MATCH_CUTOFF = 0.85

# --- Popup ---
# Top-left corner of the results popup, relative to the game monitor.
POPUP_POSITION = (1180, 150)
POPUP_SECONDS = 12
# Clicks pass through the popup to the game.
POPUP_CLICK_THROUGH = True
POPUP_OPACITY = 0.93
