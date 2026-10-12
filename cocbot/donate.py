"""Donating to clan mates' troop requests: elixir/dark elixir troops only, never gems.

Only runs when you answered "yes" at startup; otherwise Bot refuses every DONATE
tap, so clan chat is never opened. Nothing here can type: the device layer has
no text input at all.
"""
from __future__ import annotations

import logging
from collections import Counter

from . import config as C
from .bot import Bot
from .errors import FlowError, GemSpendBlocked
from .guard import Action
from .vision import Match

log = logging.getLogger("cocbot")

NEVER_DONATE_PREFIXES = ("spell_", "siege_")


def donate_troops() -> tuple[str, ...]:
    bad = [t for t in C.DONATE_TROOPS if t.startswith(NEVER_DONATE_PREFIXES)]
    if bad:
        raise FlowError(f"DONATE_TROOPS may only hold troops, not {bad}")
    return tuple(C.DONATE_TROOPS)


class Donator:
    def __init__(self, bot: Bot):
        self.bot = bot

    def run(self) -> None:
        if not self.bot.auto_donate:
            return
        if not self.bot.vision.has("res_gem"):
            raise FlowError("templates/res_gem.png missing; donations disabled so gem donations can't slip through")
        troops = donate_troops()
        opener = self.bot.find("chat_open")
        if opener is None:
            raise FlowError("clan chat tab not visible (templates/chat_open.png)")
        self.bot.tap(opener.center, Action.DONATE, "open clan chat")
        try:
            for _ in range(C.DONATE_MAX_REQUESTS_PER_ROUND):
                screen = self.bot.screen()
                button = self.bot.find("btn_donate", screen, self.bot.region("chat_panel", screen))
                if button is None:
                    break
                self.bot.tap(button.center, Action.DONATE, "open a troop request", screen=screen)
                taps = self.fill_request(troops)
                self.close_donate_window()
                if not taps:
                    log.info("Nothing in camp that this request can take; leaving the rest of the requests.")
                    break
                self.bot.events.donation(dict(taps), dry_run=self.bot.dry_run)
        finally:
            closer = self.bot.find("chat_close")
            if closer is not None:
                self.bot.tap(closer.center, Action.DONATE, "close clan chat")

    def fill_request(self, troops: tuple[str, ...]) -> Counter:
        taps: Counter = Counter()
        for _ in range(C.DONATE_MAX_TAPS_PER_REQUEST):
            screen = self.bot.screen()
            trap = self.bot.guard.find_trap(screen)
            if trap:
                raise GemSpendBlocked(f"gem offer '{trap.name}' in the donate window")
            pick = self.pick_troop(screen, troops)
            if pick is None:
                break
            troop, icon = pick
            self.bot.tap(icon.center, Action.DONATE, f"donate one {troop}", screen=screen, commits=True)
            taps[troop] += 1
        return taps

    def pick_troop(self, screen, troops: tuple[str, ...]) -> tuple[str, Match] | None:
        """Highest-priority allowed troop whose slot shows no gem price.
        (A slot switches to a gem price once your camp runs out of that troop.)"""
        window = self.bot.region("donate_window", screen)
        for troop in troops:
            icon = self.bot.find(f"donate_{troop}", screen, window)
            if icon is None:
                continue
            if self.bot.guard.find_gems(screen, icon.box.pad(C.DONATE_SLOT_PAD)):
                log.debug("Skipping %s: its slot shows a gem price.", troop)
                continue
            return troop, icon
        return None

    def close_donate_window(self) -> None:
        close = self.bot.find("btn_close")
        if close is not None:
            self.bot.tap(close.center, Action.DONATE, "close the donate window")
