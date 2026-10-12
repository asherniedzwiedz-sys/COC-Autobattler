"""
Every tunable for the bot lives in this file. Edit values here; nothing else
should need changing for normal use.

Screen positions are resolution independent: buttons and icons are found by
template matching against small PNG crops you capture from your own device
(see templates/README.md), and text regions are defined relative to the
screen size or to a matched icon (see REGIONS below).
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Base targeting (used by the attack phase, built after you approve the army)
# ---------------------------------------------------------------------------
LOOT_MIN = 2_000_000          # attack only if gold + elixir in the base preview is at least this
LOOT_MAX = None               # optional upper limit (e.g. 2_000_000); None = no maximum
MAX_NEXTS = 40                # "Next" presses per search before ending the session

# A base qualifies only when ALL of these hold (see cocbot/search.py):
#   loot: gold + elixir >= LOOT_MIN (and <= LOOT_MAX if set), read the same LOOT_CONFIRM_READS times in a row
#   dead: at least MIN_FULL_COLLECTORS full collectors/mines/drills visible (templates/full_collector*.png)
#   winnable: its Town Hall sits in the open (no wall within EXPOSED_TH_RADIUS), or its Town Hall
#             level is at most MAX_TARGET_TH (templates/enemy_th<N>.png) and it shows at most
#             MAX_AIR_DEFENSES Air Defenses (templates/air_defense*.png)
LOOT_CONFIRM_READS = 2
MIN_FULL_COLLECTORS = 3
MAX_TARGET_TH = 17
MAX_AIR_DEFENSES = 4
EXPOSED_TH_RADIUS = 2.5       # in Town Hall widths
SAVE_SEARCH_SCREENSHOTS = True  # keep each base looked at in logs/searches/ (for cutting templates)

# The approved army (Phase 1 proposal, approved by you). Slot templates are
# templates/slot_<name>.png, cut from the troop bar at the bottom of a battle.
APPROVED_ARMY = {
    "troops": {"dragon": 17},
    "spells": {"lightning": 11},
    "siege": "battle_blimp",      # carries the Clan Castle troops to the core
    "heroes": ("royal_champion", "grand_warden", "minion_prince", "dragon_duke"),
}

# ---------------------------------------------------------------------------
# Attack plan: zap Air Defenses, then a line of dragons with heroes behind
# ---------------------------------------------------------------------------
LIGHTNING_PER_AD = 4          # lightning spells dropped on each Air Defense
# The battle map is a diamond. Its centre and half-width/half-height, in screen
# heights from the screen centre (the map scales with screen height). Check with
# `python -m cocbot calibrate` on a search screen: the cyan diamond should trace
# the outer edge of the deployable grass.
MAP_CENTER = (0.0, -0.01)
MAP_HALF_SIZE = (0.66, 0.49)
DEPLOY_OUTSET = 0.015         # deploy this far outside the diamond (screen heights)
DEPLOY_EDGE_SPAN = (0.15, 0.85)  # spread units along this part of an edge
TROOP_BAR_TOP = 0.82          # never deploy below this height (fraction of screen): the troop bar
DEFAULT_SIDE = "top_left"     # used when the enemy Town Hall isn't found
DEPLOY_TAP_DELAY = 0.12       # seconds between deploy taps
ZAP_DELAY = 1.0               # seconds after each Air Defense's lightning before the next step
HERO_DELAY = 3.0              # seconds after the dragons before the siege and heroes go in
ABILITY_TIMES = {             # seconds after deployment to fire each hero's ability
    "grand_warden": 10, "royal_champion": 14, "minion_prince": 14, "dragon_duke": 14,
}
BATTLE_TIMEOUT = 200          # seconds to wait for the battle to end before surrendering
ARMY_READY_TIMEOUT = 600      # seconds to wait for the army to be full before ending the session
ARMY_CHECK_INTERVAL = 30

# ---------------------------------------------------------------------------
# Storages, walls and suggested upgrades
# ---------------------------------------------------------------------------
STORAGE_THRESHOLD = 0.95      # storage at/above this fraction of max counts as full
MAX_WALL_UPGRADES_PER_ROUND = 10       # hard cap per check, guards against OCR loops
MAX_SUGGESTED_UPGRADES_PER_ROUND = 6   # hard cap per check
WALLS_NEED_FREE_BUILDER = True         # the game wants an idle builder even for instant wall upgrades
WALLS_MAXED = None            # None = detect from the builder menu; True/False to force
BUILDER_MENU_SCROLLS = 4      # swipes through the builder menu when looking for walls
SUGGESTED_SKIP_WORDS = ()     # e.g. ("King", "Queen") to never start those suggested upgrades
MENU_HEADER_WORDS = ("suggested", "upgrades", "other", "builder", "builders", "apprentice")
# Your total storage capacities (e.g. "gold": 28_000_000). With these set, fullness is
# amount / capacity (exact). Left as None, fullness is measured from the storage bar (about +/-2%).
STORAGE_MAX = {"gold": None, "elixir": None, "dark": None}
# Storage bars fill from the right, under the icon. Each bar's left and right ends,
# measured from the centre of its home_*_icon match in screen heights (the game's
# UI scales with screen height), and how far below that centre the sampled row is.
# Measured on a TH18 screenshot; check with calibrate.
BAR_SPAN = {"gold": (-0.258, 0.037), "elixir": (-0.263, 0.032), "dark": (-0.187, 0.032)}
BAR_ROW = 0.015
BAR_SCAN_FROM = 0.033         # start reading the fill this far left of the icon centre (past the icon's rim)

# ---------------------------------------------------------------------------
# Donations
# ---------------------------------------------------------------------------
AUTO_DONATE = False           # default only; the startup prompt sets it on every run
# Elixir and dark elixir troops the bot may donate, in priority order. Each one
# needs templates/donate_<name>.png. Spells and siege machines are never donated.
DONATE_TROOPS = (
    "dragon", "electro_dragon", "balloon", "wizard", "baby_dragon", "pekka",
    "yeti", "dragon_rider", "electro_titan", "root_rider", "miner", "giant",
    "archer", "barbarian", "goblin", "wall_breaker", "healer",
    "lava_hound", "golem", "ice_golem", "hog_rider", "valkyrie", "bowler",
    "witch", "headhunter", "minion", "apprentice_warden", "druid",
)
DONATE_MAX_REQUESTS_PER_ROUND = 5
DONATE_MAX_TAPS_PER_REQUEST = 8
DONATE_SLOT_PAD = 1.2         # how far around a troop icon (in icon sizes) to look for a gem price

# ---------------------------------------------------------------------------
# Gem guard: the bot must never spend gems
# ---------------------------------------------------------------------------
GEM_MATCH_THRESHOLD = 0.72    # lower = more paranoid (more false "gem found" aborts)
# Area around a price icon treated as "the same button" (multiples of the icon size,
# same form as "icon" regions). A gem icon in here blocks the tap.
PRICE_BUTTON_SPAN = (-3.0, -1.5, 4.0, 2.5)
MAX_GEM_BLOCKS = 3            # end the session after this many blocked gem paths
CHECK_FOREGROUND = True       # refuse to tap unless Clash of Clans is the focused app
GAME_PACKAGE_ANDROID = "com.supercell.clashofclans"
GAME_BUNDLE_IOS = "com.supercell.magic"

# ---------------------------------------------------------------------------
# Run mode
# ---------------------------------------------------------------------------
DRY_RUN = True                # True = only log taps. `python -m cocbot run --live` overrides.

# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------
DEVICE = "android"            # "android" (phone or emulator via ADB) or "ios" (experimental)
ADB_PATH = None               # None = `adb` on PATH, e.g. r"C:\platform-tools\adb.exe"
ADB_SERIAL = None             # None = the only connected device; else a serial from `adb devices`
                              # or an address like "127.0.0.1:5555" (connected automatically)
EMULATOR = None               # None = find it automatically; or a key of EMULATOR_ADB_ADDRESSES
EMULATOR_ADB_ADDRESSES = {    # first instance of each emulator; check its settings if it differs
    "bluestacks": "127.0.0.1:5555",
    "ldplayer": "emulator-5554",
    "memu": "127.0.0.1:21503",
    "nox": "127.0.0.1:62001",
    "mumu": "127.0.0.1:16384",
    "android_studio": "emulator-5554",
}
# With nothing set above and no device plugged in, the bot tries these addresses
# (BlueStacks instances, MEmu, Nox, MuMu) and uses the first emulator that answers.
EMULATOR_AUTO_ADDRESSES = (
    "127.0.0.1:5555", "127.0.0.1:5565", "127.0.0.1:5575", "127.0.0.1:5585",
    "127.0.0.1:21503", "127.0.0.1:62001", "127.0.0.1:16384", "127.0.0.1:7555",
)
WDA_URL = "http://localhost:8100"   # iPhone: WebDriverAgent address
IOS_SCREENSHOT_ROTATION = 0         # iPhone: 0/90/180/270 if screenshots come out sideways

# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
TAP_SETTLE = 0.8              # seconds to wait after a tap for the UI to react
SWIPE_SETTLE = 0.6
WAIT_TIMEOUT = 6.0            # seconds to wait for an expected button/window
SCREENSHOT_RETRIES = 3

# ---------------------------------------------------------------------------
# Vision and OCR
# ---------------------------------------------------------------------------
TEMPLATE_DIR = PROJECT_ROOT / "templates"
MATCH_THRESHOLD = 0.85        # template match score needed to count as found
TEMPLATE_SCALES = (1.0,)      # add e.g. 0.9, 1.1 if templates came from another resolution
TESSERACT_CMD = None          # None = `tesseract` on PATH, e.g. r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OCR_UPSCALE = 3
OCR_TEXT_MIN_VALUE = 190      # game text is white with a dark outline: min brightness (0-255)
OCR_TEXT_MAX_SATURATION = 80  # ...and low saturation
DIGIT_MATCH_THRESHOLD = 0.80  # glyph similarity needed to accept a digit (templates/digits/)

# Text regions. Two forms:
#   ("screen", x1, y1, x2, y2)           fractions of screen width/height (0..1)
#   ("icon", template, dx1, dy1, dx2, dy2) relative to where `template` is found, in
#                                        multiples of its width (dx) and height (dy):
#                                        (0, 0) is its top-left corner, (1, 1) its bottom-right.
# These are first guesses. Check them with `python -m cocbot calibrate`.
REGIONS = {
    "home_gold_amount":    ("icon", "home_gold_icon",   -4.2, 0.10, -0.05, 0.90),
    "home_elixir_amount":  ("icon", "home_elixir_icon", -4.2, 0.10, -0.05, 0.90),
    "home_dark_amount":    ("icon", "home_dark_icon",   -4.2, 0.10, -0.05, 0.90),
    "builders_count":      ("icon", "builder_icon",      1.40, 0.00, 3.20, 1.00),
    "builder_menu":        ("icon", "builder_icon",     -3.00, 1.00, 9.00, 11.0),
    "selected_name":       ("screen", 0.25, 0.66, 0.75, 0.79),  # "Town Hall (Level 18)"
    "selected_buttons":    ("screen", 0.10, 0.78, 0.90, 1.00),  # buttons under a selected building
    "upgrade_confirm":     ("screen", 0.25, 0.55, 0.98, 0.97),  # price button in the upgrade window
    "popup_center":        ("screen", 0.25, 0.20, 0.75, 0.75),  # where gem offers pop up
    "loot_gold_amount":    ("icon", "loot_gold_icon",    1.10, 0.05, 6.50, 0.95),  # search: "Available Loot"
    "loot_elixir_amount":  ("icon", "loot_elixir_icon",  1.10, 0.05, 6.50, 0.95),
    "loot_dark_amount":    ("icon", "loot_dark_icon",    1.10, 0.05, 6.50, 0.95),
    "army_troops_count":   ("icon", "army_troops_icon",  1.05, 0.00, 6.00, 1.00),  # "340/340"
    "army_spells_count":   ("icon", "army_spells_icon",  1.05, 0.00, 5.00, 1.00),  # "11/11"
    "result_trophies":     ("icon", "result_trophy_icon", -4.0, 0.00, -0.05, 1.00),
    "chat_panel":          ("screen", 0.00, 0.08, 0.45, 1.00),
    "donate_window":       ("screen", 0.20, 0.05, 1.00, 0.97),
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = "cocbot.log"
EVENT_FILE = "events.jsonl"   # one JSON object per attack/upgrade/donation/stop
SCREENSHOT_ON_STOP = True     # save the screen to logs/ whenever the bot stops
SCAN_DIR = PROJECT_ROOT / "scans"
