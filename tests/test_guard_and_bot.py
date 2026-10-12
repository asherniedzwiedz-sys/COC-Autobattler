"""The safety rules: no gems, allow-list, dry run, foreground check."""
import json

import pytest

from cocbot import config
from cocbot.errors import (DryRunStop, FlowError, ForbiddenAction, GemSpendBlocked, NotAffordable, NotInGame,
                           StopBot)
from cocbot.guard import Action, GemGuard
from cocbot.vision import Box, Vision
from tests.conftest import H, W, draw_text, make_icon, make_screen, paste

BAR_Y = int(H * 0.85)  # inside the "selected_buttons" region


def bar_screen(*icons):
    """A screen with price buttons on the bar under a selected building: (kind, x) pairs."""
    screen = make_screen()
    for kind, x in icons:
        draw_text(screen, "250000", x - 120, BAR_Y + 26)
        paste(screen, make_icon(kind), x, BAR_Y)
    return screen


# --- GemGuard ------------------------------------------------------------------

def test_price_icon_found(vision):
    screen = bar_screen(("gold", 600))
    icon, gems = GemGuard(vision).pick_price_icon(screen, Box(0, 0, W, H), ("gold",))
    assert icon.name == "res_gold" and gems == []


def test_strict_blocks_any_gem(vision):
    screen = bar_screen(("gold", 300), ("gem", 900))
    with pytest.raises(GemSpendBlocked):
        GemGuard(vision).pick_price_icon(screen, Box(0, 0, W, H), ("gold",), strict=True)


def test_non_strict_allows_gem_on_other_button(vision):
    screen = bar_screen(("gold", 300), ("gem", 900))
    icon, gems = GemGuard(vision).pick_price_icon(screen, Box(0, 0, W, H), ("gold",), strict=False)
    assert icon.name == "res_gold" and len(gems) == 1


def test_non_strict_blocks_gem_on_same_button(vision):
    screen = bar_screen(("gold", 600))
    paste(screen, make_icon("gem"), 650, BAR_Y)
    with pytest.raises(GemSpendBlocked):
        GemGuard(vision).pick_price_icon(screen, Box(0, 0, W, H), ("gold",), strict=False)


def test_never_pays_with_gems(vision):
    with pytest.raises(GemSpendBlocked):
        GemGuard(vision).pick_price_icon(bar_screen(("gem", 600)), Box(0, 0, W, H), ("gem",))


def test_no_price_returns_none(vision):
    icon, gems = GemGuard(vision).pick_price_icon(make_screen(), Box(0, 0, W, H), ("gold", "elixir"))
    assert icon is None and gems == []


def test_spending_disabled_without_gem_template(tmp_path):
    guard = GemGuard(Vision(tmp_path))
    assert not guard.ready()
    with pytest.raises(GemSpendBlocked):
        guard.pick_price_icon(bar_screen(("gold", 600)), Box(0, 0, W, H), ("gold",))


# --- Bot.tap ---------------------------------------------------------------------

def test_live_tap(make_bot):
    bot, device = make_bot()
    bot.tap((10, 20), Action.NAVIGATE, "test")
    assert device.taps == [(10, 20)]


def test_dry_run_never_taps(make_bot, events):
    bot, device = make_bot(dry_run=True)
    with pytest.raises(DryRunStop):
        bot.tap((10, 20), Action.NAVIGATE, "open something")
    assert device.taps == []
    logged = [json.loads(line) for line in events.path.read_text().splitlines()]
    assert logged[-1]["type"] == "dry_run_action" and logged[-1]["point"] == [10, 20]


def test_step_mode_asks_for_navigation_but_never_for_spending(make_bot):
    bot, device = make_bot(dry_run=True, step=True, inputs=[""])
    bot.tap((10, 20), Action.NAVIGATE, "open the builder menu")  # user made the tap
    with pytest.raises(DryRunStop):
        bot.tap((10, 20), Action.UPGRADE_WALL, "pay", commits=True)
    assert device.taps == []


def test_donate_refused_when_switched_off(make_bot):
    bot, device = make_bot(auto_donate=False)
    with pytest.raises(ForbiddenAction):
        bot.tap((10, 20), Action.DONATE, "open chat")
    assert device.taps == []


