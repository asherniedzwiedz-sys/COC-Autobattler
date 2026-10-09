"""The main loop: read storages, upgrade with excess loot, donate, then attack.

Attacking is Phase 2 and is only built after you approve the army proposal;
until then the loop stops right before the attack step.
"""
from __future__ import annotations

import logging

from . import config as C
from .bot import Bot
from .donate import Donator
from .errors import (DeviceError, DryRunStop, FlowError, ForbiddenAction, GemSpendBlocked, NotAffordable,
                     NotInGame, StopBot)
from .ocr import OcrUnavailable
from .state import HomeState, farming_stop_reason, read_home_state
from .templates_spec import missing
from .upgrades import Upgrader

log = logging.getLogger("cocbot")


class Farmer:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.upgrader = Upgrader(bot)
        self.donator = Donator(bot)
        self.cycles = 0

    def run(self) -> str:
        """Loop until a stop condition; returns the (logged) stop reason."""
        try:
            while True:
                self.cycle()
        except StopBot as e:
            reason = str(e)
        except NotInGame as e:
            reason = f"Clash of Clans is not the app in front ({e}); stopped without tapping."
        except DeviceError as e:
            reason = f"Device error: {e}"
        except OcrUnavailable as e:
            reason = str(e)
        except KeyboardInterrupt:
            reason = "Stopped by user (Ctrl+C)."
        try:
            screen = self.bot.screen()
        except Exception:  # noqa: BLE001 - the device may be what failed
            screen = None
        self.bot.events.stop(reason, screen)
        return reason

    def cycle(self) -> None:
        self.cycles += 1
        log.info("--- cycle %d ---", self.cycles)
        state = self.read_state()
        if state is not None:
            self.attempt("upgrades", self.upgrader.run, state)
            state = self.read_state()
            reason = farming_stop_reason(state)
            if reason:
                raise StopBot(reason)
        if self.bot.auto_donate:
            self.attempt("donations", self.donator.run)
        self.attack()

    def read_state(self) -> HomeState | None:
        miss = missing(self.bot.vision, "storage")
        if miss:
            log.warning("Storage templates missing (%s): can't read storages, so no upgrades or "
                        "full-storage stop this cycle.", ", ".join(miss))
            return None
        state = read_home_state(self.bot.screen(), self.bot.vision)
        log.info("Home: %s", state.summary())
        self.bot.events.record("home_state", **state.as_dict())
        return state

    def attempt(self, name: str, fn, *args) -> None:
        """Run one flow; a failure or block in it never takes down the loop (except stop conditions)."""
        try:
            fn(*args)
        except DryRunStop as e:
            log.info("[DRY RUN] %s stops here, since the next step depends on that tap: %s", name, e)
        except GemSpendBlocked as e:
            self.bot.on_gem_block(f"{name}: {e}")
        except (FlowError, NotAffordable, ForbiddenAction) as e:
            log.warning("%s skipped: %s", name, e)
            try:
                self.bot.close_popups()
            except DryRunStop:
                pass

    def attack(self) -> None:
        if C.APPROVED_ARMY is None:
            raise StopBot("No approved army yet. Attacking is built in Phase 2, after you approve "
                          "the army proposal; stopping before searching for a base.")
        raise StopBot("Attack phase is not implemented yet.")
