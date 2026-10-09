# COC-Autobattler

A Clash of Clans farming bot in Python. It drives the game over ADB on an
Android phone or emulator (iPhone support is experimental). It reads the
screen with OpenCV template matching and Tesseract OCR.

> **Warning:** Supercell's Terms of Service forbid bots and automation tools.
> Running this risks a ban on the account. Use it at your own risk.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Device control, gem guard, number reading, storages, wall/suggested upgrades, donations, dry run, logging, account scan | done |
| 1 | Army and strategy | approved (see below) |
| 2 | Army check, base search and targeting, the attack, returning home, attack logging | built; needs templates cut on your emulator, then dry runs |

## The approved attack

- **Army:** 17 Dragons (level 12), 11 Lightning Spells (level 12), a Battle
  Blimp carrying the Clan Castle troops, and four heroes: Royal Champion,
  Grand Warden, Minion Prince and Dragon Duke. You set this up once in the
  game; the bot only checks that it's full.
- **Plan:**
  1. Attack from the edge nearest the enemy Town Hall.
  2. Drop 4 Lightning Spells on each of the Air Defenses nearest that edge
     (2 with 11 spells).
  3. Deploy the dragons in a line along that edge.
  4. After a short delay, send the Blimp and heroes in behind the dragons.
  5. Fire hero abilities on a timer, then wait for the battle to end.
- **Targets:** a base qualifies only if every rule holds:
  - gold + elixir is at least 1.7M, read the same twice in a row. There's no
    upper limit unless you set `LOOT_MAX`;
  - at least 3 full collectors are visible (a dead base);
  - its Town Hall sits in the open, or it is at most TH17 with at most 4 Air
    Defenses.

  Anything the bot can't read counts against the base. After 40 Nexts it
  ends the session.

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

## Quick start on Windows with BlueStacks

1. **BlueStacks 5:** install it and Clash of Clans inside it, and log in with
   your Supercell ID. In BlueStacks, go to Settings → Advanced and turn on
   **Android Debug Bridge (ADB)**. BlueStacks includes its own adb, and the
   bot finds it, so there's nothing else to install for ADB.
2. **Python:** install it from python.org. On the first installer screen, tick
   **"Add python.exe to PATH"**.
3. **Tesseract:** install the UB Mannheim build and keep the default folder.
   The bot finds it there.
4. **This code:** on GitHub, open the repo, switch to the
   `claude/clash-of-clans-bot-ymaa7u` branch, then Code → Download ZIP. Unzip
   it, for example to your Desktop.
5. **A terminal in that folder:** open the unzipped folder (the one with
   `README.md` in it), click the address bar, type `cmd` and press Enter.
6. **Install the bot's libraries** (once):
   ```
   py -m pip install -r requirements.txt
   ```
7. **Check the connection.** With BlueStacks open, run the following. It
   should say "Connected", and the bot finds BlueStacks by itself:
   ```
   py -m cocbot devices
   ```
   If it doesn't, look in BlueStacks under Settings → Advanced for "Connect to
   Android at 127.0.0.1:XXXX", then add that address to every command:
   `py -m cocbot --device 127.0.0.1:XXXX devices`.
8. **Use it.** Run `py -m cocbot screenshot` to save the current screen to the
   `screenshots` folder. `py -m cocbot run --step` is a dry run, and
   `py -m cocbot run --live` taps for real. The bot asks about donations
   first.

On Windows, type `py` where the rest of this README says `python`.

## Setup

Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

**ADB (Android platform-tools)**
- Windows: BlueStacks, LDPlayer, MEmu and Nox ship their own adb, and the bot
  finds it. Otherwise, download platform-tools from developer.android.com
  and unzip it to `C:\platform-tools`.
- macOS: `brew install android-platform-tools`
- Linux: `sudo apt install adb` (or your distro's equivalent)

**Tesseract OCR**
- Windows: install the UB Mannheim build into its default folder, where the
  bot finds it. If you installed it elsewhere, set `TESSERACT_CMD`.
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

**Google Play Games for PC won't work.** It's an official way to play on
PC, but it doesn't let other programs control the game over ADB. Use an
Android emulator instead. You can still install Clash of Clans inside it from
the Play Store.

**Emulator:** turn on ADB in the emulator's settings. With nothing plugged
in, the bot tries the usual emulator addresses (`EMULATOR_AUTO_ADDRESSES`) and
uses the first that answers. If yours uses another address, pass it with
`--device 127.0.0.1:XXXX`, or set `ADB_SERIAL` in `cocbot/config.py`.

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

The scan is guided and read-only, and it never taps. At each step you open a
screen and press Enter. It saves the screenshots to `scans/<timestamp>/`,
along with what it could read. (For this account, the army was chosen from
screenshots sent directly instead.)

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

Recommended order on a new device:
1. Cut the templates (see [templates/README.md](templates/README.md)), then
   run `python -m cocbot templates` until every feature says "ready".
2. Run `python -m cocbot calibrate` on the home screen and on a search
   screen, and check every box and the cyan battle-map diamond.
3. Run `python -m cocbot run --step` a few times. You make the menu taps
   yourself while the bot reads each base and logs its decision and its whole
   attack plan. It never deploys. Every base it looks at is saved in
   `logs/searches/`, which is handy for cutting more templates.
4. Run `python -m cocbot run --live`.

Each loop:
1. Read gold, elixir and dark elixir storages and the builder count.
2. If gold or elixir is at or above `STORAGE_THRESHOLD` (95%), upgrade walls
   with that resource until it drops below the threshold. If walls are maxed,
   start the game's suggested upgrades until every builder is busy.
3. If every builder is busy and all three storages are full, stop: further
   attacks would waste loot.
4. Donate (only if enabled): elixir and dark elixir troops from `DONATE_TROOPS`.
   A slot showing a gem price is skipped.
5. Attack:
   1. Check the army is full, waiting up to 10 minutes for it to refill.
   2. Search for a qualifying base.
   3. Run the attack.
   4. Return home and log the target TH, loot gained and trophy change.

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
