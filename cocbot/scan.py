"""Phase 1 scan: capture the account's Town Hall, troop, spell and hero levels.

Guided and read-only: you open each screen yourself, the bot takes the
screenshot. It never taps, so it can't start research, train troops or spend
anything. It OCRs what it can (Town Hall level, storages, builders) and saves
every screenshot so the army proposal can be checked against the real levels.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable

import cv2

from . import config as C
from . import ocr
from .device import Device
from .state import read_home_state
from .templates_spec import FEATURE_REQUIREMENTS
from .vision import Vision, crop, resolve_region

log = logging.getLogger("cocbot")

STEPS = [
    ("home", "Go to your home village with no windows open."),
    ("town_hall", "Tap your Town Hall once so its name and level show at the bottom. Don't press any button."),
    ("army", "Open the Army window (Army tab) so your heroes, troops and spells show."),
    ("train_troops", "Switch to the Train Troops tab. Don't tap any troop."),
    ("train_troops_more", "If some troops are off screen, scroll the list sideways (Enter to skip)."),
    ("brew_spells", "Switch to the Brew Spells tab. Don't tap any spell."),
    ("siege", "Switch to the Siege Machines tab, if you have one (Enter to skip)."),
    ("heroes", "Close the Army window and open the Hero Hall (or tap each hero) so hero levels and "
               "equipment show."),
    ("heroes_more", "Optional: another hero/equipment screen (Enter to skip)."),
]


def read_town_hall_level(screen, vision: Vision) -> tuple[int | None, str]:
    box = resolve_region(C.REGIONS["selected_name"], screen, vision)
    text = ocr.read_text(crop(screen, box)) if box else ""
    if "town" not in text.lower():
        # fall back to the whole bottom half, in case the region needs calibrating
        h = screen.shape[0]
        text = ocr.read_text(screen[h // 2:], psm=11)
        found = [line for line in text.splitlines() if "town" in line.lower()]
        text = found[0] if found else ""
    return ocr.parse_level(text), text


def run_scan(device: Device, vision: Vision, out_root: Path | None = None,
             input_fn: Callable[[str], str] = input) -> Path:
    out = Path(out_root or C.SCAN_DIR) / time.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"device": device.describe(), "screens": {}}
    ocr_ok = ocr.available()
    if not ocr_ok:
        log.warning("Tesseract not found: saving screenshots only, no text readings.")
    print(f"\nPhase 1 scan. Follow each step on the device, then press Enter here.\nSaving to {out}\n")
    for key, instruction in STEPS:
        answer = input_fn(f"[{key}] {instruction}\n  Enter = capture, s = skip: ")
        if answer.strip().lower().startswith("s"):
            continue
        screen = device.screenshot()
        path = out / f"{key}.png"
        cv2.imwrite(str(path), screen)
        entry: dict = {"file": path.name, "size": [screen.shape[1], screen.shape[0]]}
        if ocr_ok and key == "town_hall":
            level, text = read_town_hall_level(screen, vision)
            entry.update(town_hall_level=level, ocr_text=text)
            print(f"  Town Hall level read: {level if level else 'not readable'} ({text!r})")
        if ocr_ok and key == "home" and all(vision.has(n) for n in FEATURE_REQUIREMENTS["storage"]):
            state = read_home_state(screen, vision)
            entry["home_state"] = state.as_dict()
            print(f"  {state.summary()}")
        report["screens"][key] = entry
        print(f"  saved {path.name}")
    th = report["screens"].get("town_hall", {}).get("town_hall_level")
    report["town_hall_level"] = th
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "report.md").write_text(_markdown(report), encoding="utf-8")
    print(f"\nDone. Send me the folder {out} (commit it, or attach the screenshots) "
          f"so I can read the troop, spell and hero levels and propose the army.")
    return out


def _markdown(report: dict) -> str:
    lines = ["# Phase 1 scan", "", f"- Device: {report['device']}",
             f"- Town Hall level (OCR): {report.get('town_hall_level') or 'not read'}", ""]
    for key, entry in report["screens"].items():
        lines.append(f"## {key}")
        lines.append(f"![{key}]({entry['file']})")
        for k, v in entry.items():
            if k != "file":
                lines.append(f"- {k}: {v}")
        lines.append("")
    return "\n".join(lines)
