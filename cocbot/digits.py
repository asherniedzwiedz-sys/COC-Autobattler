"""Reading numbers by matching each character against glyphs cut from your own screen.

Tesseract misreads the game's font (it drops zeros and reads 8 as 3), so numbers
are read by splitting the binarized text into glyphs and matching each one
against templates/digits/<char>.png. Glyphs are compared at a normalized size,
so templates cut at one resolution work at another.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config as C
from .ocr import binarize
from .vision import Box

CHAR_NAMES = {**{d: d for d in "0123456789"}, "/": "slash"}
GLYPH_SIZE = 32


def glyph_boxes(binary: np.ndarray) -> list[Box]:
    """Character boxes in a black-on-white image, left to right."""
    ink = (binary == 0).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    # solid shapes only: digits fill a good part of their box, stray outlines don't
    boxes = [Box(*map(int, stats[i][:4])) for i in range(1, n)
             if stats[i][4] >= 12 and stats[i][4] >= 0.2 * stats[i][2] * stats[i][3]]
    if not boxes:
        return []
    tallest = max(b.h for b in boxes)
    boxes = [b for b in boxes if b.h >= 0.5 * tallest]
    typical = float(np.median([b.h for b in boxes]))
    # drop specks and stray frame edges much taller than the characters
    boxes = sorted((b for b in boxes if 0.7 * typical <= b.h <= 1.4 * typical), key=lambda b: b.x)
    merged: list[Box] = []
    for b in boxes:  # rejoin glyphs that binarized into stacked pieces
        last = merged[-1] if merged else None
        if last and min(last.x2, b.x2) - max(last.x, b.x) > 0.5 * min(last.w, b.w):
            merged[-1] = Box.from_corners(min(last.x, b.x), min(last.y, b.y), max(last.x2, b.x2), max(last.y2, b.y2))
        else:
            merged.append(b)
    return merged


def normalize(binary: np.ndarray, box: Box) -> np.ndarray:
    """A glyph scaled to a fixed height on a square canvas, aspect ratio kept."""
    ink = 255 - binary[box.y:box.y2, box.x:box.x2]
    scale = GLYPH_SIZE / max(box.h, box.w)
    w, h = max(1, round(box.w * scale)), max(1, round(box.h * scale))
    canvas = np.zeros((GLYPH_SIZE, GLYPH_SIZE), np.float32)
    x0, y0 = (GLYPH_SIZE - w) // 2, (GLYPH_SIZE - h) // 2
    canvas[y0:y0 + h, x0:x0 + w] = cv2.resize(ink, (w, h), interpolation=cv2.INTER_AREA) / 255.0
    return cv2.GaussianBlur(canvas, (3, 3), 0)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0, 0])


class DigitReader:
    def __init__(self, directory: Path | str):
        self.dir = Path(directory)
        self.templates: dict[str, list[np.ndarray]] = {}
        for char, name in CHAR_NAMES.items():
            paths = ([self.dir / f"{name}.png"] if (self.dir / f"{name}.png").exists() else []) \
                + sorted(self.dir.glob(f"{name}__*.png"))
            for path in paths:
                img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
                    box = Box.from_corners(*_ink_bounds(img))
                    self.templates.setdefault(char, []).append(normalize(img, box))

    def ready(self) -> bool:
        """True once every digit 0-9 has a template."""
        return all(d in self.templates for d in "0123456789")

    def classify(self, glyph: np.ndarray) -> tuple[str | None, float]:
        best, best_score = None, -1.0
        for char, variants in self.templates.items():
            for t in variants:
                score = similarity(glyph, t)
                if score > best_score:
                    best, best_score = char, score
        return best, best_score

    def read(self, img: np.ndarray) -> str | None:
        """The characters in `img`, or None if any glyph isn't a confident match
        (so a misread can never turn into a wrong number)."""
        binary = binarize(img)
        boxes = glyph_boxes(binary)
        found = [(box, *self.classify(normalize(binary, box))) for box in boxes]
        found = _trim_junk(found)
        if not found or any(char is None or score < C.DIGIT_MATCH_THRESHOLD for _, char, score in found):
            return None
        return "".join(char for _, char, _ in found)

    def save_glyphs(self, img: np.ndarray, text: str) -> list[Path]:
        """Cut each character of `text` (as shown in `img`) out as a template."""
        wanted = [c for c in text if not c.isspace()]
        unknown = [c for c in wanted if c not in CHAR_NAMES]
        if unknown:
            raise ValueError(f"only digits and '/' can be saved, not {unknown}")
        binary = binarize(img)
        boxes = glyph_boxes(binary)
        if len(boxes) != len(wanted):
            raise ValueError(f"found {len(boxes)} characters in the box but the text has {len(wanted)}")
        self.dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for char, box in zip(wanted, boxes):
            name = CHAR_NAMES[char]
            path, n = self.dir / f"{name}.png", 2
            while path.exists():
                path, n = self.dir / f"{name}__{n}.png", n + 1
            pad = cv2.copyMakeBorder(binary[box.y:box.y2, box.x:box.x2], 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=255)
            cv2.imwrite(str(path), pad)
            saved.append(path)
        self.__init__(self.dir)
        return saved


def _trim_junk(found: list[tuple[Box, str | None, float]]) -> list[tuple[Box, str | None, float]]:
    """Drop background blobs at either end of the text: clearly not a character
    (score under 0.5) and set apart from the rest by at least a character's width."""
    if len(found) < 2:
        return found
    width = float(np.median([box.w for box, _, _ in found]))
    while len(found) > 1 and found[0][2] < 0.5 and found[1][0].x - found[0][0].x2 >= 0.8 * width:
        found = found[1:]
    while len(found) > 1 and found[-1][2] < 0.5 and found[-1][0].x - found[-2][0].x2 >= 0.8 * width:
        found = found[:-1]
    return found


def _ink_bounds(binary: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(binary == 0)
    if len(xs) == 0:
        return 0, 0, binary.shape[1], binary.shape[0]
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
