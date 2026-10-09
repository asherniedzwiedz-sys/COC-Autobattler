"""Finding adb and the emulator without editing config.py."""
from types import SimpleNamespace

import pytest

from cocbot import cli, config, device
from cocbot.errors import DeviceError


def test_find_adb_falls_back_to_known_locations(tmp_path, monkeypatch):
    bundled = tmp_path / "HD-Adb.exe"
    bundled.write_text("")
    monkeypatch.setattr(config, "ADB_PATH", None)
    monkeypatch.setattr(device.shutil, "which", lambda name: None)
    monkeypatch.setattr(device, "adb_candidates", lambda: [str(tmp_path / "missing.exe"), str(bundled)])
    assert device.find_adb() == str(bundled)


def test_find_adb_reports_how_to_fix(monkeypatch):
    monkeypatch.setattr(config, "ADB_PATH", None)
    monkeypatch.setattr(device.shutil, "which", lambda name: None)
    monkeypatch.setattr(device, "adb_candidates", lambda: [])
    with pytest.raises(DeviceError, match="BlueStacks"):
        device.find_adb()


def test_autoconnect_uses_the_first_emulator_that_answers(monkeypatch):
    monkeypatch.setattr(config, "EMULATOR_AUTO_ADDRESSES", ("127.0.0.1:5555", "127.0.0.1:5565"))
    tried = []

    def fake_run(cmd, **kwargs):
        tried.append(cmd[-1])
        ok = cmd[-1] == "127.0.0.1:5565"
        return SimpleNamespace(stdout=f"connected to {cmd[-1]}" if ok else "cannot connect", returncode=0)

    monkeypatch.setattr(device.subprocess, "run", fake_run)
    monkeypatch.setattr(device, "list_adb_devices", lambda adb: {"127.0.0.1:5565": "device"})
    assert device.autoconnect_emulator("adb") == "127.0.0.1:5565"
    assert tried == ["127.0.0.1:5555", "127.0.0.1:5565"]


def test_open_device_autoconnects_when_nothing_is_attached(monkeypatch):
    monkeypatch.setattr(config, "DEVICE", "android")
    monkeypatch.setattr(config, "ADB_SERIAL", None)
    monkeypatch.setattr(config, "EMULATOR", None)
    monkeypatch.setattr(device, "find_adb", lambda: "adb")
    monkeypatch.setattr(device, "list_adb_devices", lambda adb: {})
    monkeypatch.setattr(device, "autoconnect_emulator", lambda adb: "127.0.0.1:5555")
    opened = {}
    monkeypatch.setattr(device, "AdbDevice", lambda serial, adb: opened.setdefault("args", (serial, adb)))
    device.open_device()
    assert opened["args"] == ("127.0.0.1:5555", "adb")


def test_device_option_overrides_config(monkeypatch):
    monkeypatch.setattr(config, "ADB_SERIAL", None)
    seen = {}
    monkeypatch.setattr(cli, "cmd_templates", lambda args: seen.setdefault("serial", config.ADB_SERIAL) and 0)
    cli.main(["--device", "127.0.0.1:5585", "templates"])
    assert seen["serial"] == "127.0.0.1:5585"
