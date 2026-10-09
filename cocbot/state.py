"""Reading the home village: storages and builders, plus the decisions built on them."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from . import config as C
from . import ocr
from .vision import Vision, crop, resolve_region

log = logging.getLogger("cocbot")

RESOURCES = ("gold", "elixir", "dark")
WALL_RESOURCES = ("gold", "elixir")


@dataclass(frozen=True)
class Storage:
    current: int | None = None
    maximum: int | None = None

    @property
    def fraction(self) -> float | None:
        if self.current is None or not self.maximum:
            return None
        return self.current / self.maximum

    def is_full(self, threshold: float) -> bool:
        """Unknown readings count as not full, so a misread never triggers spending."""
        f = self.fraction
        return f is not None and f >= threshold

    def __str__(self) -> str:
        f = self.fraction
        return f"{self.current}/{self.maximum}" + (f" ({f:.0%})" if f is not None else " (unknown)")


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
        d = {r: {"current": self.storage(r).current, "max": self.storage(r).maximum} for r in RESOURCES}
        d["builders"] = {"free": self.builders_free, "total": self.builders_total}
        return d


def checked_storage(current: int | None, maximum: int | None) -> Storage:
    """Drop readings that can't be right (OCR misreads)."""
    if current is not None and maximum is not None and current > maximum * 1.02:
        log.warning("Storage reading %s > max %s looks like an OCR misread; ignoring it.", current, maximum)
        return Storage(None, maximum)
    return Storage(current, maximum)


def read_storage(screen: np.ndarray, vision: Vision, resource: str) -> Storage:
    amount_box = resolve_region(C.REGIONS[f"home_{resource}_amount"], screen, vision)
    max_box = resolve_region(C.REGIONS[f"home_{resource}_max"], screen, vision)
    current = ocr.read_number(crop(screen, amount_box)) if amount_box else None
    maximum = C.STORAGE_MAX.get(resource)
    if maximum is None and max_box is not None:
        maximum = ocr.parse_max(ocr.read_text(crop(screen, max_box)))
    return checked_storage(current, maximum)


def read_builders(screen: np.ndarray, vision: Vision) -> tuple[int, int] | None:
    box = resolve_region(C.REGIONS["builders_count"], screen, vision)
    if box is None:
        return None
    pair = ocr.parse_fraction(ocr.read_text(crop(screen, box), whitelist="0123456789/"))
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
