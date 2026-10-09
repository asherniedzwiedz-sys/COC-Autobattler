"""Storages, upgrades, donations and the main loop."""
import json

import cv2
import pytest

from cocbot import config, ocr
from cocbot.cli import ask_yes_no, cmd_crop
from cocbot.device import parse_focused_window
from cocbot.donate import Donator, donate_troops
from cocbot.errors import DryRunStop, FlowError
from cocbot.farmer import Farmer
from cocbot.ocr import Word
from cocbot.state import HomeState, Storage, checked_storage, farming_stop_reason, read_home_state, storages_to_spend
from cocbot.upgrades import Upgrader, is_wall_row, pick_suggested_row, row_name, spent_amount
from cocbot.vision import Box, Vision
from tests.conftest import draw_text, make_icon, make_screen, paste

needs_tesseract = pytest.mark.skipif(not ocr.available(), reason="tesseract not installed")

FULL = Storage(9_600_000, 10_000_000)
HALF = Storage(5_000_000, 10_000_000)


def state(gold=HALF, elixir=HALF, dark=HALF, free=1, total=6):
    return HomeState(gold, elixir, dark, builders_free=free, builders_total=total)


# --- storages and decisions ------------------------------------------------------

def test_storage_fraction():
    assert FULL.fraction == pytest.approx(0.96)
    assert FULL.is_full(0.95) and not HALF.is_full(0.95)
    assert not Storage(None, 10).is_full(0.95) and not Storage(5, None).is_full(0.95)


