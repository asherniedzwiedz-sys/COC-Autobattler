"""Making sure the approved army is full before searching.

The bot doesn't change the army composition: you set it once in the game
(17 Dragons, 11 Lightning, Battle Blimp, your four heroes). Before each search
it opens the Army window, checks that troops and spells are at capacity, and
waits for them to refill if they aren't.
"""
from __future__ import annotations

import logging
import time

from . import config as C
from . import ocr
from .bot import Bot
from .errors import FlowError, StopBot
from .guard import Action
from .vision import crop

log = logging.getLogger("cocbot")


def is_full(pair: tuple[int, int] | None) -> bool:
    return pair is not None and pair[1] > 0 and pair[0] >= pair[1]


class Army:
    def __init__(self, bot: Bot):
        self.bot = bot

    def read_capacity(self) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        screen = self.bot.screen()
        button = self.bot.find("btn_army", screen)
        if button is None:
            raise FlowError("Army button not visible (templates/btn_army.png)")
        self.bot.tap_button(button, Action.TRAIN, "open the Army window to check it's full", screen=screen)
        icon, screen = self.bot.wait_for("army_troops_icon")
        if icon is None:
            raise FlowError("Army window didn't open (templates/army_troops_icon.png)")
        counts = []
        for key in ("army_troops_count", "army_spells_count"):
            box = self.bot.region(key, screen)
            text = ocr.read_chars(crop(screen, box), self.bot.vision.digits, "0123456789/") if box else ""
            counts.append(ocr.parse_fraction(text))
        self.bot.close_popups()
        return counts[0], counts[1]

    def ensure_ready(self) -> None:
        deadline = time.monotonic() + C.ARMY_READY_TIMEOUT
        while True:
            troops, spells = self.read_capacity()
            if troops is None or spells is None:
                raise FlowError(f"couldn't read the army counts (troops {troops}, spells {spells})")
            if is_full(troops) and is_full(spells):
                log.info("Army ready: troops %d/%d, spells %d/%d.", *troops, *spells)
                return
            if time.monotonic() >= deadline:
                raise StopBot(f"Army still not full after {C.ARMY_READY_TIMEOUT // 60} min "
                              f"(troops {troops[0]}/{troops[1]}, spells {spells[0]}/{spells[1]}).")
            log.info("Army not full yet (troops %d/%d, spells %d/%d); checking again in %ds.",
                     *troops, *spells, C.ARMY_CHECK_INTERVAL)
            time.sleep(C.ARMY_CHECK_INTERVAL)
