"""Logging: a human-readable log file plus a JSON-lines event log.

events.jsonl gets one line per attack, wall upgrade, suggested upgrade,
donation, blocked gem path, dry-run action and stop reason.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import cv2
import numpy as np

from . import config as C

log = logging.getLogger("cocbot")


def setup_logging(log_dir: Path | None = None, verbose: bool = False) -> Path:
    log_dir = Path(log_dir or C.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(log_dir / C.LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    log.addHandler(file_handler)
    log.addHandler(console)
    return log_dir


class EventLog:
    def __init__(self, log_dir: Path | None = None):
        self.dir = Path(log_dir or C.LOG_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / C.EVENT_FILE

    def record(self, kind: str, **fields) -> dict:
        event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "type": kind, **fields}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
        return event

    def attack(self, target_th: int | None, loot_gained: dict, trophies_change: int | None, **extra) -> None:
        self.record("attack", target_th=target_th, loot_gained=loot_gained, trophies_change=trophies_change, **extra)
        trophies = f"{trophies_change:+d}" if trophies_change is not None else "unknown"
        log.info("ATTACK vs TH%s: loot %s, trophies %s", target_th or "?", loot_gained, trophies)

    def wall_upgrade(self, resource: str, spent: int | None, dry_run: bool) -> None:
        self.record("wall_upgrade", resource=resource, spent=spent, dry_run=dry_run)
        log.info("WALL UPGRADE with %s (spent %s)%s", resource, spent, " [dry run]" if dry_run else "")

    def suggested_upgrade(self, name: str, resource: str, spent: int | None, dry_run: bool) -> None:
        self.record("suggested_upgrade", name=name, resource=resource, spent=spent, dry_run=dry_run)
        log.info("SUGGESTED UPGRADE %r with %s (spent %s)%s", name, resource, spent, " [dry run]" if dry_run else "")

    def donation(self, taps: dict[str, int], dry_run: bool) -> None:
        self.record("donation", taps=taps, dry_run=dry_run)
        log.info("DONATION taps %s%s", taps, " [dry run]" if dry_run else "")

    def gem_block(self, reason: str) -> None:
        self.record("gem_block", reason=reason)
        log.warning("GEM GUARD blocked an action: %s", reason)

    def dry_run_action(self, action: str, why: str, point: tuple[int, int]) -> None:
        self.record("dry_run_action", action=action, why=why, point=list(point))
        log.info("[DRY RUN] would tap %s for %s: %s", point, action, why)

    def stop(self, reason: str, screen: np.ndarray | None = None) -> None:
        shot = None
        if screen is not None and C.SCREENSHOT_ON_STOP:
            shot = self.dir / f"stop_{time.strftime('%Y%m%d_%H%M%S')}.png"
            cv2.imwrite(str(shot), screen)
        self.record("stop", reason=reason, screenshot=str(shot) if shot else None)
        log.info("STOP: %s", reason)
