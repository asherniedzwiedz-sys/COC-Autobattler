"""Finding a base worth attacking: press Next until one qualifies, up to MAX_NEXTS.

A base qualifies only when every rule holds (see `evaluate`): loot in range,
a dead base (full collectors), and a near-certain win for the approved army.
Anything the bot can't read counts against the base, so an unreadable screen
is skipped rather than attacked.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import config as C
from . import ocr
from .bot import Bot
from .errors import FlowError
from .guard import Action
from .vision import Box, Match, crop

log = logging.getLogger("cocbot")


@dataclass
class BaseInfo:
    gold: int | None = None
    elixir: int | None = None
    dark: int | None = None
    full_collectors: int = 0
    air_defenses: list[Box] = field(default_factory=list)
    town_hall: Match | None = None
    th_level: int | None = None
    th_exposed: bool = False
    nexts: int = 0

    @property
    def loot(self) -> int | None:
        if self.gold is None or self.elixir is None:
            return None
        return self.gold + self.elixir

    def summary(self) -> str:
        loot = f"{self.loot:,}" if self.loot is not None else "unreadable"
        return (f"loot {loot} (gold {self.gold}, elixir {self.elixir}, dark {self.dark}), "
                f"TH{self.th_level or '?'}{' in the open' if self.th_exposed else ''}, "
                f"{self.full_collectors} full collectors, {len(self.air_defenses)} air defenses")


def evaluate(info: BaseInfo) -> tuple[bool, list[str]]:
    """(qualifies, reasons it doesn't). Pure, so the rules are unit tested."""
    reasons = []
    if info.loot is None:
        reasons.append("loot unreadable")
    elif not C.LOOT_MIN <= info.loot <= C.LOOT_MAX:
        reasons.append(f"loot {info.loot:,} outside {C.LOOT_MIN:,}-{C.LOOT_MAX:,}")
    if info.full_collectors < C.MIN_FULL_COLLECTORS:
        reasons.append(f"{info.full_collectors} full collectors, need {C.MIN_FULL_COLLECTORS} (not a dead base)")
    overmatched = (info.th_level is not None and info.th_level <= C.MAX_TARGET_TH
                   and len(info.air_defenses) <= C.MAX_AIR_DEFENSES)
    if not (info.th_exposed or overmatched):
        if info.th_level is None:
            reasons.append("Town Hall level unknown and not in the open")
        elif info.th_level > C.MAX_TARGET_TH:
            reasons.append(f"TH{info.th_level} is above TH{C.MAX_TARGET_TH}")
        else:
            reasons.append(f"{len(info.air_defenses)} air defenses, max {C.MAX_AIR_DEFENSES}")
    return not reasons, reasons


def th_level_of(name: str) -> int | None:
    m = re.fullmatch(r"enemy_th(\d+)", name)
    return int(m.group(1)) if m else None


class Searcher:
    def __init__(self, bot: Bot):
        self.bot = bot

    # --- reading a base -------------------------------------------------------

    def read_loot_once(self, screen: np.ndarray) -> dict[str, int | None]:
        loot = {}
        for resource in ("gold", "elixir", "dark"):
            box = self.bot.region(f"loot_{resource}_amount", screen)
            loot[resource] = ocr.read_number(crop(screen, box), self.bot.vision.digits) if box else None
        return loot

    def read_loot(self) -> dict[str, int | None]:
        """Loot read LOOT_CONFIRM_READS times; a value that changes between reads is unknown."""
        reads = []
        for i in range(max(1, C.LOOT_CONFIRM_READS)):
            if i:
                time.sleep(0.4)
            reads.append(self.read_loot_once(self.bot.screen()))
        return {r: reads[0][r] if all(x[r] == reads[0][r] for x in reads) else None for r in reads[0]}

    def find_town_hall(self, screen: np.ndarray) -> tuple[Match | None, int | None]:
        best: Match | None = None
        for name in self.bot.vision.names_with_prefix("enemy_th"):
            m = self.bot.vision.find(screen, name)
            if m and (best is None or m.score > best.score):
                best = m
        return best, th_level_of(best.name) if best else None

    def th_in_the_open(self, screen: np.ndarray, town_hall: Match | None) -> bool:
        """No wall piece near the Town Hall. Needs templates/enemy_wall*.png; without them
        the bot can't tell, so it says no."""
        walls = self.bot.vision.names_with_prefix("enemy_wall")
        if town_hall is None or not walls:
            return False
        r = C.EXPOSED_TH_RADIUS
        area = town_hall.box.relative(-r, -r, 1 + r, 1 + r)
        return not any(self.bot.vision.find_all(screen, name, area) for name in walls)

    def inspect(self, nexts: int) -> BaseInfo:
        loot = self.read_loot()
        screen = self.bot.screen()
        vision = self.bot.vision
        full = sum(len(vision.find_all(screen, n, limit=50)) for n in vision.names_with_prefix("full_collector"))
        ads = [m.box for n in vision.names_with_prefix("air_defense") for m in vision.find_all(screen, n)]
        town_hall, level = self.find_town_hall(screen)
        if C.SAVE_SEARCH_SCREENSHOTS:
            folder = Path(C.LOG_DIR) / "searches"
            folder.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(folder / f"{time.strftime('%Y%m%d_%H%M%S')}_{nexts:02d}.png"), screen)
        return BaseInfo(loot["gold"], loot["elixir"], loot["dark"], full, ads, town_hall, level,
                        self.th_in_the_open(screen, town_hall), nexts)

    # --- the search loop ----------------------------------------------------------

    def start(self) -> None:
        screen = self.bot.screen()
        attack = self.bot.find("btn_attack", screen)
        if attack is None:
            raise FlowError("Attack button not visible (templates/btn_attack.png); not on the home screen?")
        self.bot.tap_button(attack, Action.SEARCH, "open the attack menu", screen=screen)
        find, screen = self.bot.wait_for("btn_find_match")
        if find is None:
            raise FlowError("'Find a Match' button didn't appear (templates/btn_find_match.png)")
        self.bot.tap_button(find, Action.SEARCH, "find a match", screen=screen)

    def find_base(self) -> BaseInfo | None:
        """Search until a base qualifies; None (back home) after MAX_NEXTS Nexts."""
        self.start()
        for nexts in range(C.MAX_NEXTS + 1):
            button, _ = self.bot.wait_for("btn_next", timeout=20)
            if button is None:
                raise FlowError("search screen didn't appear (templates/btn_next.png)")
            info = self.inspect(nexts)
            ok, reasons = evaluate(info)
            self.bot.events.record("base", nexts=nexts, qualifies=ok, reasons=reasons, gold=info.gold,
                                   elixir=info.elixir, dark=info.dark, th_level=info.th_level,
                                   th_exposed=info.th_exposed, full_collectors=info.full_collectors,
                                   air_defenses=len(info.air_defenses))
            log.info("Base %d: %s -> %s", nexts, info.summary(), "ATTACK" if ok else "skip (" + "; ".join(reasons) + ")")
            if ok:
                return info
            if nexts == C.MAX_NEXTS:
                break
            button, screen = self.bot.wait_for("btn_next", timeout=5)
            if button is None:
                raise FlowError("Next button disappeared")
            self.bot.tap_button(button, Action.SEARCH, f"next base ({nexts + 1}/{C.MAX_NEXTS})", screen=screen)
            self.bot.wait_gone("btn_next", timeout=5)
        self.end_search()
        return None

    def end_search(self) -> None:
        """Leave the search without deploying anything (no trophies lost)."""
        end, screen = self.bot.wait_for("btn_end_battle", timeout=5)
        if end is None:
            raise FlowError("'End Battle' button not found (templates/btn_end_battle.png)")
        self.bot.tap_button(end, Action.RETURN_HOME, "end the search and go home", screen=screen)
        home, _ = self.bot.wait_for("builder_icon", timeout=20)
        if home is None:
            raise FlowError("didn't get back to the home screen")
