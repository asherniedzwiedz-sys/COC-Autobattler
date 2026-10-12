"""Device control: Android over ADB (phones and emulators) and experimental iPhone.

The bot only uses three primitives: screenshot, tap and swipe (plus reading
which app is in front). There is deliberately no text-input method, so the
bot has no way to type into clan chat.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np

from . import config as C
from .errors import DeviceError

log = logging.getLogger("cocbot")


class Device(ABC):
    @abstractmethod
    def screenshot(self) -> np.ndarray:
        """Return the current screen as a BGR image."""

    @abstractmethod
    def tap(self, x: int, y: int) -> None: ...

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None: ...

    def foreground_app(self) -> str | None:
        """Package/bundle id (or window name) of the focused app; None if unknown."""
        return None

    def press_back(self) -> bool:
        """Send the system Back key. Returns False where there is none (iPhone)."""
        return False

    def describe(self) -> str:
        return type(self).__name__


def adb_candidates() -> list[str]:
    """Where adb usually lives: Android platform-tools, or the copy an emulator ships with."""
    local = os.environ.get("LOCALAPPDATA", "")
    return [
        r"C:\platform-tools\adb.exe",
        str(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe") if local else "",
        r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        r"C:\Program Files\BlueStacks\HD-Adb.exe",
        r"C:\LDPlayer\LDPlayer9\adb.exe",
        r"C:\Program Files\Microvirt\MEmu\adb.exe",
        r"C:\Program Files\Nox\bin\nox_adb.exe",
        r"C:\Program Files (x86)\Nox\bin\nox_adb.exe",
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
        str(Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb"),
    ]


def find_adb(adb_path: str | None = None) -> str:
    adb = adb_path or C.ADB_PATH or shutil.which("adb")
    if adb and (Path(adb).exists() or shutil.which(adb)):
        return adb
    for candidate in adb_candidates():
        if candidate and Path(candidate).exists():
            return candidate
    raise DeviceError(
        "adb not found. Install BlueStacks 5 (it includes adb) or Android platform-tools, "
        "or set ADB_PATH in cocbot/config.py."
    )


def autoconnect_emulator(adb: str) -> str | None:
    """Try the usual emulator addresses; return the first one that connects as a device."""
    for address in C.EMULATOR_AUTO_ADDRESSES:
        try:
            out = subprocess.run([adb, "connect", address], capture_output=True, text=True, timeout=5).stdout
        except subprocess.TimeoutExpired:
            continue
        if "connected to" in out and list_adb_devices(adb).get(address) == "device":
            log.info("Found an emulator at %s.", address)
            return address
    return None


def list_adb_devices(adb: str) -> dict[str, str]:
    """Map serial -> state ("device", "unauthorized", "offline", ...)."""
    out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=20).stdout
    devices = {}
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices[parts[0]] = parts[1]
    return devices


class AdbDevice(Device):
    """A physical Android phone (USB or Wi-Fi debugging) or an Android emulator."""

    def __init__(self, serial: str | None = None, adb_path: str | None = None):
        self.adb = find_adb(adb_path)
        if serial and ":" in serial:
            self._connect(serial)
        self.serial = self._resolve_serial(serial)

    def _connect(self, address: str) -> None:
        proc = subprocess.run([self.adb, "connect", address], capture_output=True, text=True, timeout=20)
        if "connected" not in proc.stdout:
            raise DeviceError(f"adb connect {address} failed: {(proc.stdout + proc.stderr).strip()}")

    def _resolve_serial(self, serial: str | None) -> str:
        devices = list_adb_devices(self.adb)
        if serial:
            state = devices.get(serial)
            if state is None:
                raise DeviceError(f"Device {serial} not found by `adb devices` (found: {devices or 'none'}).")
            if state != "device":
                raise DeviceError(_state_hint(serial, state))
            return serial
        ready = [s for s, st in devices.items() if st == "device"]
        if len(ready) == 1:
            return ready[0]
        if not ready:
            for s, st in devices.items():
                raise DeviceError(_state_hint(s, st))
            raise DeviceError(
                "No Android device found. Plug the phone in with USB debugging on "
                "(or start the emulator and enable its ADB option), then check `adb devices`."
            )
        raise DeviceError(f"Several devices connected ({', '.join(ready)}); set ADB_SERIAL in config.py.")

    def _run(self, *args: str, timeout: float = 20, binary: bool = False):
        cmd = [self.adb, "-s", self.serial, *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise DeviceError(f"adb {' '.join(args)} timed out") from e
        if proc.returncode != 0:
            raise DeviceError(f"adb {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()}")
        return proc.stdout if binary else proc.stdout.decode(errors="replace")

    def screenshot(self) -> np.ndarray:
        for _ in range(C.SCREENSHOT_RETRIES):
            data = self._run("exec-out", "screencap", "-p", binary=True)
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                return img
            time.sleep(0.5)
        raise DeviceError("Could not decode a screenshot from the device.")

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "input", "tap", str(int(x)), str(int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._run("shell", "input", "swipe", *(str(int(v)) for v in (x1, y1, x2, y2, duration_ms)))

    def foreground_app(self) -> str | None:
        return parse_focused_window(self._run("shell", "dumpsys", "window"))

    def press_back(self) -> bool:
        self._run("shell", "input", "keyevent", "4")
        return True

    def describe(self) -> str:
        return f"Android device {self.serial}"


def _state_hint(serial: str, state: str) -> str:
    if state == "unauthorized":
        return f"{serial} is unauthorized: unlock the phone and accept the 'Allow USB debugging' prompt."
    return f"{serial} is {state}; reconnect it (unplug/replug, or restart the emulator)."


def parse_focused_window(dumpsys: str) -> str | None:
    """Pull the focused app's package (or window name) out of `dumpsys window`."""
    for key in ("mCurrentFocus", "mFocusedApp"):
        for line in dumpsys.splitlines():
            if key not in line or "null" in line.split(key, 1)[1][:6]:
                continue
            m = re.search(r"\bu\d+\s+([^\s/}]+)", line)
            if m:
                return m.group(1)
    return None


