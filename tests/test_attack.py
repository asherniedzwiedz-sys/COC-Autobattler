"""Phase 2: base targeting rules, deploy geometry, the attack plan and the search/attack/army flows."""
import math

import cv2
import pytest

from cocbot import config
from cocbot.army import Army, is_full
from cocbot.attack import Attacker, EDGES, build_plan, choose_side, edge_points, map_corners, parse_signed
from cocbot.bot import Bot
from cocbot.errors import DryRunStop, StopBot
from cocbot.farmer import loot_gained
from cocbot.search import BaseInfo, Searcher, evaluate, th_level_of
from cocbot.state import HomeState, Storage
from cocbot.vision import Box, Match, Vision
from tests.conftest import GAME, H, W, TapDevice, draw_text, make_icon, make_screen, paste

needs_tesseract = pytest.mark.skipif(not __import__("cocbot.ocr", fromlist=["available"]).available(),
                                     reason="tesseract not installed")


def qualifying(**changes):
    info = BaseInfo(gold=1_050_000, elixir=1_000_000, dark=8_000, full_collectors=5,
                    air_defenses=[Box(600, 300, 40, 40)] * 3, th_level=16)
    for k, v in changes.items():
        setattr(info, k, v)
    return info


# --- targeting rules -----------------------------------------------------------------

def test_qualifying_base():
    assert evaluate(qualifying()) == (True, [])


@pytest.mark.parametrize("changes,reason", [
    ({"gold": 500_000}, "below"),
    ({"elixir": None}, "unreadable"),
    ({"full_collectors": 1}, "not a dead base"),
    ({"th_level": 18}, "above TH17"),
    ({"th_level": None}, "unknown"),
    ({"air_defenses": [Box(0, 0, 9, 9)] * 6}, "air defenses"),
])
def test_base_rejected(changes, reason):
    ok, reasons = evaluate(qualifying(**changes))
    assert not ok and any(reason in r for r in reasons)


def test_th_in_the_open_is_winnable_regardless_of_level():
    assert evaluate(qualifying(th_level=None, th_exposed=True, air_defenses=[Box(0, 0, 9, 9)] * 6))[0]


def test_loot_minimum_is_inclusive_and_there_is_no_maximum():
    assert evaluate(qualifying(gold=1_000_000, elixir=1_000_000))[0]      # exactly 2.0M
    assert not evaluate(qualifying(gold=1_000_000, elixir=999_999))[0]    # just under
    assert evaluate(qualifying(gold=3_000_000, elixir=2_500_000))[0]      # 5.5M: no upper limit


def test_optional_loot_maximum(monkeypatch):
    monkeypatch.setattr(config, "LOOT_MAX", 2_500_000)
    assert evaluate(qualifying(gold=1_500_000, elixir=1_000_000))[0]      # exactly 2.5M
    ok, reasons = evaluate(qualifying(gold=1_700_000, elixir=1_000_000))
    assert not ok and "above" in reasons[0]


def test_th_level_from_template_name():
    assert th_level_of("enemy_th17") == 17 and th_level_of("enemy_wall") is None


# --- deploy geometry and plan -----------------------------------------------------------

def test_edge_points_outside_map_and_above_troop_bar():
    corners = map_corners(W, H)
    cx, cy = (corners["left"][0] + corners["right"][0]) / 2, (corners["top"][1] + corners["bottom"][1]) / 2
    hw, hh = corners["right"][0] - cx, corners["bottom"][1] - cy
    for edge in EDGES:
        for x, y in edge_points(W, H, edge, 17):
            assert abs(x - cx) / hw + abs(y - cy) / hh >= 1.0 - 1e-6 or x in (0, W - 1) or y in (0, H - 1)
            assert y < config.TROOP_BAR_TOP * H


def test_top_edges_fit_all_dragons():
    assert len(edge_points(W, H, "top_left", 17)) == 17
    assert len(edge_points(W, H, "top_right", 17)) == 17


def test_side_nearest_town_hall():
    assert choose_side(W, H, Box(1000, 120, 40, 40)) == "top_right"
    assert choose_side(W, H, Box(200, 150, 40, 40)) == "top_left"
    assert choose_side(W, H, None) == config.DEFAULT_SIDE


