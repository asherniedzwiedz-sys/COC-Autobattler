"""Wall upgrades with excess loot, and the game's suggested upgrades once walls are maxed."""
from __future__ import annotations

import logging
import re

import numpy as np

from . import config as C
from . import ocr
from .bot import Bot
from .errors import FlowError, NotAffordable
from .guard import SPEND_RESOURCES, Action
from .ocr import Word
from .state import HomeState, read_home_state, storages_to_spend
from .vision import Box, crop

log = logging.getLogger("cocbot")


def is_wall_row(text: str) -> bool:
    low = text.lower()
    return bool(re.search(r"\bwalls?\b", low)) and not re.search(r"breaker|wrecker", low)


def row_name(text: str) -> str:
    """'Archer Tower 6,500,000 5d 12h' -> 'Archer Tower'."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z.'-]*", text) if len(w) > 1]
    return " ".join(words[:4])


def pick_suggested_row(lines: list[list[Word]], tried: set[str]) -> tuple[str, Box] | None:
    """First untried row in the builder menu's "Suggested upgrades" section."""
    for line in lines:
        text = ocr.line_text(line)
        low = text.lower()
        if "other" in low and "upgrade" in low:
            break  # past the suggested section
        words = re.findall(r"[a-z]{3,}", low)
        if not words or all(w in C.MENU_HEADER_WORDS for w in words):
            continue
        if any(skip.lower() in low for skip in C.SUGGESTED_SKIP_WORDS):
            continue
        name = row_name(text)
        if name and name not in tried:
            return name, ocr.line_box(line)
    return None


def spent_amount(before: int | None, after: int | None) -> int | None:
    if before is None or after is None or after > before:
        return None
    return before - after


