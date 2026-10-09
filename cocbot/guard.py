"""Safety guards: the allow-list of actions and the gem guard.

Gem protection is layered and fails closed:
  1. Every tap is tagged with an Action; anything off the allow-list is refused,
     and DONATE taps are refused unless donations were switched on at startup.
  2. Every tap first checks that Clash of Clans is the focused app, so a Google
     Play / App Store purchase sheet can never be tapped.
  3. Every tap first checks the screen for known gem offers (templates/trap_*.png)
     and refuses to tap anything but a close button while one is visible.
  4. Taps that land on a known gem/shop button (templates/forbid_*.png) are refused.
  5. Anything that spends resources taps the price icon itself, and only after
     positively finding a gold, elixir or dark elixir icon on the button and no
     gem icon (templates/res_gem*.png) anywhere on it. No icon found = no tap.
"""
from __future__ import annotations

from enum import Enum

import numpy as np

from . import config as C
from .errors import GemSpendBlocked
from .vision import Box, Match, Vision


class Action(Enum):
    NAVIGATE = "navigate"                # open/close menus and windows, select buildings
    DISMISS = "dismiss"                  # close a popup
    UPGRADE_WALL = "upgrade_wall"
    SUGGESTED_UPGRADE = "suggested_upgrade"
    DONATE = "donate"                    # includes opening/closing clan chat
    SEARCH = "search"
    ATTACK = "attack"
    RETURN_HOME = "return_home"
    TRAIN = "train"


ALLOWED_ACTIONS = frozenset(Action)
SPEND_RESOURCES = ("gold", "elixir", "dark")


class GemGuard:
    def __init__(self, vision: Vision):
        self.vision = vision

    def ready(self) -> bool:
        """Spending is only allowed when the gem icon template exists to check against."""
        return self.vision.has("res_gem") and any(self.vision.has(f"res_{r}") for r in SPEND_RESOURCES)

    def find_gems(self, screen: np.ndarray, region: Box | None = None) -> list[Match]:
        if not self.vision.has("res_gem"):
            return []
        return self.vision.find_all(screen, "res_gem", region, threshold=C.GEM_MATCH_THRESHOLD)

    def find_trap(self, screen: np.ndarray) -> Match | None:
        """A known gem offer popup (templates/trap_*.png) on screen, if any."""
        for name in self.vision.names_with_prefix("trap_"):
            m = self.vision.find(screen, name)
            if m:
                return m
        return None

    def forbidden_at(self, screen: np.ndarray, point: tuple[int, int]) -> str | None:
        """Name of a never-press button (templates/forbid_*.png) under `point`, if any."""
        for name in self.vision.names_with_prefix("forbid_"):
            for m in self.vision.find_all(screen, name):
                if m.box.pad(0.1).contains(point):
                    return name
        return None

    def pick_price_icon(self, screen: np.ndarray, area: Box, allowed: tuple[str, ...],
                        strict: bool = True) -> tuple[Match | None, list[Match]]:
        """The gold/elixir/dark elixir price icon to tap inside `area`, plus any gem icons seen.

        strict=True: any gem icon in the area blocks (use inside a single-button window).
        strict=False: only a gem icon on the same button as the price blocks (use on
        the bar under a selected building, where e.g. a gem "Boost" button may sit
        beside the gold "Upgrade" button).
        Raises GemSpendBlocked when blocked; returns (None, gems) when no allowed price is visible.
        """
        bad = [r for r in allowed if r not in SPEND_RESOURCES]
        if bad or not allowed:
            raise GemSpendBlocked(f"refusing to pay with {bad or 'nothing'}; only gold/elixir/dark elixir")
        if not self.ready():
            raise GemSpendBlocked("gem guard templates missing (res_gem + res_gold/elixir/dark); spending disabled")
        gems = self.find_gems(screen, area)
        if strict and gems:
            raise GemSpendBlocked(f"gem price found at {gems[0].center}")
        for resource in allowed:
            name = f"res_{resource}"
            icon = self.vision.find(screen, name, area) if self.vision.has(name) else None
            if icon is None:
                continue
            button = icon.box.relative(*C.PRICE_BUTTON_SPAN)
            if any(button.contains(g.center) for g in gems):
                raise GemSpendBlocked(f"gem price on the same button as the {resource} price at {icon.center}")
            return icon, gems
        return None, gems