def test_donate_allowed_when_switched_on(make_bot):
    bot, device = make_bot(auto_donate=True)
    bot.tap((10, 20), Action.DONATE, "open chat")
    assert device.taps == [(10, 20)]


def test_refuses_when_game_not_in_front(make_bot):
    bot, device = make_bot(foreground="com.android.vending")
    with pytest.raises(NotInGame):
        bot.tap((10, 20), Action.NAVIGATE, "test")
    assert device.taps == []


def test_refuses_while_gem_offer_visible(make_bot):
    bot, device = make_bot(paste(make_screen(), make_icon("trap"), 600, 300))
    with pytest.raises(GemSpendBlocked):
        bot.tap((10, 20), Action.NAVIGATE, "test")
    bot.tap((10, 20), Action.DISMISS, "close it")
    assert device.taps == [(10, 20)]


def test_refuses_forbidden_button(make_bot):
    bot, device = make_bot(paste(make_screen(), make_icon("shop"), 100, 100))
    with pytest.raises(GemSpendBlocked):
        bot.tap((118, 118), Action.NAVIGATE, "oops")
    bot.tap((400, 400), Action.NAVIGATE, "elsewhere is fine")
    assert device.taps == [(400, 400)]


# --- Bot.spend -------------------------------------------------------------------

def test_spend_taps_the_price_icon(make_bot):
    bot, device = make_bot(bar_screen(("gold", 300), ("elixir", 800)))
    assert bot.spend("selected_buttons", ["elixir"], Action.UPGRADE_WALL, "wall", strict=False) == "elixir"
    assert device.taps == [(818, BAR_Y + 18)]


def test_spend_blocks_gem_price(make_bot):
    screen = bar_screen(("gold", 600))
    paste(screen, make_icon("gem"), 650, BAR_Y)
    bot, device = make_bot(screen)
    with pytest.raises(GemSpendBlocked):
        bot.spend("selected_buttons", ["gold"], Action.UPGRADE_WALL, "wall", strict=False)
    assert device.taps == []


def test_spend_only_gem_price_strict(make_bot):
    bot, device = make_bot(bar_screen(("gem", 600)))
    with pytest.raises(GemSpendBlocked):
        bot.spend("selected_buttons", ["gold"], Action.UPGRADE_WALL, "wall")
    assert device.taps == []


def test_spend_optional_with_no_price(make_bot):
    bot, device = make_bot()
    assert bot.spend("upgrade_confirm", ["gold"], Action.UPGRADE_WALL, "confirm", optional=True) is None
    with pytest.raises(FlowError):
        bot.spend("upgrade_confirm", ["gold"], Action.UPGRADE_WALL, "confirm")
    assert device.taps == []


def test_spend_red_price_not_affordable(make_bot):
    screen = make_screen()
    draw_text(screen, "250000", 480, BAR_Y + 26, colour=(40, 40, 230))
    paste(screen, make_icon("gold"), 600, BAR_Y)
    bot, device = make_bot(screen)
    with pytest.raises(NotAffordable):
        bot.spend("selected_buttons", ["gold"], Action.UPGRADE_WALL, "wall")
    assert device.taps == []


def test_spend_detects_gem_offer_afterwards(make_bot):
    after = paste(make_screen(), make_icon("trap"), 600, 300)
    bot, device = make_bot(bar_screen(("gold", 600)), after)
    with pytest.raises(GemSpendBlocked):
        bot.spend("selected_buttons", ["gold"], Action.UPGRADE_WALL, "wall")
    assert len(device.taps) == 1  # the gold tap happened; the gem offer was not accepted


def test_on_gem_block_closes_and_stops_after_limit(make_bot, monkeypatch):
    monkeypatch.setattr(config, "MAX_GEM_BLOCKS", 2)
    offer = paste(paste(make_screen(), make_icon("trap"), 600, 300), make_icon("close"), 900, 150)
    bot, device = make_bot(offer, make_screen())
    bot.on_gem_block("first")
    assert device.taps == [(918, 168)]  # closed with the X
    with pytest.raises(StopBot):
        bot.on_gem_block("second")