def test_plan_zaps_nearest_air_defenses_then_dragons_then_blimp_and_heroes():
    ads = [Box(300, 200, 40, 40), Box(900, 500, 40, 40), Box(350, 260, 40, 40)]
    base = qualifying(air_defenses=ads, town_hall=Match("enemy_th16", Box(250, 150, 40, 40), 0.9))
    slots = {"dragon", "lightning", "battle_blimp", "royal_champion", "grand_warden", "minion_prince", "dragon_duke"}
    side, steps = build_plan(W, H, base, slots)
    assert side == "top_left"
    zaps = [s for s in steps if s.slot == "lightning"]
    assert len(zaps) == 11 // config.LIGHTNING_PER_AD == 2
    assert {s.points[0] for s in zaps} == {ads[0].center, ads[2].center}  # the two near the attack side
    assert all(len(s.points) == config.LIGHTNING_PER_AD for s in zaps)
    dragons = next(s for s in steps if s.slot == "dragon")
    assert len(dragons.points) == 17 and dragons.wait_after == config.HERO_DELAY
    assert [s.slot for s in steps][-5:] == ["battle_blimp", "royal_champion", "grand_warden", "minion_prince", "dragon_duke"]


def test_every_dragon_deploys_even_from_a_bottom_edge():
    town_hall_low = Match("enemy_th16", Box(300, 520, 40, 40), 0.9)
    side, steps = build_plan(W, H, qualifying(town_hall=town_hall_low, air_defenses=[]), {"dragon"})
    assert side.startswith("bottom")
    assert len(edge_points(W, H, side, 17)) < 17
    assert len(steps[0].points) == 17
    assert all(y < config.TROOP_BAR_TOP * H for _, y in steps[0].points)


def test_plan_skips_slots_not_in_the_troop_bar():
    _, steps = build_plan(W, H, qualifying(), {"dragon"})
    assert [s.slot for s in steps] == ["dragon"]


@pytest.mark.parametrize("text,value", [("+12", 12), ("-8", -8), ("15", 15), ("", None)])
def test_parse_signed(text, value):
    assert parse_signed(text) == value


def test_loot_gained():
    before = HomeState(Storage(1_000_000), Storage(2_000_000), Storage(None))
    after = HomeState(Storage(1_900_000), Storage(2_850_000), Storage(5_000))
    assert loot_gained(before, after) == {"gold": 900_000, "elixir": 850_000, "dark": None}
    assert loot_gained(None, after) == {"gold": None, "elixir": None, "dark": None}


def test_army_full():
    assert is_full((340, 340)) and not is_full((300, 340)) and not is_full(None)


# --- flows on synthetic screens ------------------------------------------------------------

def _templates(template_dir, names):
    icons = {}
    for name in names:
        icons[name] = make_icon(f"troop_{name}", 36)
        cv2.imwrite(str(template_dir / f"{name}.png"), icons[name])
    return icons


def _search_screen(icons, gold, elixir, collectors, th="enemy_th16"):
    screen = make_screen()
    paste(screen, icons["btn_next"], 1150, 600)
    paste(screen, icons["btn_end_battle"], 60, 600)
    for i, (res, amount) in enumerate((("gold", gold), ("elixir", elixir))):
        paste(screen, icons[f"loot_{res}_icon"], 40, 60 + i * 50)
        draw_text(screen, amount, 86, 88 + i * 50)
    for i in range(collectors):
        paste(screen, icons["full_collector"], 400 + i * 60, 400)
    paste(screen, icons["air_defense"], 600, 250)
    paste(screen, icons[th], 640, 330)
    return screen


SEARCH_NAMES = ["btn_attack", "btn_find_match", "btn_next", "btn_end_battle", "loot_gold_icon",
                "loot_elixir_icon", "full_collector", "air_defense", "enemy_th16"]


@needs_tesseract
def test_search_skips_until_a_base_qualifies(template_dir, events, monkeypatch):
    icons = _templates(template_dir, SEARCH_NAMES)
    monkeypatch.setattr(Bot, "wait_gone", lambda self, name, timeout=5.0: True)
    home = paste(make_screen(), icons["btn_attack"], 60, 600)
    menu = paste(make_screen(), icons["btn_find_match"], 600, 400)
    poor = _search_screen(icons, "300000", "200000", collectors=5)
    rich = _search_screen(icons, "1050000", "1000000", collectors=4)
    device = TapDevice(home, menu, poor, rich)
    bot = Bot(device, Vision(template_dir), events, dry_run=False, auto_donate=False)
    info = Searcher(bot).find_base()
    assert (info.gold, info.elixir, info.th_level, info.full_collectors, info.nexts) == (1_050_000, 1_000_000, 16, 4, 1)
    assert device.taps == [(78, 618), (618, 418), (1168, 618)]  # Attack!, Find a Match, Next


