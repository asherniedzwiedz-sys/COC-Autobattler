"""Every tap and swipe the bot makes goes through Bot, so the safety guards and
dry-run mode apply to all of them."""
from __future__ import annotations

import logging
import time
from typing import Callable, Sequence

import numpy as np

from . import config as C
from .device import Device
from .errors import DryRunStop, FlowError, ForbiddenAction, GemSpendBlocked, NotAffordable, NotInGame, StopBot
from .guard import ALLOWED_ACTIONS, Action, GemGuard
from .logbook import EventLog
from .vision import Box, Match, Vision, is_price_red, resolve_region

log = logging.getLogger("cocbot")


class Bot:
    def __init__(self, device: Device, vision: Vision, events: EventLog, *, dry_run: bool,
                 auto_donate: bool, step: bool = False, input_fn: Callable[[str], str] = input):
        self.device = device
        self.vision = vision
        self.events = events
        self.guard = GemGuard(vision)
        self.dry_run = dry_run
        self.auto_donate = auto_donate
        self.step = step
        self.input = input_fn
        self.gem_blocks = 0
        self._warned_foreground = False

    # --- screen helpers ------------------------------------------------------

    def screen(self) -> np.ndarray:
        return self.device.screenshot()

    def region(self, key: str, screen: np.ndarray) -> Box | None:
        return resolve_region(C.REGIONS[key], screen, self.vision)

    def need_region(self, key: str, screen: np.ndarray) -> Box:
        box = self.region(key, screen)
        if box is None:
            raise FlowError(f"screen region '{key}' not found (is its anchor icon visible?)")
        return box

    def find(self, name: str, screen: np.ndarray | None = None, region: Box | None = None) -> Match | None:
        if not self.vision.has(name):
            return None
        return self.vision.find(self.screen() if screen is None else screen, name, region)

    def wait_for(self, name: str, region_key: str | None = None,
                 timeout: float = C.WAIT_TIMEOUT) -> tuple[Match | None, np.ndarray]:
        deadline = time.monotonic() + timeout
        while True:
            screen = self.screen()
            region = self.region(region_key, screen) if region_key else None
            m = self.find(name, screen, region)
            if m or time.monotonic() >= deadline:
                return m, screen
            time.sleep(0.4)

    # --- guards --------------------------------------------------------------

    def check_allowed(self, action: Action) -> None:
        if not isinstance(action, Action) or action not in ALLOWED_ACTIONS:
            raise ForbiddenAction(f"{action!r} is not an allowed action")
        if action is Action.DONATE and not self.auto_donate:
            raise ForbiddenAction("donations and clan chat are switched off for this session")

    def check_foreground(self) -> None:
        if not C.CHECK_FOREGROUND:
            return
        app = self.device.foreground_app()
        if app is None:
            if not self._warned_foreground:
                log.warning("Can't tell which app is in front on this device; foreground check skipped.")
                self._warned_foreground = True
            return
        if app not in (C.GAME_PACKAGE_ANDROID, C.GAME_BUNDLE_IOS):
            raise NotInGame(f"'{app}' is in front, not Clash of Clans")

    def _pre_tap(self, action: Action, points: Sequence[tuple[int, int]], screen: np.ndarray | None) -> None:
        self.check_allowed(action)
        self.check_foreground()
        screen = self.screen() if screen is None else screen
        if action is not Action.DISMISS:
            trap = self.guard.find_trap(screen)
            if trap:
                raise GemSpendBlocked(f"gem offer '{trap.name}' is on screen")
        for point in points:
            forbidden = self.guard.forbidden_at(screen, point)
            if forbidden:
                raise GemSpendBlocked(f"tap at {point} would press '{forbidden}'")

    def _dry_run(self, action: Action, why: str, point: tuple[int, int], commits: bool) -> None:
        self.events.dry_run_action(action.value, why, point)
        if self.step and not commits:
            answer = self.input(f"    [step] Do this yourself: {why} at {point}. Enter = done, s = stop this flow: ")
            if answer.strip().lower().startswith("s"):
                raise DryRunStop(why)
            return
        raise DryRunStop(why)

    # --- actions -------------------------------------------------------------

    def tap(self, point: tuple[int, int], action: Action, why: str, *,
            screen: np.ndarray | None = None, commits: bool = False) -> None:
        """Tap after every guard passes. `commits` marks taps that spend, donate or deploy:
        in step-by-step dry runs you are never asked to make those yourself."""
        point = (int(point[0]), int(point[1]))
        self._pre_tap(action, [point], screen)
        if self.dry_run:
            self._dry_run(action, why, point, commits)
            return
        log.debug("tap %s [%s] %s", point, action.value, why)
        self.device.tap(*point)
        time.sleep(C.TAP_SETTLE)

    def tap_button(self, button: Match, action: Action, why: str, *, screen: np.ndarray | None = None) -> None:
        """Tap a button found by template, refusing if a gem price shows on it."""
        screen = self.screen() if screen is None else screen
        gems = self.guard.find_gems(screen, button.box.relative(*C.PRICE_BUTTON_SPAN))
        if gems:
            raise GemSpendBlocked(f"'{button.name}' shows a gem price; not pressing it")
        self.tap(button.center, action, why, screen=screen)

    def tap_many(self, points: Sequence[tuple[int, int]], action: Action, why: str) -> None:
        """Several quick taps (deploying units). Guards run once for the whole batch;
        these always count as committing taps, so a dry run logs them all and stops."""
        points = [(int(x), int(y)) for x, y in points]
        if not points:
            return
        self._pre_tap(action, points, None)
        if self.dry_run:
            for point in points:
                self.events.dry_run_action(action.value, why, point)
            raise DryRunStop(why)
        for point in points:
            self.device.tap(*point)
            time.sleep(C.DEPLOY_TAP_DELAY)

    def wait_gone(self, name: str, timeout: float = 5.0) -> bool:
        """Wait for a template to disappear (e.g. a screen transition); False on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.find(name) is None:
                return True
            time.sleep(0.3)
        return False

    def swipe(self, start: tuple[int, int], end: tuple[int, int], action: Action, why: str,
              duration_ms: int = 400) -> None:
        self._pre_tap(action, [start, end], None)
        if self.dry_run:
            self._dry_run(action, f"swipe {start}->{end}: {why}", start, False)
            return
        self.device.swipe(*start, *end, duration_ms)
        time.sleep(C.SWIPE_SETTLE)

    def spend(self, area_key: str, allowed: Sequence[str], action: Action, why: str, *,
              strict: bool = True, optional: bool = False) -> str | None:
        """Tap a price that is positively gold, elixir or dark elixir, never gems.

        Returns the resource paid with, or None if `optional` and no price is shown.
        """
        screen = self.screen()
        area = self.need_region(area_key, screen)
        icon, gems = self.guard.pick_price_icon(screen, area, tuple(allowed), strict=strict)
        if icon is None:
            if gems and strict:
                raise GemSpendBlocked(f"{why}: only a gem price is shown")
            if optional:
                return None
            raise FlowError(f"{why}: no {'/'.join(allowed)} price found")
        if is_price_red(screen, icon.box):
            raise NotAffordable(f"{why}: price is shown in red")
        resource = icon.name.removeprefix("res_")
        self.tap(icon.center, action, f"{why} (pay with {resource})", screen=screen, commits=True)
        self.check_after_spend(why)
        return resource

    def check_after_spend(self, why: str) -> None:
        screen = self.screen()
        trap = self.guard.find_trap(screen)
        popup = self.region("popup_center", screen)
        gems = self.guard.find_gems(screen, popup) if popup else []
        if trap or gems:
            what = f"'{trap.name}'" if trap else "a gem price in a popup"
            raise GemSpendBlocked(f"after '{why}' the game showed {what}")

    def close_popups(self, attempts: int = 4) -> None:
        """Close windows/popups with their close button (Back key as a last resort for gem offers)."""
        for _ in range(attempts):
            screen = self.screen()
            close = self.find("btn_close", screen)
            if close is not None:
                self.tap(close.center, Action.DISMISS, "close window", screen=screen)
                continue
            if self.guard.find_trap(screen) is None:
                return
            if self.dry_run:
                raise DryRunStop("press Back to close a gem offer")
            if not self.device.press_back():
                break
            time.sleep(C.TAP_SETTLE)
        if self.guard.find_trap(self.screen()):
            raise StopBot("A gem offer is open and could not be closed; stopping to be safe.")

    def on_gem_block(self, reason: str) -> None:
        """Log a blocked gem path, close whatever offered it, and stop after too many."""
        self.gem_blocks += 1
        self.events.gem_block(reason)
        try:
            self.close_popups()
        except DryRunStop:
            pass
        if self.gem_blocks >= C.MAX_GEM_BLOCKS:
            raise StopBot(f"Gem guard blocked {self.gem_blocks} actions this session; stopping to be safe.")
