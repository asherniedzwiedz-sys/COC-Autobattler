"""Exceptions shared across the bot."""


class DeviceError(RuntimeError):
    """The phone/emulator could not be reached or returned bad data."""


class StopBot(Exception):
    """End the session cleanly. The message is the logged stop reason."""


class GuardError(Exception):
    """Base class for actions refused by a safety guard."""


class GemSpendBlocked(GuardError):
    """An action would (or might) spend gems, so it was aborted."""


class ForbiddenAction(GuardError):
    """The action is not on the bot's allow-list for this session."""


class NotInGame(GuardError):
    """Clash of Clans is not the focused app, so no tap is safe."""


class NotAffordable(Exception):
    """The price on a button is shown in red: not enough resources."""


class FlowError(Exception):
    """An expected screen, button or reading was not found; the flow is skipped."""


class DryRunStop(Exception):
    """Dry run reached a tap whose result the rest of the flow depends on."""
