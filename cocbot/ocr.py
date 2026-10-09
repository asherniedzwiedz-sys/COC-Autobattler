"""Text and number reading with Tesseract, tuned for the game's white outlined text."""
from __future__ import annotations

import re
from dataclasses import dataclass

import cv2
import numpy as np

from . import config as C
from .vision import Box

try:
    import pytesseract
except ImportError:  # pragma: no cover - reported by available()
    pytesseract = None

if pytesseract is not None and C.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = str(C.TESSERACT_CMD)

_PAD = 12


class OcrUnavailable(RuntimeError):
    pass


def available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def binarize(img: np.ndarray) -> np.ndarray:
    """Black text on white, upscaled, ready for Tesseract."""
    up = cv2.resize(img, None, fx=C.OCR_UPSCALE, fy=C.OCR_UPSCALE, interpolation=cv2.INTER_CUBIC)
    hsv = cv2.cvtColor(up, cv2.COLOR_BGR2HSV)
    text = (hsv[..., 2] >= C.OCR_TEXT_MIN_VALUE) & (hsv[..., 1] <= C.OCR_TEXT_MAX_SATURATION)
    if text.mean() >= 0.005:
        out = np.where(text, 0, 255).astype(np.uint8)
    else:  # no white text: fall back to Otsu and treat the minority colour as text
        gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
        _, out = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if (out == 255).mean() < 0.5:
            out = 255 - out
    return cv2.copyMakeBorder(out, _PAD, _PAD, _PAD, _PAD, cv2.BORDER_CONSTANT, value=255)


def _tesseract(img: np.ndarray, config: str) -> str:
    if not available():
        raise OcrUnavailable("Tesseract is not installed or not on PATH (see README, or set TESSERACT_CMD).")
    return pytesseract.image_to_string(img, config=config)


def read_text(img: np.ndarray, psm: int = 7, whitelist: str | None = None) -> str:
    config = f"--psm {psm}"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    return _tesseract(binarize(img), config).strip()


def read_number(img: np.ndarray) -> int | None:
    return parse_int(read_text(img, whitelist="0123456789"))


@dataclass(frozen=True)
class Word:
    text: str
    box: Box
    conf: float


def read_words(img: np.ndarray, offset: tuple[int, int] = (0, 0)) -> list[Word]:
    """Every word Tesseract finds, with boxes in screen coordinates."""
    if not available():
        raise OcrUnavailable("Tesseract is not installed or not on PATH.")
    data = pytesseract.image_to_data(binarize(img), config="--psm 11", output_type=pytesseract.Output.DICT)
    s, (ox, oy) = C.OCR_UPSCALE, offset
    words = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        x = (data["left"][i] - _PAD) / s + ox
        y = (data["top"][i] - _PAD) / s + oy
        box = Box.from_corners(x, y, x + data["width"][i] / s, y + data["height"][i] / s)
        words.append(Word(text.strip(), box, float(data["conf"][i])))
    return words


def group_lines(words: list[Word]) -> list[list[Word]]:
    """Group words into text lines (top to bottom, each line left to right)."""
    if not words:
        return []
    tolerance = max(4.0, float(np.median([w.box.h for w in words])) * 0.6)
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: w.box.center[1]):
        if lines and abs(w.box.center[1] - lines[-1][-1].box.center[1]) <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.box.x) for line in lines]


def line_box(line: list[Word]) -> Box:
    return Box.from_corners(min(w.box.x for w in line), min(w.box.y for w in line),
                            max(w.box.x2 for w in line), max(w.box.y2 for w in line))


def line_text(line: list[Word]) -> str:
    return " ".join(w.text for w in line)


# --- parsers (pure functions, unit tested) ---------------------------------

def parse_int(text: str) -> int | None:
    """'1 234 567' / '1,234,567' / '1.234.567' -> 1234567."""
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


def parse_max(text: str) -> int | None:
    """'Max: 24 000 000' -> 24000000."""
    m = re.search(r"max\W*([\d\s.,]+)", text or "", re.IGNORECASE)
    return parse_int(m.group(1)) if m else parse_int(text)


def parse_level(text: str) -> int | None:
    """'Town Hall (Level 18)' -> 18."""
    m = re.search(r"(?:level|lvl|lv)\.?\s*(\d{1,2})", text or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_fraction(text: str) -> tuple[int, int] | None:
    """'2/6' -> (2, 6)."""
    m = re.search(r"(\d+)\s*/\s*(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None