class WdaDevice(Device):
    """EXPERIMENTAL iPhone control through WebDriverAgent (`pip install facebook-wda`).

    WebDriverAgent must already be running on the phone and reachable at
    WDA_URL. Building and signing it needs Xcode on a Mac; on Windows/Linux,
    `tidevice` or `go-ios` can launch an already-installed WebDriverAgent and
    forward port 8100.
    """

    def __init__(self, url: str | None = None):
        try:
            import wda  # type: ignore
        except ImportError as e:
            raise DeviceError("iPhone support needs `pip install facebook-wda`.") from e
        self.url = url or C.WDA_URL
        self.client = wda.Client(self.url)
        try:
            self.client.status()
            self.scale = float(self.client.scale)
        except Exception as e:  # noqa: BLE001 - any connection failure means "not reachable"
            raise DeviceError(f"WebDriverAgent is not reachable at {self.url}: {e}") from e

    def screenshot(self) -> np.ndarray:
        img = self.client.screenshot(format="pillow")
        arr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        rotations = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
        if C.IOS_SCREENSHOT_ROTATION in rotations:
            arr = cv2.rotate(arr, rotations[C.IOS_SCREENSHOT_ROTATION])
        return arr

    def tap(self, x: int, y: int) -> None:
        # Screenshots are in pixels, WebDriverAgent taps in points.
        self.client.tap(x / self.scale, y / self.scale)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        s = self.scale
        self.client.swipe(x1 / s, y1 / s, x2 / s, y2 / s, duration_ms / 1000)

    def foreground_app(self) -> str | None:
        try:
            return self.client.app_current().get("bundleId")
        except Exception:  # noqa: BLE001
            return None

    def describe(self) -> str:
        return f"iPhone via WebDriverAgent at {self.url}"


class ImageDevice(Device):
    """Serves a saved screenshot instead of a live screen (calibration and tests).
    Taps and swipes are recorded, never sent anywhere."""

    def __init__(self, image: np.ndarray | str | Path, foreground: str | None = None):
        if isinstance(image, (str, Path)):
            loaded = cv2.imread(str(image), cv2.IMREAD_COLOR)
            if loaded is None:
                raise DeviceError(f"Cannot read image {image}")
            image = loaded
        self.image = image
        self.foreground = foreground
        self.taps: list[tuple[int, int]] = []
        self.swipes: list[tuple[int, int, int, int]] = []

    def screenshot(self) -> np.ndarray:
        return self.image.copy()

    def tap(self, x: int, y: int) -> None:
        self.taps.append((int(x), int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.swipes.append((int(x1), int(y1), int(x2), int(y2)))

    def foreground_app(self) -> str | None:
        return self.foreground

    def describe(self) -> str:
        return "saved screenshot"


def open_device() -> Device:
    """Open the device described in config.py, or find one: a plugged-in phone,
    an emulator adb already sees, or an emulator at one of the usual addresses."""
    if C.DEVICE == "ios":
        return WdaDevice(C.WDA_URL)
    if C.DEVICE != "android":
        raise DeviceError(f"Unknown DEVICE {C.DEVICE!r} in config.py (use 'android' or 'ios').")
    serial = C.ADB_SERIAL
    if serial is None and C.EMULATOR:
        try:
            serial = C.EMULATOR_ADB_ADDRESSES[C.EMULATOR]
        except KeyError as e:
            raise DeviceError(f"Unknown EMULATOR {C.EMULATOR!r}; use one of {list(C.EMULATOR_ADB_ADDRESSES)}.") from e
    adb = find_adb()
    if serial is None and not any(st == "device" for st in list_adb_devices(adb).values()):
        serial = autoconnect_emulator(adb)
    return AdbDevice(serial, adb)