class Upgrader:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.walls_maxed: bool | None = C.WALLS_MAXED

    def run(self, state: HomeState) -> None:
        full = storages_to_spend(state)
        if not full:
            log.info("Gold and elixir below %.0f%% of max; no upgrades needed.", C.STORAGE_THRESHOLD * 100)
            return
        if not self.bot.guard.ready():
            raise FlowError("gem guard templates missing (res_gem, res_gold/res_elixir); upgrades disabled")
        if state.builders_free is None:
            raise FlowError("couldn't read the builder count; skipping upgrades")
        if state.builders_free == 0 and (C.WALLS_NEED_FREE_BUILDER or self.walls_maxed):
            log.info("%s full but every builder is busy; nothing can be upgraded right now.", " and ".join(full))
            return
        if not self.walls_maxed:
            for resource in full:
                self.upgrade_walls(resource)
                if self.walls_maxed:
                    break
        if self.walls_maxed:
            self.suggested_upgrades()

    # --- walls -----------------------------------------------------------------

    def upgrade_walls(self, resource: str) -> None:
        for _ in range(C.MAX_WALL_UPGRADES_PER_ROUND):
            state = read_home_state(self.bot.screen(), self.bot.vision)
            before = state.storage(resource)
            if not before.is_full(C.STORAGE_THRESHOLD):
                return
            if C.WALLS_NEED_FREE_BUILDER and not state.builders_free:
                log.info("No free builder for a wall upgrade.")
                return
            row = self.find_menu_row(is_wall_row)
            if row is None:
                self.walls_maxed = True
                log.info("No wall upgrade in the builder menu: walls are maxed for this Town Hall.")
                return
            self.bot.tap(row.center, Action.UPGRADE_WALL, "select the wall suggested in the builder menu")
            used = self.bot.spend("selected_buttons", [resource], Action.UPGRADE_WALL,
                                  f"wall upgrade button ({resource})", strict=False)
            self.bot.spend("upgrade_confirm", [resource], Action.UPGRADE_WALL, "confirm wall upgrade", optional=True)
            after = read_home_state(self.bot.screen(), self.bot.vision).storage(resource)
            self.bot.events.wall_upgrade(used, spent_amount(before.current, after.current), dry_run=self.bot.dry_run)

    # --- suggested upgrades ----------------------------------------------------

    def suggested_upgrades(self) -> None:
        tried: set[str] = set()
        for _ in range(C.MAX_SUGGESTED_UPGRADES_PER_ROUND):
            state = read_home_state(self.bot.screen(), self.bot.vision)
            if state.builders_free is None:
                raise FlowError("couldn't read the builder count")
            if state.builders_free == 0:
                log.info("All builders busy.")
                return
            screen = self.open_builder_menu()
            row = pick_suggested_row(self.menu_lines(screen), tried)
            if row is None:
                self.close_builder_menu()
                log.info("No more suggested upgrades to try.")
                return
            name, box = row
            tried.add(name)
            self.bot.tap(box.center, Action.SUGGESTED_UPGRADE, f"select suggested upgrade '{name}'")
            try:
                used = self.open_upgrade(name)
            except NotAffordable as e:
                log.info("Skipping %s: %s", name, e)
                self.bot.close_popups()
                continue
            after = read_home_state(self.bot.screen(), self.bot.vision)
            spent = spent_amount(state.storage(used).current, after.storage(used).current)
            self.bot.events.suggested_upgrade(name, used, spent, dry_run=self.bot.dry_run)

    def open_upgrade(self, name: str) -> str:
        """Press the selected building's upgrade button and confirm, paying with gold/elixir/dark only."""
        used = self.bot.spend("selected_buttons", SPEND_RESOURCES, Action.SUGGESTED_UPGRADE,
                              f"upgrade button for '{name}'", strict=False, optional=True)
        if used is None:
            # No price on the bar: the button only opens the upgrade window, where the price must show.
            button = self.bot.find("btn_upgrade", region=self.bot.need_region("selected_buttons", self.bot.screen()))
            if button is None:
                raise FlowError(f"no upgrade button found for '{name}'")
            self.bot.tap(button.center, Action.SUGGESTED_UPGRADE, f"open the upgrade window for '{name}'")
            return self.bot.spend("upgrade_confirm", SPEND_RESOURCES, Action.SUGGESTED_UPGRADE,
                                  f"confirm upgrade of '{name}'")
        self.bot.spend("upgrade_confirm", [used], Action.SUGGESTED_UPGRADE,
                       f"confirm upgrade of '{name}'", optional=True)
        return used

    # --- builder menu ----------------------------------------------------------

    def open_builder_menu(self) -> np.ndarray:
        screen = self.bot.screen()
        icon = self.bot.find("builder_icon", screen)
        if icon is None:
            raise FlowError("builder icon not visible (templates/builder_icon.png); not on the home screen?")
        self.bot.tap(icon.center, Action.NAVIGATE, "open the builder menu", screen=screen)
        return self.bot.screen()

    def close_builder_menu(self) -> None:
        icon = self.bot.find("builder_icon")
        if icon is not None:
            self.bot.tap(icon.center, Action.NAVIGATE, "close the builder menu")

    def menu_lines(self, screen: np.ndarray) -> list[list[Word]]:
        box = self.bot.need_region("builder_menu", screen)
        return ocr.group_lines(ocr.read_words(crop(screen, box), offset=(box.x, box.y)))

    def find_menu_row(self, predicate) -> Box | None:
        """Open the builder menu and scroll it looking for a row whose text matches."""
        screen = self.open_builder_menu()
        words_seen = 0
        for scroll in range(C.BUILDER_MENU_SCROLLS + 1):
            lines = self.menu_lines(screen)
            words_seen += sum(len(line) for line in lines)
            for line in lines:
                if predicate(ocr.line_text(line)):
                    return ocr.line_box(line)
            if scroll < C.BUILDER_MENU_SCROLLS:
                box = self.bot.need_region("builder_menu", screen)
                cx = box.center[0]
                self.bot.swipe((cx, box.y + int(box.h * 0.85)), (cx, box.y + int(box.h * 0.2)),
                               Action.NAVIGATE, "scroll the builder menu")
                screen = self.bot.screen()
        self.close_builder_menu()
        if words_seen < 3:
            raise FlowError("couldn't read the builder menu; not concluding anything about walls")
        return None
