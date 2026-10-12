"""Reading the home village: storages and builders, plus the decisions built on them."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config as C
from . import ocr
from .vision import Box, Vision, crop, resolve_region

log = logging.getLogger("cocbot")

RESOURCES = ("gold", "elixir", "dark")
WALL_RESOURCES = ("gold", "elixir")


@dataclass(frozen=True)
class Storage:
    current: int | None = None
    maximum: int | None = None
    fill: float | None = None      # fullness measured from the storage bar

    @property
    def fraction(self) -> float | None:
        if self.current is not None and self.maximum:
            return self.current / self.maximum
        return self.fill

    def is_full(self, threshold: float) -> bool:
        """Unknown readings count as not full, so a misread never triggers spending."""
        f = self.fraction
        return f is not None and f >= threshold

    def __str__(self) -> str:
        f = self.fraction
        cap = f"/{self.maximum}" if self.maximum else ""
        return f"{self.current}{cap}" + (f" ({f:.0%})" if f is not None else " (unknown)")


@dataclass(frozen=True)
class HomeState:
    gold: Storage = field(default_factory=Storage)
    elixir: Storage = field(default_factory=Storage)
    dark: Storage = field(default_factory=Storage)
    builders_free: int | None = None
    builders_total: int | None = None

    def storage(self, resource: str) -> Storage:
        return getattr(self, resource)

    def full(self, threshold: float, resources: tuple[str, ...] = RESOURCES) -> list[str]:
        return [r for r in resources if self.storage(r).is_full(threshold)]

    def summary(self) -> str:
        return (f"gold {self.gold}, elixir {self.elixir}, dark {self.dark}, "
                f"builders free {self.builders_free}/{self.builders_total}")

    def as_dict(self) -> dict:
        d = {r: {"current": self.storage(r).current, "max": self.storage(r).maximum,
                 "fraction": self.storage(r).fraction} for r in RESOURCES}
        d["builders"] = {"free": self.builders_free, "total": self.builders_total}
        return d


def checked_storage(current: int | None, maximum: int | None, fill: float | None = None) -> Storage:
    """Drop readings that can't be right (OCR misreads)."""
    if current is not None and maximum is not None and current > maximum * 1.02:
        log.warning("Storage reading %s > max %s looks like an OCR misread; ignoring it.", current, maximum)
        return Storage(None, maximum, fill)
    return Storage(current, maximum, fill)


FILL_HSV = {  # (hue range, min saturation, value range) of each bar's filled part, OpenCV HSV
    "gold": ((15, 35), 150, (150, 255)),
    "elixir": ((135, 170), 120, (120, 255)),
    "dark": ((120, 170), 100, (25, 120)),
}


def _is_fill(pixel: np.ndarray, resource: str) -> bool:
    (h1, h2), min_s, (v1, v2) = FILL_HSV[resource]
    h, s, v = (int(c) for c in pixel)
    return h1 <= h <= h2 and s >= min_s and v1 <= v <= v2


def bar_fill(screen: np.ndarray, icon: Box, resource: str) -> float | None:
    """How full a storage bar is (0..1). Bars fill from the right, under the icon,
    so this walks left from the icon while the pixels are the resource's fill colour.
    Below roughly a quarter the fill is hidden under the icon, so low readings are rough."""
    unit = screen.shape[0]
    cx, cy = icon.center
    left_dx, right_dx = C.BAR_SPAN[resource]
    bar_left, bar_right = cx + left_dx * unit, cx + right_dx * unit
    if bar_right - bar_left < 10:
        return None
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    lefts = []
    for dy in (-0.003, 0.0, 0.003):
        y = int(cy + (C.BAR_ROW + dy) * unit)
        if not 0 <= y < screen.shape[0]:
            continue
        start = int(cx - C.BAR_SCAN_FROM * unit)
        fill_left, gap, x = start, 0, start
        while x > max(bar_left, 0):
            if _is_fill(hsv[y, x], resource):
                fill_left, gap = x, 0
            elif (gap := gap + 1) > 3:
                break
            x -= 1
        lefts.append(fill_left)
    if not lefts:
        return None
    return max(0.0, min(1.0, (bar_right - float(np.median(lefts))) / (bar_right - bar_left)))


def read_storage(screen: np.ndarray, vision: Vision, resource: str) -> Storage:
    icon = vision.find(screen, f"home_{resource}_icon")
    if icon is None:
        return Storage()
    amount_box = resolve_region(C.REGIONS[f"home_{resource}_amount"], screen, vision)
    current = ocr.read_number(crop(screen, amount_box), vision.digits) if amount_box else None
    maximum = C.STORAGE_MAX.get(resource)
    fill = None if maximum else bar_fill(screen, icon.box, resource)
    return checked_storage(current, maximum, fill)


def read_builders(screen: np.ndarray, vision: Vision) -> tuple[int, int] | None:
    box = resolve_region(C.REGIONS["builders_count"], screen, vision)
    if box is None:
        return None
    pair = ocr.parse_fraction(ocr.read_chars(crop(screen, box), vision.digits, whitelist="0123456789/"))
    if pair and pair[0] <= pair[1] <= 10:
        return pair
    return None


def read_home_state(screen: np.ndarray, vision: Vision) -> HomeState:
    builders = read_builders(screen, vision) or (None, None)
    return HomeState(
        *(read_storage(screen, vision, r) for r in RESOURCES),
        builders_free=builders[0], builders_total=builders[1],
    )


# --- decisions (pure, unit tested) -------------------------------------------

def storages_to_spend(state: HomeState, threshold: float = C.STORAGE_THRESHOLD) -> list[str]:
    """Gold/elixir storages full enough that walls should soak up the excess."""
    return state.full(threshold, WALL_RESOURCES)


def farming_stop_reason(state: HomeState, threshold: float = C.STORAGE_THRESHOLD) -> str | None:
    """Why farming should end now, or None to keep going."""
    if state.builders_free == 0 and len(state.full(threshold)) == len(RESOURCES):
        return (f"All builders are busy and gold, elixir and dark elixir are all at or above "
                f"{threshold:.0%} of max, so further attacks would waste loot.")
    return None
