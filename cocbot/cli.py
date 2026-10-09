"""Command line entry point: `python -m cocbot <command>`."""
from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path
from typing import Callable

import cv2

from . import config as C
from . import ocr
from .bot import Bot
from .device import ImageDevice, find_adb, list_adb_devices, open_device
from .errors import DeviceError
from .farmer import Farmer
from .logbook import EventLog, setup_logging
from .scan import run_scan
from .templates_spec import report as templates_report
from .vision import Vision, crop, resolve_region

log = logging.getLogger("cocbot")


def ask_yes_no(prompt: str, input_fn: Callable[[str], str] = input) -> bool:
    while True:
        answer = input_fn(prompt).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer yes or no.")


def cmd_devices(args) -> int:
    if C.DEVICE == "android":
        try:
            adb = find_adb()
            print(f"adb: {adb}")
            print(f"adb devices: {list_adb_devices(adb) or 'none'}")
        except DeviceError as e:
            print(e)
            return 1
    try:
        device = open_device()
        screen = device.screenshot()
        print(f"Connected: {device.describe()}, screen {screen.shape[1]}x{screen.shape[0]}, "
              f"app in front: {device.foreground_app()}")
        if screen.shape[0] > screen.shape[1]:
            print("Screen is portrait: open Clash of Clans so it's in landscape before running the bot.")
    except DeviceError as e:
        print(f"Device not ready: {e}")
        return 1
    print(f"Tesseract OCR: {'found' if ocr.available() else 'NOT FOUND (install it or set TESSERACT_CMD)'}")
    return 0


def cmd_screenshot(args) -> int:
    out = Path(args.out or C.PROJECT_ROOT / "screenshots" / f"{time.strftime('%Y%m%d_%H%M%S')}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), open_device().screenshot())
    print(f"Saved {out}")
    return 0


def cmd_crop(args) -> int:
    if not re.fullmatch(r"[a-z0-9_]+", args.name):
        print("Template names use lowercase letters, digits and _ only (e.g. res_gem, btn_close).")
        return 1
    image = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if image is None:
        print(f"Cannot read {args.image}")
        return 1
    if args.box:
        x, y, w, h = (int(v) for v in args.box.split(","))
    else:
        scale = min(1.0, 1600 / image.shape[1], 900 / image.shape[0])
        shown = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
        try:
            rx, ry, rw, rh = cv2.selectROI(f"Drag a box around '{args.name}', then Enter", shown, False)
            cv2.destroyAllWindows()
        except cv2.error:
            print("No window support in this OpenCV build; pass --box x,y,w,h instead.")
            return 1
        x, y, w, h = (round(v / scale) for v in (rx, ry, rw, rh))
    if w < 4 or h < 4:
        print("Selection too small; nothing saved.")
        return 1
    C.TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    out = C.TEMPLATE_DIR / f"{args.name}.png"
    n = 2
    while out.exists() and not args.replace:
        out = C.TEMPLATE_DIR / f"{args.name}__{n}.png"
        n += 1
    cv2.imwrite(str(out), image[y:y + h, x:x + w])
    print(f"Saved {out} ({w}x{h})")
    return 0


def cmd_calibrate(args) -> int:
    device = ImageDevice(args.image) if args.image else open_device()
    screen = device.screenshot()
    vision = Vision()
    canvas = screen.copy()
    print("Templates found on this screen:")
    names = sorted({p.stem.split("__")[0] for p in vision.dir.glob("*.png")})
    for name in names:
        for m in vision.find_all(screen, name):
            cv2.rectangle(canvas, (m.box.x, m.box.y), (m.box.x2, m.box.y2), (0, 255, 0), 2)
            cv2.putText(canvas, f"{name} {m.score:.2f}", (m.box.x, max(12, m.box.y - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            print(f"  {name:<24} at {m.center} score {m.score:.2f}")
    print("Text regions:")
    for key, spec in C.REGIONS.items():
        box = resolve_region(spec, screen, vision)
        if box is None:
            print(f"  {key:<20} (anchor '{spec[1]}' not on screen)")
            continue
        text = ocr.read_text(crop(screen, box)) if ocr.available() else "(no OCR)"
        cv2.rectangle(canvas, (box.x, box.y), (box.x2, box.y2), (0, 200, 255), 2)
        cv2.putText(canvas, key, (box.x, box.y2 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
        print(f"  {key:<20} {box} -> {text!r}")
    out = C.LOG_DIR / "calibration.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas)
    print(f"Saved {out}: green = template matches, orange = text regions. Adjust REGIONS in config.py "
          f"until each orange box covers its text.")
    return 0


def cmd_templates(args) -> int:
    print(templates_report(Vision()))
    return 0


def cmd_scan(args) -> int:
    run_scan(open_device(), Vision())
    return 0


def cmd_run(args, input_fn: Callable[[str], str] = input) -> int:
    dry_run = (C.DRY_RUN and not args.live) or args.step
    auto_donate = ask_yes_no("Auto-donate to clan mate requests? (yes/no) ", input_fn)
    events = EventLog()
    events.record("start", dry_run=dry_run, step=args.step, auto_donate=auto_donate)
    log.info("Mode: %s; donations %s.", ("step-by-step dry run" if args.step else "dry run") if dry_run else "LIVE",
             "ON (elixir/dark elixir troops only)" if auto_donate else "OFF (clan chat untouched)")
    if not ocr.available():
        log.error("Tesseract OCR not found; install it or set TESSERACT_CMD in config.py.")
        return 1
    device = open_device()
    vision = Vision()
    log.info("Device: %s", device.describe())
    log.info("\n%s", templates_report(vision))
    if not dry_run and input_fn("LIVE mode taps for real. Type 'live' to continue: ").strip().lower() != "live":
        print("Cancelled.")
        return 1
    bot = Bot(device, vision, events, dry_run=dry_run, auto_donate=auto_donate, step=args.step, input_fn=input_fn)
    Farmer(bot).run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cocbot", description="Clash of Clans farming bot")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logging on the console")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="check the device connection and Tesseract")
    p = sub.add_parser("screenshot", help="save the current screen (for cutting templates)")
    p.add_argument("-o", "--out")
    p = sub.add_parser("crop", help="cut a template out of a screenshot")
    p.add_argument("image")
    p.add_argument("name", help="template name, e.g. res_gem")
    p.add_argument("--box", help="x,y,w,h in pixels instead of dragging a box with the mouse")
    p.add_argument("--replace", action="store_true", help="overwrite instead of adding a variant")
    p = sub.add_parser("calibrate", help="draw template matches and text regions with their readings")
    p.add_argument("--image", help="use a saved screenshot instead of the live screen")
    sub.add_parser("templates", help="list which features have the templates they need")
    sub.add_parser("scan", help="Phase 1: capture Town Hall, troop, spell and hero levels")
    p = sub.add_parser("run", help="run the bot (dry run unless --live)")
    p.add_argument("--live", action="store_true", help="really tap (overrides DRY_RUN in config.py)")
    p.add_argument("--step", action="store_true", help="dry run where you make the navigation taps yourself")
    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose)
    commands = {"devices": cmd_devices, "screenshot": cmd_screenshot, "crop": cmd_crop,
                "calibrate": cmd_calibrate, "templates": cmd_templates, "scan": cmd_scan, "run": cmd_run}
    try:
        return commands[args.command](args)
    except DeviceError as e:
        log.error("%s", e)
        return 1
