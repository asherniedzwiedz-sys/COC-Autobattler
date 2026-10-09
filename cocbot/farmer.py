"""The main loop: read storages, upgrade with excess loot, donate, then attack."""
from __future__ import annotations

import logging

from . import config as C
from .army import Army
from .attack import Attacker
from .bot import Bot
from .donate import Donator
from .errors import (DeviceError, DryRunStop, FlowError, ForbiddenAction, GemSpendBlocked, NotAffordable,
                     NotInGame, StopBot)
from .ocr import OcrUnavailable
from .search import Searcher
from .state import RESOURCES, HomeState, farming_stop_reason, read_home_state
from .templates_spec import missing
from .upgrades import Upgrader

log = logging.getLogger("cocbot")


class Farmer:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.upgrader = Upgrader(bot)
        self.donator = Donator(bot)
        self.army = Army(bot)
        self.searcher = Searcher(bot)
        self.attacker = Attacker(bot)
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
            raise StopBot("No approved army in config.py; stopping before searching for a base.")
        miss = [n for feature in ("attack", "army", "targeting") for n in missing(self.bot.vision, feature)]
        if miss:
            raise StopBot(f"Attacking needs these templates first: {', '.join(miss)} (see templates/README.md).")
        before = self.read_state()
        try:
            self.army.ensure_ready()
            base = self.searcher.find_base()
            if base is None:
                raise StopBot(f"No base qualified in {C.MAX_NEXTS} Nexts; ending the session.")
            result = self.attacker.attack(base)
        except DryRunStop as e:
            raise StopBot(f"Dry run finished; the next step would have been: {e}.") from None
        except GemSpendBlocked as e:
            self.bot.on_gem_block(f"attack: {e}")
            raise StopBot(f"Gem guard blocked a step of the attack ({e}); stopping to be safe.") from None
        except FlowError as e:
            self.leave_search()
            raise StopBot(f"Attack stopped: {e}") from None
        after = self.read_state()
        self.bot.events.attack(
            target_th=base.th_level, loot_gained=loot_gained(before, after), trophies_change=result["trophies"],
            base_loot={"gold": base.gold, "elixir": base.elixir, "dark": base.dark}, nexts=base.nexts,
            side=result["side"], air_defenses_zapped=result["air_defenses_zapped"])

    def leave_search(self) -> None:
        """Best effort: if stuck on a search screen, end it (nothing deployed, no trophies lost)."""
        try:
            if self.bot.find("btn_end_battle") is not None:
                self.searcher.end_search()
        except Exception as e:  # noqa: BLE001 - already stopping; just record it
            log.warning("Couldn't leave the search screen: %s", e)


def loot_gained(before: HomeState | None, after: HomeState | None) -> dict[str, int | None]:
    """Change in each storage across the attack (net of the gold spent on searching)."""
    gained = {}
    for r in RESOURCES:
        a = before.storage(r).current if before else None
        b = after.storage(r).current if after else None
        gained[r] = b - a if a is not None and b is not None else None
    return gained
