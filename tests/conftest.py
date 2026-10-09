"""Shared fixtures: synthetic screens and icons so the logic can be tested without a device."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from cocbot import config
from cocbot.bot import Bot
from cocbot.device import Device
from cocbot.logbook import EventLog
from cocbot.vision import Vision

W, H = 1280, 720
GAME = config.GAME_PACKAGE_ANDROID


def make_icon(kind: str, size: int = 36) -> np.ndarray:
    img = np.full((size, size, 3), 35, np.uint8)
    c = size // 2
    if kind == "gem":
        pts = np.array([[c, 3], [size - 4, c], [c, size - 4], [3, c]], np.int32)
        cv2.fillPoly(img, [pts], (60, 220, 60))
        cv2.line(img, (c, 3), (c, size - 4), (200, 255, 200), 2)
    elif kind == "gold":
        cv2.circle(img, (c, c), c - 3, (0, 200, 255), -1)
        cv2.rectangle(img, (c - 4, c - 8), (c + 4, c + 8), (0, 120, 170), -1)
    elif kind == "elixir":
        cv2.ellipse(img, (c, c + 3), (c - 6, c - 3), 0, 0, 360, (200, 60, 230), -1)
        cv2.rectangle(img, (c - 3, 2), (c + 3, c), (240, 180, 250), -1)
    elif kind == "dark":
        cv2.circle(img, (c, c), c - 3, (90, 20, 70), -1)
        cv2.circle(img, (c, c), c - 9, (200, 150, 220), 3)
    elif kind == "close":
        cv2.rectangle(img, (3, 3), (size - 4, size - 4), (30, 30, 220), -1)
        cv2.line(img, (9, 9), (size - 10, size - 10), (255, 255, 255), 4)
        cv2.line(img, (size - 10, 9), (9, size - 10), (255, 255, 255), 4)
    elif kind == "trap":
        cv2.rectangle(img, (2, 2), (size - 3, size - 3), (220, 120, 20), -1)
        for x in range(4, size, 8):
            cv2.line(img, (x, 2), (x, size - 3), (0, 240, 240), 2)
    elif kind == "shop":
        cv2.rectangle(img, (4, 10), (size - 5, size - 5), (20, 120, 220), -1)
        cv2.circle(img, (c, 10), 7, (240, 240, 240), 3)
    elif kind == "builder":
        cv2.rectangle(img, (3, 3), (size - 4, size - 4), (40, 90, 160), -1)
        cv2.rectangle(img, (8, 8), (size - 9, 14), (180, 180, 180), -1)
        cv2.rectangle(img, (c - 2, 14), (c + 2, size - 6), (180, 180, 180), -1)
    elif kind.startswith("troop"):
        seed = sum(map(ord, kind))
        rng = np.random.default_rng(seed)
        img = rng.integers(0, 255, (size, size, 3), dtype=np.uint8)
    else:
        raise ValueError(kind)
    return img


TEMPLATE_KINDS = {
    "res_gem": "gem", "res_gold": "gold", "res_elixir": "elixir", "res_dark": "dark",
    "btn_close": "close", "trap_not_enough": "trap", "forbid_shop": "shop",
    "builder_icon": "builder", "donate_dragon": "troop_dragon", "donate_balloon": "troop_balloon",
}


def make_screen(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    ramp = np.linspace(60, 120, W, dtype=np.float32)[None, :, None]
    base = np.broadcast_to(ramp, (H, W, 3)) + rng.normal(0, 6, (H, W, 3))
    return np.clip(base, 0, 255).astype(np.uint8)


def paste(screen: np.ndarray, img: np.ndarray, x: int, y: int) -> np.ndarray:
    h, w = img.shape[:2]
    screen[y:y + h, x:x + w] = img
    return screen


def draw_text(screen: np.ndarray, text: str, x: int, y: int, scale: float = 0.8, colour=(255, 255, 255)):
    """White game-style text with a dark outline; (x, y) is the baseline start."""
    font = cv2.FONT_HERSHEY_DUPLEX
    cv2.putText(screen, text, (x, y), font, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(screen, text, (x, y), font, scale, colour, 2, cv2.LINE_AA)
    return screen


class SequenceDevice(Device):
    """Returns the given screens in order (the last one repeats) and records taps."""

    def __init__(self, *screens: np.ndarray, foreground: str | None = GAME):
        self.screens = list(screens)
        self.index = 0
        self.foreground = foreground
        self.taps: list[tuple[int, int]] = []
        self.swipes: list[tuple] = []
        self.backs = 0

    def screenshot(self) -> np.ndarray:
        screen = self.screens[min(self.index, len(self.screens) - 1)]
        self.index += 1
        return screen.copy()

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, x1, y1, x2, y2, duration_ms=300) -> None:
        self.swipes.append((x1, y1, x2, y2))

    def foreground_app(self):
        return self.foreground

    def press_back(self) -> bool:
        self.backs += 1
        return True


class TapDevice(SequenceDevice):
    """Shows screens[n] after n taps (the last one repeats): each tap moves the game on."""

    def screenshot(self) -> np.ndarray:
        return self.screens[min(len(self.taps), len(self.screens) - 1)].copy()


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(config, "TAP_SETTLE", 0)
    monkeypatch.setattr(config, "SWIPE_SETTLE", 0)
    monkeypatch.setattr(config, "DEPLOY_TAP_DELAY", 0)
    monkeypatch.setattr(config, "HERO_DELAY", 0)
    monkeypatch.setattr(config, "ZAP_DELAY", 0)
    monkeypatch.setattr(config, "SAVE_SEARCH_SCREENSHOTS", False)


@pytest.fixture
def template_dir(tmp_path):
    d = tmp_path / "templates"
    d.mkdir()
    for name, kind in TEMPLATE_KINDS.items():
        cv2.imwrite(str(d / f"{name}.png"), make_icon(kind))
    return d


@pytest.fixture
def vision(template_dir):
    return Vision(template_dir)


@pytest.fixture
def events(tmp_path):
    return EventLog(tmp_path / "logs")


@pytest.fixture
def make_bot(vision, events):
    def _make(*screens, dry_run=False, auto_donate=False, step=False, inputs=(), foreground=GAME):
        device = SequenceDevice(*(screens or (make_screen(),)), foreground=foreground)
        answers = iter(inputs)
        bot = Bot(device, vision, events, dry_run=dry_run, auto_donate=auto_donate, step=step,
                  input_fn=lambda prompt: next(answers))
        return bot, device
    return _make
