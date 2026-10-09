# Templates

Crop these from screenshots of **your own** device. Take a screenshot with
`python -m cocbot screenshot`, then cut a template with
`python -m cocbot crop <screenshot> <name>`.

Starter templates are already included, cut from a TH18 home screen at
2622×1206: the storage icons, the builder icon and the digit glyphs. They
rescale automatically to your screen, because `heights.json` records the
screen height each template was cut at. If one doesn't match on your device,
re-cut it there.

Tips:
- Crop **inside** the icon: a tight box within the coin or drop, with no
  background corners, since the village behind them changes. Leave out
  numbers, prices and counts, because they change too.
- Running `crop` again with the same name adds a variant (`name__2.png`, ...).
  Any variant counts as a match, which helps when the same icon appears at
  different sizes on different screens.
- Run `python -m cocbot templates` to see what's still missing, and
  `python -m cocbot calibrate` to see what's found on the current screen.

## Safety (needed before the bot spends anything or donates)

| Name | Where to find it | What to crop |
|---|---|---|
| `res_gem` | Any button priced in gems, e.g. "Finish now" on a building that's upgrading | Only the small gem icon on the button. Add variants for every size you see. |
| `res_gold` | An upgrade button or window priced in gold | Only the small gold icon on the button |
| `res_elixir` | A wall's elixir upgrade button | Only the small elixir icon on the button |
| `res_dark` | A dark elixir price, e.g. a hero upgrade | Only the small dark elixir icon |
| `btn_close` | Any window (upgrade window, donate window) | The red X close button |

Recommended:
- `trap_*`: gem offers to close on sight. For example, tap an upgrade you
  can't afford, crop the "get missing resources?" popup's title area as
  `trap_not_enough_resources`, then close the popup **without** pressing its
  gem button. Do the same for the "all builders busy" offer as `trap_builders_busy`.
- `forbid_*`: buttons that must never be pressed, e.g. `forbid_shop` (shop
  button), `forbid_gem_counter` (the gem count / "+" at top right) and
  `forbid_chat_input` (the chat text box).

## Storages (home village, top right)

| Name | What to crop |
|---|---|
| `home_gold_icon` | Inside the gold coin at the right end of the gold bar |
| `home_elixir_icon` | Inside the elixir drop at the right end of the elixir bar |
| `home_dark_icon` | Inside the dark elixir drop at the right end of its bar |

The amount is read from a box to the left of each icon (`REGIONS` in
`cocbot/config.py`). The game shows no "Max" text, so fullness is measured
from how far the bar has filled. Bars fill from the right, under the icon.
That measurement is accurate to about 2%. For exact numbers, put your total
capacities in `STORAGE_MAX`.

## Digits (`templates/digits/`)

Tesseract misreads the game's number font: it reads 11 012 576 as 1 112 576,
and Level 18 as Level 13. So numbers are read by matching each character
against glyphs cut from a real screen. A glyph that isn't a confident match
makes the whole number "unknown", never a wrong number. To add glyphs from
your own device:

```bash
python -m cocbot digits screenshots/<file>.png 2190,40,155,55 "11 012 576"
```

Give a box around a number and exactly what it shows (digits and `/` only).

## Upgrades

| Name | What to crop |
|---|---|
| `builder_icon` | The builder icon next to the free/total builder count (top centre) |
| `btn_upgrade` (optional) | The Upgrade button's arrow icon under a selected building, without its price |

## Army check

| Name | Where | What to crop |
|---|---|---|
| `btn_army` | Home, bottom left | The Army button |
| `army_troops_icon` | Army window | The troop-capacity icon left of `340/340` |
| `army_spells_icon` | Army window | The spell-capacity icon left of `11/11` |

## Searching

| Name | Where | What to crop |
|---|---|---|
| `btn_attack` | Home, bottom left | The Attack! button |
| `btn_find_match` | Attack menu | The Find a Match button, without its price |
| `btn_next` | Search screen | The Next button, without its price |
| `btn_end_battle` | Search screen | The End Battle button |
| `loot_gold_icon`, `loot_elixir_icon`, `loot_dark_icon` | Search screen, Available Loot | Each resource icon. Then use `calibrate` to check the amount boxes (`loot_*_amount` in `REGIONS`) |
| `full_collector` | Search screen | A full gold mine, elixir collector or drill. Add variants (`full_collector__2`, ...) for each kind and level you see |
| `air_defense` | Search screen | An Air Defense. Add a variant per level |
| `enemy_th<N>` | Search screen | An enemy Town Hall of level N, e.g. `enemy_th16`, `enemy_th17` |
| `enemy_wall` (optional) | Search screen | A wall piece. Lets the bot spot a Town Hall left in the open |

`run --step` saves every base it looks at to `logs/searches/`. Cut these
templates from those screenshots.

## Attacking

| Name | Where | What to crop |
|---|---|---|
| `slot_dragon`, `slot_lightning` | Troop bar at the bottom of the search/battle screen | Each card's picture, without the count |
| `slot_battle_blimp`, `slot_royal_champion`, `slot_grand_warden`, `slot_minion_prince`, `slot_dragon_duke` | Troop bar | Each card's picture (anything missing isn't deployed) |
| `btn_return_home` | Battle results | The Return Home button |
| `btn_surrender`, `btn_okay` | Battle screen | Used only if a battle runs past `BATTLE_TIMEOUT` |
| `result_trophy_icon` | Battle results | The trophy icon next to the trophy change. Also cut `+` and `-` glyphs with `digits` |
| `forbid_boost` | Army window | Boost Army / Boost Heroes, so they're never pressed |

## Donations (only used if you answer "yes" at startup)

| Name | What to crop |
|---|---|
| `chat_open` | The tab on the left edge that slides clan chat open |
| `chat_close` | The tab that slides clan chat closed |
| `btn_donate` | The green Donate button on a troop request |
| `donate_<troop>` | Each troop from `DONATE_TROOPS` in the donate window, e.g. `donate_dragon`. Crop the **top/middle of the portrait**, not the count or price at the bottom. |

Troop names must match `DONATE_TROOPS` in `cocbot/config.py`. Spells and
siege machines are never donated.
