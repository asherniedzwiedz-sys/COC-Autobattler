"""The template images each feature needs. You crop these from your own device's
screenshots with `python -m cocbot crop` (see templates/README.md)."""
from __future__ import annotations

from . import config as C
from .guard import SPEND_RESOURCES
from .vision import Vision

# name: (feature, where it is, what to crop)
TEMPLATES = {
    "res_gem": ("safety", "any button priced in gems, e.g. 'Finish now' on a building that is upgrading",
                "only the small gem icon on the button"),
    "res_gold": ("safety", "an upgrade button or upgrade window priced in gold", "only the small gold icon on the button"),
    "res_elixir": ("safety", "an upgrade button priced in elixir (e.g. a wall's elixir upgrade)",
                   "only the small elixir icon on the button"),
    "res_dark": ("safety", "a button priced in dark elixir (e.g. a hero upgrade)", "only the small dark elixir icon"),
    "btn_close": ("safety", "any window (upgrade window, donate window, ...)", "the red X close button"),
    "home_gold_icon": ("storage", "home village, top right", "the gold icon at the right end of the gold bar"),
    "home_elixir_icon": ("storage", "home village, top right", "the elixir icon at the right end of the elixir bar"),
    "home_dark_icon": ("storage", "home village, top right", "the dark elixir icon at the end of its bar"),
    "builder_icon": ("upgrades", "home village, top centre", "the builder icon next to the free/total builder count"),
    "btn_upgrade": ("upgrades (optional)", "bar under a selected building",
                    "the Upgrade button's arrow icon, without the price"),
    "chat_open": ("donate", "home village, left edge", "the tab that slides clan chat open"),
    "chat_close": ("donate", "clan chat open", "the tab that slides clan chat closed"),
    "btn_donate": ("donate", "clan chat with a troop request", "the green Donate button on a request"),
}

FEATURE_REQUIREMENTS = {
    "safety": ["res_gem", "btn_close"],
    "storage": ["home_gold_icon", "home_elixir_icon", "home_dark_icon"],
    "upgrades": ["builder_icon"],
    "donate": ["chat_open", "chat_close", "btn_donate"],
}

RECOMMENDED_EXTRAS = {
    "trap_*": "gem offers the bot should close on sight, e.g. trap_not_enough_resources (the "
              "'get missing resources for gems?' popup) and trap_builders_busy",
    "forbid_*": "buttons that must never be pressed, e.g. forbid_shop, forbid_gem_counter, forbid_chat_input",
    "donate_<troop>": "each troop in DONATE_TROOPS, cropped from the donate window",
}


def missing(vision: Vision, feature: str) -> list[str]:
    miss = [n for n in FEATURE_REQUIREMENTS[feature] if not vision.has(n)]
    if feature == "safety" and not any(vision.has(f"res_{r}") for r in SPEND_RESOURCES):
        miss.append("res_gold/res_elixir/res_dark (at least one)")
    return miss


def report(vision: Vision) -> str:
    lines = [f"Templates folder: {vision.dir}"]
    for feature in FEATURE_REQUIREMENTS:
        miss = missing(vision, feature)
        lines.append(f"  {feature:<9} {'ready' if not miss else 'MISSING ' + ', '.join(miss)}")
    donate_have = [t for t in C.DONATE_TROOPS if vision.has(f"donate_{t}")]
    lines.append(f"  donate troops with templates: {', '.join(donate_have) or 'none'}")
    lines.append(f"  gem offers (trap_*): {', '.join(vision.names_with_prefix('trap_')) or 'none'}")
    lines.append(f"  never-press (forbid_*): {', '.join(vision.names_with_prefix('forbid_')) or 'none'}")
    return "\n".join(lines)
