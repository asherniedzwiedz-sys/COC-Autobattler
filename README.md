# COC-Autobattler

A Clash of Clans farming bot in Python. It drives the game over ADB on an
Android phone or emulator (iPhone support is experimental). It reads the
screen with OpenCV template matching and Tesseract OCR.

> **Warning:** Supercell's Terms of Service forbid bots and automation tools.
> Running this risks a ban on the account. Use it at your own risk.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Device control, gem guard, OCR, storage reading, wall/suggested upgrades, donations, dry run, logging, **account scan** | done |
| 1 | Army + strategy proposal | waiting on your scan results |
| 2 | Training the approved army, base search/targeting, attacking, returning home | built after you approve the army |

Until an army is approved (`APPROVED_ARMY` in `cocbot/config.py`), `run`
stops right before it would search for a base.

## Things the bot never does

- **Spend gems.** Every gem path is blocked, including finishing builds early,
  gem upgrades, gem training, shields, gem donations and buying missing
  resources. See [How the gem guard works](#how-the-gem-guard-works).
- Type anything. The device layer has no text-input method at all, so it
  cannot post in clan chat.
- Touch clan chat or donations unless you answer **yes** at the startup prompt.
- Do anything beyond these actions: search, attack, return home, train the
  approved army, donate (if enabled), and upgrade walls (or the suggested
  upgrades once walls are maxed). It never does lab research, moves buildings,
  edits the base, or buys shields/guards.

## Setup

Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

**ADB (Android platform-tools)**
- Windows: download platform-tools from developer.android.com, unzip it, and
  either add it to PATH or set `ADB_PATH` in `cocbot/config.py`.
- macOS: `brew install android-platform-tools`
- Linux: `sudo apt install adb` (or your distro's equivalent)

**Tesseract OCR**
- Windows: install the UB Mannheim build. If it isn't on PATH, set
  `TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`.
- macOS: `brew install tesseract`
- Linux: `sudo apt install tesseract-ocr`

Set the game language to English, since the OCR looks for words like
"Wall". Numbers are read with digit glyphs rather than Tesseract (see
[templates/README.md](templates/README.md#digits-templatesdigits)).

## Connecting the device

All settings are in `cocbot/config.py`.

**Android phone:** turn on Developer options, then USB debugging. Plug the
phone in and accept the "Allow USB debugging" prompt. Leave `ADB_SERIAL = None`
if it's the only device. For Wi-Fi debugging, set `ADB_SERIAL = "<phone-ip>:5555"`.

**Emulator:** turn on ADB in the emulator's settings, then set `EMULATOR` to
`"bluestacks"`, `"ldplayer"`, `"memu"`, `"nox"`, `"mumu"` or `"android_studio"`.
If your instance uses another port, set `ADB_SERIAL` directly.

If your phone is an iPhone, the easiest route is an emulator on your PC
(BlueStacks 5 or LDPlayer 9). Log in there with your Supercell ID.

**iPhone (experimental, untested):** this needs WebDriverAgent running on the
phone, which you build and sign with Xcode on a Mac. On Windows/Linux, `tidevice`
or `go-ios` can launch an already-installed WebDriverAgent. Then run
`pip install facebook-wda` and set `DEVICE = "ios"` and `WDA_URL`. If
screenshots come out sideways, set `IOS_SCREENSHOT_ROTATION`.

Check the connection:

```bash
python -m cocbot devices
```

## Phase 1: scan the account

```bash
python -m cocbot scan
```

The scan is guided and read-only, and it never taps. At each step you open
a screen on the device (home, Town Hall selected, Army tab, Train Troops,
Brew Spells, Siege, Hero Hall) and press Enter. It saves each screenshot to
`scans/<timestamp>/`, reads the Town Hall level (plus storages and builders,
if the storage templates exist), and writes `report.md` and `report.json`.

Send that folder back (commit it to this branch, or attach the screenshots).
I'll read the troop, spell, hero and equipment levels, then propose the army
and strategy for you to approve.

## Templates

The bot finds buttons and icons by matching small images that you crop from
**your own** device. That way they match your resolution and game version.
[templates/README.md](templates/README.md) lists each one.

Starter templates are included, cut from a TH18 screen: the storage icons,
the builder icon and the number digits. They rescale to your screen
automatically. Everything else you cut yourself:

```bash
python -m cocbot screenshot                 # saves screenshots/<time>.png
python -m cocbot crop screenshots/<file>.png res_gem   # drag a box, press Enter
python -m cocbot digits screenshots/<file>.png x,y,w,h "11 012 576"   # more digit glyphs
python -m cocbot templates                  # which features are ready
python -m cocbot calibrate                  # draws matches + text regions -> logs/calibration.png
```

If a feature's templates are missing, that feature turns itself off. For
example, with no `res_gem.png` the bot refuses all spending and all donations.

## Running

```bash
python -m cocbot run            # dry run (default): logs every tap it would make, taps nothing
python -m cocbot run --step     # dry run where you make the navigation taps yourself, step by step
python -m cocbot run --live     # real taps (asks you to type "live" first)
```

On startup the bot asks: `Auto-donate to clan mate requests? (yes/no)`.

Each loop:
1. Read gold, elixir and dark elixir storages and the builder count.
2. If gold or elixir is at or above `STORAGE_THRESHOLD` (95%), upgrade walls
   with that resource until it drops below the threshold. If walls are maxed,
   start the game's suggested upgrades until every builder is busy.
3. If every builder is busy and all three storages are full, stop: further
   attacks would waste loot.
4. Donate (only if enabled): elixir and dark elixir troops from `DONATE_TROOPS`.
   A slot showing a gem price is skipped.
5. Attack (Phase 2).

A plain dry run reads the real screen but stops each flow at its first tap,
because the next step depends on that tap. `--step` lets you make the
navigation taps yourself so a whole flow can be checked. You are never asked
to make a tap that spends, donates or deploys.

## Logs

- `logs/cocbot.log`: everything, human-readable.
- `logs/events.jsonl`: one JSON line per attack (target TH, loot gained,
  trophies), wall upgrade, suggested upgrade, donation, blocked gem path,
  dry-run action and stop reason.
- `logs/stop_*.png`: the screen at the moment the bot stopped.

## How the gem guard works

The gem guard has several layers and fails closed:

1. Every tap carries an action tag. Untagged taps are refused, and donation
   taps are refused unless you enabled donations.
2. Before every tap, the bot checks that Clash of Clans is the app in front.
   This means a Play Store or App Store purchase sheet can never be tapped.
3. Known gem offers (`templates/trap_*.png`) close on sight, and nothing else
   is tapped while one is showing.
4. Taps landing on a never-press button (`templates/forbid_*.png`) are refused.
5. Spending only ever taps the price icon itself, and only after positively
   finding a gold, elixir or dark elixir icon there with no gem icon on the
   same button. If no icon is found, nothing is tapped. A red (unaffordable)
   price is skipped.
6. After paying, if a gem offer or gem price pops up, the bot closes it.
   After `MAX_GEM_BLOCKS` blocks the session ends.

## Tests

```bash
pip install pytest
python -m pytest
```

The tests use synthetic screens, so they need no device. The OCR tests need
Tesseract installed.
