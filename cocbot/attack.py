"""The approved attack: lightning on the Air Defenses, a line of dragons, then the
Battle Blimp and heroes behind them, with hero abilities on a timer.

`build_plan` is pure (screen size + what the search saw -> list of steps), so a
dry run can log the whole attack without tapping, and the geometry is tested.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

import numpy as np

from . import config as C
from . import ocr
from .bot import Bot
from .errors import FlowError
from .guard import Action
from .search import BaseInfo
from .vision import Box, Match, crop

log = logging.getLogger("cocbot")

EDGES = ("top_left", "top_right", "bottom_right", "bottom_left")
_EDGE_CORNERS = {"top_left": ("left", "top"), "top_right": ("top", "right"),
                 "bottom_right": ("right", "bottom"), "bottom_left": ("bottom", "left")}


@dataclass(frozen=True)
class Step:
    slot: str                          # troop bar slot to select, e.g. "dragon"
    points: tuple[tuple[int, int], ...]
    why: str
    wait_after: float = 0.0


def map_corners(width: int, height: int) -> dict[str, tuple[float, float]]:
    """Corners of the battle map diamond in pixels (see MAP_CENTER / MAP_HALF_SIZE)."""
    cx = width / 2 + C.MAP_CENTER[0] * height
    cy = height / 2 + C.MAP_CENTER[1] * height
    hw, hh = C.MAP_HALF_SIZE[0] * height, C.MAP_HALF_SIZE[1] * height
    return {"top": (cx, cy - hh), "right": (cx + hw, cy), "bottom": (cx, cy + hh), "left": (cx - hw, cy)}


def edge_points(width: int, height: int, edge: str, count: int) -> list[tuple[int, int]]:
    """`count` points spread along one edge of the map, just outside it, never on the troop bar."""
    corners = map_corners(width, height)
    (x1, y1), (x2, y2) = (corners[c] for c in _EDGE_CORNERS[edge])
    cx, cy = (corners["left"][0] + corners["right"][0]) / 2, (corners["top"][1] + corners["bottom"][1]) / 2
    a, b = C.DEPLOY_EDGE_SPAN
    ts = [a + (b - a) * (i + 0.5) / count for i in range(count)] if count > 0 else []
    points = []
    for t in ts:
        x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        dx, dy = x - cx, y - cy
        norm = math.hypot(dx, dy) or 1.0
        x, y = x + dx / norm * C.DEPLOY_OUTSET * height, y + dy / norm * C.DEPLOY_OUTSET * height
        x, y = min(max(x, 0), width - 1), min(max(y, 0), height - 1)
        if y < C.TROOP_BAR_TOP * height:
            points.append((round(x), round(y)))
    return points


def edge_midpoint(width: int, height: int, edge: str) -> tuple[int, int]:
    corners = map_corners(width, height)
    (x1, y1), (x2, y2) = (corners[c] for c in _EDGE_CORNERS[edge])
    return round((x1 + x2) / 2), round((y1 + y2) / 2)


def choose_side(width: int, height: int, town_hall: Box | None) -> str:
    """Attack from the edge nearest the enemy Town Hall (the surest star)."""
    usable = [e for e in EDGES if edge_points(width, height, e, 5)]
    if town_hall is None:
        return C.DEFAULT_SIDE if C.DEFAULT_SIDE in usable else usable[0]
    tx, ty = town_hall.center
    return min(usable, key=lambda e: math.dist(edge_midpoint(width, height, e), (tx, ty)))


def build_plan(width: int, height: int, base: BaseInfo, available_slots: set[str]) -> tuple[str, list[Step]]:
    army = C.APPROVED_ARMY
    side = choose_side(width, height, base.town_hall.box if base.town_hall else None)
    mid_points = edge_points(width, height, side, 3)
    mid = mid_points[len(mid_points) // 2] if mid_points else edge_midpoint(width, height, side)
    steps: list[Step] = []

    lightning = army["spells"].get("lightning", 0)
    if lightning and "lightning" in available_slots and base.air_defenses:
        sx, sy = edge_midpoint(width, height, side)
        targets = sorted(base.air_defenses, key=lambda b: math.dist(b.center, (sx, sy)))
        for ad in targets[: lightning // C.LIGHTNING_PER_AD]:
            steps.append(Step("lightning", (ad.center,) * C.LIGHTNING_PER_AD,
                              f"lightning on the Air Defense at {ad.center}", C.ZAP_DELAY))

    for troop, count in army["troops"].items():
        points = edge_points(width, height, side, count)
        # part of a bottom edge can sit behind the troop bar: reuse the visible points so all deploy
        points = [points[i % len(points)] for i in range(count)] if points else []
        steps.append(Step(troop, tuple(points), f"{count} {troop}s along the {side} edge"))
    if steps:
        steps[-1] = Step(steps[-1].slot, steps[-1].points, steps[-1].why, C.HERO_DELAY)

    siege = army.get("siege")
    if siege and siege in available_slots:
        steps.append(Step(siege, (mid,), f"{siege} (carries the Clan Castle) at the {side} edge"))
    for hero in army["heroes"]:
        if hero in available_slots:
            steps.append(Step(hero, (mid,), f"{hero} behind the dragons"))
    return side, steps


def parse_signed(text: str) -> int | None:
    """'+12' -> 12, '-8' -> -8, '12' -> 12."""
    digits = ocr.parse_int(text)
    if digits is None:
        return None
    return -digits if text.strip().startswith("-") else digits


class Attacker:
    def __init__(self, bot: Bot):
        self.bot = bot

    def slot_names(self) -> list[str]:
        army = C.APPROVED_ARMY
        return [*army["troops"], *army["spells"], *([army["siege"]] if army.get("siege") else []), *army["heroes"]]

    def find_slots(self, screen: np.ndarray) -> dict[str, Match]:
        slots = {}
        for name in self.slot_names():
            m = self.bot.find(f"slot_{name}", screen)
            if m:
                slots[name] = m
        missing = [t for t in C.APPROVED_ARMY["troops"] if t not in slots]
        if missing:
            raise FlowError(f"troop bar slot not found for {missing} (templates/slot_<name>.png)")
        skipped = [n for n in self.slot_names() if n not in slots]
        if skipped:
            log.warning("Not in the troop bar (or no template), so not deployed: %s", ", ".join(skipped))
        return slots

    def attack(self, base: BaseInfo) -> dict:
        screen = self.bot.screen()
        height, width = screen.shape[:2]
        slots = self.find_slots(screen)
        side, steps = build_plan(width, height, base, set(slots))
        log.info("Attacking from the %s edge: %s", side, "; ".join(s.why for s in steps))
        if self.bot.dry_run:
            for step in steps:
                self.bot.events.dry_run_action(Action.ATTACK.value, step.why, step.points[0])
            self.bot.tap_many(steps[0].points, Action.ATTACK, steps[0].why)  # raises DryRunStop

        deployed: dict[str, float] = {}
        for step in steps:
            slot = slots[step.slot]
            self.bot.tap(slot.center, Action.ATTACK, f"select {step.slot}", commits=True)
            self.bot.tap_many(step.points, Action.ATTACK, step.why)
            deployed.setdefault(step.slot, time.monotonic())
            time.sleep(step.wait_after)
        trophies = self.wait_for_end(slots, deployed)
        return {"side": side, "trophies": trophies, "air_defenses_zapped": sum(s.slot == "lightning" for s in steps)}

    def wait_for_end(self, slots: dict[str, Match], deployed: dict[str, float]) -> int | None:
        """Fire hero abilities on schedule until the battle ends; surrender at BATTLE_TIMEOUT."""
        abilities = sorted((deployed[h] + C.ABILITY_TIMES.get(h, 15), h) for h in C.APPROVED_ARMY["heroes"] if h in deployed)
        start = time.monotonic()
        while time.monotonic() - start < C.BATTLE_TIMEOUT:
            while abilities and time.monotonic() >= abilities[0][0]:
                _, hero = abilities.pop(0)
                self.bot.tap(slots[hero].center, Action.ATTACK, f"{hero} ability", commits=True)
            screen = self.bot.screen()
            home = self.bot.find("btn_return_home", screen)
            if home:
                return self.finish(home, screen)
            time.sleep(1.0)
        log.info("Battle still running after %ds; surrendering.", C.BATTLE_TIMEOUT)
        surrender, screen = self.bot.wait_for("btn_surrender", timeout=5)
        if surrender is None:
            raise FlowError("battle didn't end and no Surrender button was found (templates/btn_surrender.png)")
        self.bot.tap_button(surrender, Action.RETURN_HOME, "surrender (battle timeout)", screen=screen)
        okay, screen = self.bot.wait_for("btn_okay", timeout=5)
        if okay:
            self.bot.tap_button(okay, Action.RETURN_HOME, "confirm surrender", screen=screen)
        home, screen = self.bot.wait_for("btn_return_home", timeout=15)
        if home is None:
            raise FlowError("no Return Home button after the battle (templates/btn_return_home.png)")
        return self.finish(home, screen)

    def finish(self, home: Match, screen: np.ndarray) -> int | None:
        """Read the trophy change on the results screen, then go home."""
        box = self.bot.region("result_trophies", screen)
        trophies = parse_signed(ocr.read_chars(crop(screen, box), self.bot.vision.digits, "0123456789+-")) if box else None
        self.bot.tap_button(home, Action.RETURN_HOME, "return home", screen=screen)
        back, _ = self.bot.wait_for("builder_icon", timeout=20)
        if back is None:
            self.bot.close_popups()
        return trophies
