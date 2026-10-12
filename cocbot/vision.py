"""Template matching and screen regions.

Templates are small PNG crops captured from your own device (see
templates/README.md). A template may have variants (`btn_close.png`,
`btn_close__2.png`, ...); a match on any variant counts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import config as C


HEIGHTS_FILE = "heights.json"


def record_source_height(template_dir: Path, filename: str, height: int) -> None:
    path = Path(template_dir) / HEIGHTS_FILE
    heights = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    heights[filename] = int(height)
    path.write_text(json.dumps(heights, indent=1, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @staticmethod
    def from_corners(x1: float, y1: float, x2: float, y2: float) -> "Box":
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        return Box(round(x1), round(y1), max(1, round(x2 - x1)), max(1, round(y2 - y1)))

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def contains(self, point: tuple[int, int]) -> bool:
        px, py = point
        return self.x <= px < self.x2 and self.y <= py < self.y2

    def relative(self, dx1: float, dy1: float, dx2: float, dy2: float) -> "Box":
        """A box placed relative to this one, in multiples of this box's width/height."""
        return Box.from_corners(
            self.x + dx1 * self.w, self.y + dy1 * self.h,
            self.x + dx2 * self.w, self.y + dy2 * self.h,
        )

    def pad(self, factor: float) -> "Box":
        """Grow by `factor` of the box size on every side."""
        return self.relative(-factor, -factor, 1 + factor, 1 + factor)

    def clip(self, width: int, height: int) -> "Box | None":
        x1, y1 = max(0, self.x), max(0, self.y)
        x2, y2 = min(width, self.x2), min(height, self.y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return Box(x1, y1, x2 - x1, y2 - y1)

    def iou(self, other: "Box") -> float:
        ix = max(0, min(self.x2, other.x2) - max(self.x, other.x))
        iy = max(0, min(self.y2, other.y2) - max(self.y, other.y))
        inter = ix * iy
        union = self.w * self.h + other.w * other.h - inter
        return inter / union if union else 0.0


@dataclass(frozen=True)
class Match:
    name: str
    box: Box
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.box.center


def crop(screen: np.ndarray, box: Box) -> np.ndarray:
    return screen[box.y:box.y2, box.x:box.x2]


class Vision:
    def __init__(self, template_dir: Path | str | None = None, threshold: float | None = None,
                 scales: tuple[float, ...] | None = None):
        self.dir = Path(template_dir or C.TEMPLATE_DIR)
        self.threshold = C.MATCH_THRESHOLD if threshold is None else threshold
        self.scales = tuple(scales or C.TEMPLATE_SCALES)
        self._cache: dict[str, list[np.ndarray]] = {}
        self._digits = None

    @property
    def digits(self):
        """DigitReader for templates/digits/ (number reading)."""
        if self._digits is None:
            from .digits import DigitReader
            self._digits = DigitReader(self.dir / "digits")
        return self._digits

    def variant_paths(self, name: str) -> list[Path]:
        base = self.dir / f"{name}.png"
        return ([base] if base.exists() else []) + sorted(self.dir.glob(f"{name}__*.png"))

    def has(self, name: str) -> bool:
        return bool(self.variant_paths(name))

    def names_with_prefix(self, prefix: str) -> list[str]:
        return sorted({p.stem.split("__")[0] for p in self.dir.glob(f"{prefix}*.png")})

    def source_heights(self) -> dict[str, int]:
        """Screen height each template was cut at (templates/heights.json), so a template
        cut on one device is rescaled to match another (the game's UI scales with height)."""
        path = self.dir / HEIGHTS_FILE
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def templates(self, name: str) -> list[tuple[np.ndarray, int | None]]:
        """Each variant of `name` with the screen height it was cut at (None if unknown)."""
        if name not in self._cache:
            heights = self.source_heights()
            images = []
            for path in self.variant_paths(name):
                img = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if img is None:
                    raise ValueError(f"Unreadable template {path}")
                images.append((img, heights.get(path.name)))
            self._cache[name] = images
        return self._cache[name]

    def find_all(self, screen: np.ndarray, name: str, region: Box | None = None,
                 threshold: float | None = None, limit: int = 20) -> list[Match]:
        """Every non-overlapping match of `name`, best first."""
        threshold = self.threshold if threshold is None else threshold
        area, ox, oy = screen, 0, 0
        if region is not None:
            region = region.clip(screen.shape[1], screen.shape[0])
            if region is None:
                return []
            area, ox, oy = crop(screen, region), region.x, region.y
        found: list[Match] = []
        for tpl, source_height in self.templates(name):
            base = screen.shape[0] / source_height if source_height else 1.0
            for scale in self.scales:
                s = base * scale
                t = tpl if abs(s - 1.0) < 0.01 else cv2.resize(tpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                th, tw = t.shape[:2]
                if th < 4 or tw < 4 or th > area.shape[0] or tw > area.shape[1]:
                    continue
                res = cv2.matchTemplate(area, t, cv2.TM_CCOEFF_NORMED)
                res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
                ys, xs = np.where(res >= threshold)
                if len(xs) > 500:
                    best = np.argsort(res[ys, xs])[::-1][:500]
                    ys, xs = ys[best], xs[best]
                found += [Match(name, Box(int(x) + ox, int(y) + oy, tw, th), float(res[y, x]))
                          for y, x in zip(ys, xs)]
        return _non_max_suppression(found, limit)

    def find(self, screen: np.ndarray, name: str, region: Box | None = None,
             threshold: float | None = None) -> Match | None:
        matches = self.find_all(screen, name, region, threshold, limit=1)
        return matches[0] if matches else None


def _non_max_suppression(matches: list[Match], limit: int) -> list[Match]:
    kept: list[Match] = []
    for m in sorted(matches, key=lambda m: m.score, reverse=True):
        if all(m.box.iou(k.box) < 0.3 for k in kept):
            kept.append(m)
            if len(kept) >= limit:
                break
    return kept


def resolve_region(spec: tuple, screen: np.ndarray, vision: Vision) -> Box | None:
    """Turn a REGIONS entry into a pixel box on this screen (None if its anchor icon isn't visible)."""
    h, w = screen.shape[:2]
    kind = spec[0]
    if kind == "screen":
        _, x1, y1, x2, y2 = spec
        return Box.from_corners(x1 * w, y1 * h, x2 * w, y2 * h).clip(w, h)
    if kind == "icon":
        _, name, dx1, dy1, dx2, dy2 = spec
        anchor = vision.find(screen, name)
        if anchor is None:
            return None
        return anchor.box.relative(dx1, dy1, dx2, dy2).clip(w, h)
    raise ValueError(f"Unknown region kind {kind!r}")


def is_price_red(screen: np.ndarray, icon: Box) -> bool:
    """True if the price text next to a resource icon is red (the game's 'can't afford')."""
    area = icon.relative(-4.0, 0.0, 0.0, 1.0).clip(screen.shape[1], screen.shape[0])
    if area is None:
        return False
    b, g, r = (crop(screen, area).astype(int)[..., i] for i in range(3))
    red = ((r > 170) & (g < 100) & (b < 100)).sum()
    white = ((r > 200) & (g > 200) & (b > 200)).sum()
    return red > 25 and red > white