@needs_tesseract
def test_search_gives_up_after_max_nexts(template_dir, events, monkeypatch):
    icons = _templates(template_dir, SEARCH_NAMES + ["builder_icon"])
    monkeypatch.setattr(Bot, "wait_gone", lambda self, name, timeout=5.0: True)
    monkeypatch.setattr(config, "MAX_NEXTS", 2)
    home = paste(make_screen(), icons["btn_attack"], 60, 600)
    menu = paste(make_screen(), icons["btn_find_match"], 600, 400)
    poor = _search_screen(icons, "300000", "200000", collectors=5)
    back_home = paste(make_screen(), icons["builder_icon"], 600, 10)
    device = TapDevice(home, menu, poor, poor, poor, back_home)
    bot = Bot(device, Vision(template_dir), events, dry_run=False, auto_donate=False)
    assert Searcher(bot).find_base() is None
    assert device.taps[-1] == (78, 618)  # End Battle: home without deploying
    assert len(device.taps) == 2 + 2 + 1  # menu, 2 Nexts, End Battle


SLOT_NAMES = ["slot_dragon", "slot_lightning", "slot_battle_blimp", "slot_royal_champion",
              "slot_grand_warden", "slot_minion_prince", "slot_dragon_duke", "btn_return_home", "builder_icon"]


def _battle(template_dir, monkeypatch, dry_run=False):
    icons = _templates(template_dir, SLOT_NAMES)
    monkeypatch.setattr(config, "ABILITY_TIMES", {h: 999 for h in config.APPROVED_ARMY["heroes"]})
    battle = make_screen()
    for i, name in enumerate(SLOT_NAMES[:7]):
        paste(battle, icons[name], 100 + i * 60, 640)
    results = paste(make_screen(), icons["btn_return_home"], 600, 600)
    home = paste(make_screen(), icons["builder_icon"], 600, 10)
    base = qualifying(air_defenses=[Box(300, 200, 40, 40), Box(350, 260, 40, 40)],
                      town_hall=Match("enemy_th16", Box(250, 150, 40, 40), 0.9))
    # select + taps per step: 2 zaps (1+4 each), dragons (1+17), blimp and 4 heroes (1+1 each)
    deploy_taps = 2 * 5 + 18 + 5 * 2
    device = TapDevice(*([battle] * deploy_taps), results, home)
    return device, base


def test_attack_dry_run_logs_the_whole_plan_and_taps_nothing(template_dir, events, monkeypatch):
    device, base = _battle(template_dir, monkeypatch)
    bot = Bot(device, Vision(template_dir), events, dry_run=True, auto_donate=False)
    with pytest.raises(DryRunStop):
        Attacker(bot).attack(base)
    assert device.taps == []
    logged = events.path.read_text()
    assert "17 dragons" in logged and "lightning on the Air Defense" in logged and "dragon_duke" in logged


def test_attack_live_deploys_everything_then_returns_home(template_dir, events, monkeypatch):
    device, base = _battle(template_dir, monkeypatch)
    bot = Bot(device, Vision(template_dir), events, dry_run=False, auto_donate=False)
    result = Attacker(bot).attack(base)
    assert result["side"] == "top_left" and result["air_defenses_zapped"] == 2
    assert len(device.taps) == 2 * 5 + 18 + 5 * 2 + 1  # every deploy, then Return Home
    assert device.taps[-1] == (618, 618)
    dragon_slot = (100 + 0 * 60 + 18, 658)
    assert device.taps[10] == dragon_slot


@needs_tesseract
def test_army_ready_check(template_dir, events, monkeypatch):
    icons = _templates(template_dir, ["btn_army", "army_troops_icon", "army_spells_icon"])
    cv2.imwrite(str(template_dir / "btn_close.png"), make_icon("close"))
    home = paste(make_screen(), icons["btn_army"], 60, 500)

    def window(troops, spells):
        screen = paste(make_screen(), make_icon("close"), 1200, 30)
        paste(screen, icons["army_troops_icon"], 300, 150)
        draw_text(screen, troops, 346, 178)
        paste(screen, icons["army_spells_icon"], 300, 300)
        draw_text(screen, spells, 346, 328)
        return screen

    bot = Bot(TapDevice(home, window("340/340", "11/11"), home), Vision(template_dir), events,
              dry_run=False, auto_donate=False)
    Army(bot).ensure_ready()
    assert bot.device.taps == [(78, 518), (1218, 48)]  # open the Army window, close it

    monkeypatch.setattr(config, "ARMY_READY_TIMEOUT", 0)
    bot = Bot(TapDevice(home, window("300/340", "11/11"), home), Vision(template_dir), events,
              dry_run=False, auto_donate=False)
    with pytest.raises(StopBot, match="not full"):
        Army(bot).ensure_ready()