def test_storage_max_override(template_dir, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_MAX", {"gold": 12_000_000, "elixir": None, "dark": None})
    from cocbot.state import read_storage
    icon = make_icon("troop_home_gold", 40)
    cv2.imwrite(str(template_dir / "home_gold_icon.png"), icon)
    screen = paste(make_screen(), icon, 1200, 60)
    assert read_storage(screen, Vision(template_dir), "gold") == Storage(None, 12_000_000, None)
    assert read_storage(make_screen(), Vision(template_dir), "gold") == Storage()


def test_misread_storage_is_ignored():
    assert checked_storage(95_000_000, 10_000_000).current is None
    assert checked_storage(9_000_000, 10_000_000).current == 9_000_000


def test_storages_to_spend_only_gold_and_elixir():
    assert storages_to_spend(state(gold=FULL, dark=FULL)) == ["gold"]
    assert storages_to_spend(state()) == []


def test_stop_only_when_builders_busy_and_everything_full():
    assert farming_stop_reason(state(FULL, FULL, FULL, free=0)) is not None
    assert farming_stop_reason(state(FULL, FULL, FULL, free=1)) is None
    assert farming_stop_reason(state(FULL, FULL, HALF, free=0)) is None
    assert farming_stop_reason(state(FULL, FULL, Storage(None, None), free=0)) is None


@needs_tesseract
def test_read_home_state_from_screen(template_dir, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_MAX", {"gold": 10_000_000, "elixir": 10_000_000, "dark": 350_000})
    screen = make_screen()
    for i, (res, amount) in enumerate([("gold", "9500000"), ("elixir", "4200000"), ("dark", "180000")]):
        icon = make_icon(f"troop_home_{res}", 40)
        cv2.imwrite(str(template_dir / f"home_{res}_icon.png"), icon)
        y = 60 + i * 80
        paste(screen, icon, 1200, y)
        draw_text(screen, amount, 1040, y + 30)
    paste(screen, make_icon("builder"), 600, 10)
    draw_text(screen, "2/6", 655, 36)
    home = read_home_state(screen, Vision(template_dir))
    assert (home.gold.current, home.elixir.current, home.dark.current) == (9_500_000, 4_200_000, 180_000)
    assert (home.builders_free, home.builders_total) == (2, 6)
    assert storages_to_spend(home) == ["gold"]


def _bar_screen(fraction, resource="gold", height=1206):
    """A storage bar laid out like the game's: it fills from the right, under the icon."""
    import numpy as np
    from cocbot.state import FILL_HSV
    screen = np.full((height, 2622, 3), (40, 60, 30), np.uint8)
    cx, cy = 2390, 57
    left, right = (cx + d * height for d in config.BAR_SPAN[resource])
    cv2.rectangle(screen, (int(left), cy - 20), (int(right), cy + 25), (60, 60, 60), -1)
    (h1, h2), s, (v1, v2) = FILL_HSV[resource]
    fill = cv2.cvtColor(np.uint8([[[(h1 + h2) // 2, max(s, 200), (v1 + v2) // 2]]]), cv2.COLOR_HSV2BGR)[0, 0]
    fill_left = right - fraction * (right - left)
    cv2.rectangle(screen, (int(fill_left), cy - 20), (int(right), cy + 25), tuple(int(c) for c in fill), -1)
    return screen, Box(cx - 25, cy - 25, 50, 50)


@pytest.mark.parametrize("fraction", [0.39, 0.6, 0.95, 1.0])
def test_bar_fill(fraction):
    from cocbot.state import bar_fill
    screen, icon = _bar_screen(fraction)
    assert bar_fill(screen, icon, "gold") == pytest.approx(fraction, abs=0.02)


def test_bar_fill_hidden_under_icon_reads_low():
    from cocbot.state import bar_fill
    screen, icon = _bar_screen(0.05)
    assert bar_fill(screen, icon, "gold") < 0.5


def _real_home_screen():
    """The real TH18 home screen's HUD (from a user screenshot), placed back on a 2622x1206 canvas."""
    import numpy as np
    from pathlib import Path
    data = Path(__file__).parent / "data"
    screen = np.zeros((1206, 2622, 3), np.uint8)
    screen[20:95, 1200:1420] = cv2.imread(str(data / "home_builders.png"))
    screen[0:300, 2040:2622] = cv2.imread(str(data / "home_storages.png"))
    return screen


def test_real_home_screen_reads_exactly():
    """Regression test on real game graphics with the committed templates and digit glyphs."""
    home = read_home_state(_real_home_screen(), Vision(config.PROJECT_ROOT / "templates"))
    assert (home.gold.current, home.elixir.current, home.dark.current) == (11_012_576, 10_509_457, 67_445)
    assert (home.builders_free, home.builders_total) == (1, 6)
    assert home.gold.fraction == pytest.approx(0.386, abs=0.02)
    assert home.elixir.fraction == pytest.approx(0.374, abs=0.02)


def test_real_home_screen_at_emulator_resolution():
    """Templates cut at 1206 px high still match a 900 px high screen (heights.json scaling)."""
    small = cv2.resize(_real_home_screen(), (1957, 900), interpolation=cv2.INTER_AREA)
    home = read_home_state(small, Vision(config.PROJECT_ROOT / "templates"))
    assert (home.gold.current, home.elixir.current, home.dark.current) == (11_012_576, 10_509_457, 67_445)
    assert (home.builders_free, home.builders_total) == (1, 6)
    assert home.gold.fraction == pytest.approx(0.386, abs=0.03)


# --- upgrades ----------------------------------------------------------------------

def test_wall_rows():
    assert is_wall_row("Wall x24 3,500,000")
    assert is_wall_row("Walls")
    assert not is_wall_row("Wall Wrecker")
    assert not is_wall_row("Archer Tower")


def test_row_name_strips_costs_and_times():
    assert row_name("Archer Tower 6,500,000 5d 12h") == "Archer Tower"


def _line(text, y):
    return [Word(w, Box(10 + i * 60, y, 50, 12), 90) for i, w in enumerate(text.split())]


def test_pick_suggested_row_skips_headers_tried_and_other_section(monkeypatch):
    lines = [_line("Suggested Upgrades", 10), _line("Cannon 4,000,000 3d", 30),
             _line("Barbarian King 120,000 4d", 50), _line("Other Upgrades", 70), _line("Mortar 1d", 90)]
    assert pick_suggested_row(lines, set())[0] == "Cannon"
    assert pick_suggested_row(lines, {"Cannon"})[0] == "Barbarian King"
    monkeypatch.setattr(config, "SUGGESTED_SKIP_WORDS", ("King",))
    assert pick_suggested_row(lines, {"Cannon"}) is None


def test_spent_amount():
    assert spent_amount(10, 4) == 6
    assert spent_amount(None, 4) is None
    assert spent_amount(4, 10) is None


def test_upgrader_does_nothing_below_threshold(make_bot):
    bot, device = make_bot()
    Upgrader(bot).run(state())
    assert device.taps == [] and device.index == 0


def test_upgrader_waits_for_a_free_builder(make_bot):
    bot, device = make_bot()
    Upgrader(bot).run(state(gold=FULL, free=0))
    assert device.taps == []


def test_upgrader_refuses_without_gem_guard(make_bot, tmp_path, events):
    from cocbot.bot import Bot
    from tests.conftest import SequenceDevice
    device = SequenceDevice(make_screen())
    bot = Bot(device, Vision(tmp_path), events, dry_run=False, auto_donate=False)
    with pytest.raises(FlowError):
        Upgrader(bot).run(state(gold=FULL))
    assert device.taps == []


def test_wall_upgrade_dry_run_stops_at_first_tap(make_bot, monkeypatch):
    home = paste(make_screen(), make_icon("builder"), 600, 10)
    bot, device = make_bot(home, dry_run=True)
    monkeypatch.setattr("cocbot.upgrades.read_home_state", lambda screen, vision: state(gold=FULL))
    with pytest.raises(DryRunStop, match="builder menu"):
        Upgrader(bot).run(state(gold=FULL))
    assert device.taps == []


# --- donations ---------------------------------------------------------------------

def test_donations_off_never_touch_the_screen(make_bot):
    bot, device = make_bot(auto_donate=False)
    Donator(bot).run()
    assert device.taps == [] and device.index == 0


def test_donate_skips_troop_with_gem_price(make_bot, monkeypatch, template_dir):
    # Templates are the top/middle of each portrait; the count or gem price sits at the bottom.
    screen = make_screen()
    for troop, x in (("dragon", 500), ("balloon", 700)):
        portrait = make_icon(f"troop_{troop}", 60)
        paste(screen, portrait, x, 300)
        cv2.imwrite(str(template_dir / f"donate_{troop}.png"), portrait[4:40, 12:48])
    paste(screen, make_icon("gem"), 512, 342)  # dragon slot now costs gems
    bot, device = make_bot(screen, auto_donate=True)
    troop, icon = Donator(bot).pick_troop(screen, ("dragon", "balloon"))
    assert troop == "balloon"


def test_donate_fills_request_with_allowed_troop(make_bot, monkeypatch):
    screen = paste(make_screen(), make_icon("troop_balloon"), 700, 300)
    bot, device = make_bot(screen, auto_donate=True)
    monkeypatch.setattr(config, "DONATE_MAX_TAPS_PER_REQUEST", 3)
    taps = Donator(bot).fill_request(("dragon", "balloon"))
    assert taps == {"balloon": 3} and device.taps == [(718, 318)] * 3


def test_donate_list_rejects_spells_and_sieges(monkeypatch):
    monkeypatch.setattr(config, "DONATE_TROOPS", ("dragon", "spell_rage"))
    with pytest.raises(FlowError):
        donate_troops()


# --- main loop and CLI --------------------------------------------------------------

def test_farmer_stops_before_attacking_without_approved_army(make_bot, events):
    bot, device = make_bot()
    reason = Farmer(bot).run()
    assert "approved army" in reason.lower()
    assert device.taps == []
    last = json.loads(events.path.read_text().splitlines()[-1])
    assert last["type"] == "stop" and "approved army" in last["reason"].lower()


def test_farmer_stops_when_builders_busy_and_storages_full(make_bot, monkeypatch, events, template_dir):
    for res in ("gold", "elixir", "dark"):
        cv2.imwrite(str(template_dir / f"home_{res}_icon.png"), make_icon(f"troop_{res}", 40))
    monkeypatch.setattr("cocbot.farmer.read_home_state", lambda screen, vision: state(FULL, FULL, FULL, free=0))
    bot, device = make_bot()
    reason = Farmer(bot).run()
    assert "builders are busy" in reason
    assert device.taps == []


def test_ask_yes_no_repeats_until_valid():
    answers = iter(["maybe", "YES"])
    assert ask_yes_no("? ", lambda prompt: next(answers)) is True
    assert ask_yes_no("? ", lambda prompt: "n") is False


@pytest.mark.parametrize("dumpsys,expected", [
    ("  mCurrentFocus=Window{1a2b3c u0 com.supercell.clashofclans/com.supercell.titan.GameApp}",
     "com.supercell.clashofclans"),
    ("  mCurrentFocus=Window{9f u0 com.android.vending/com.google.android.finsky.billing.BillingActivity}",
     "com.android.vending"),
    ("  mCurrentFocus=Window{77 u0 NotificationShade}", "NotificationShade"),
    ("  mCurrentFocus=null\n  mFocusedApp=ActivityRecord{5 u0 com.supercell.clashofclans/.GameApp t3}",
     "com.supercell.clashofclans"),
    ("nothing useful", None),
])
def test_parse_focused_window(dumpsys, expected):
    assert parse_focused_window(dumpsys) == expected


def test_crop_saves_template_and_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMPLATE_DIR", tmp_path / "templates")
    shot = tmp_path / "shot.png"
    cv2.imwrite(str(shot), make_screen())

    class Args:
        image, name, box, replace = str(shot), "res_gem", "10,20,30,40", False

    assert cmd_crop(Args) == 0 and cmd_crop(Args) == 0
    saved = sorted(p.name for p in (tmp_path / "templates").iterdir())
    assert saved == ["heights.json", "res_gem.png", "res_gem__2.png"]
    heights = json.loads((tmp_path / "templates" / "heights.json").read_text())
    assert heights == {"res_gem.png": 720, "res_gem__2.png": 720}
    assert cv2.imread(str(tmp_path / "templates" / "res_gem.png")).shape == (40, 30, 3)


@needs_tesseract
def test_scan_saves_screens_and_reads_town_hall(vision, tmp_path):
    from cocbot.scan import STEPS, run_scan
    from tests.conftest import SequenceDevice
    home = make_screen()
    town_hall = draw_text(make_screen(), "Town Hall (Level 18)", 450, 530, scale=0.9)
    device = SequenceDevice(home, town_hall, make_screen())
    answers = iter(["", ""] + ["s"] * (len(STEPS) - 2))
    out = run_scan(device, vision, tmp_path, input_fn=lambda prompt: next(answers))
    report = json.loads((out / "report.json").read_text())
    assert report["town_hall_level"] == 18
    assert sorted(p.name for p in out.glob("*.png")) == ["home.png", "town_hall.png"]
    assert device.taps == []
