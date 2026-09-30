# TLDR 
**What it is**: in poe2, it screenshots your options for the stones in expedition and tells you what they're worth. you can always pick the highest value option instead of something random

**how does it work**: you run `update_prices.py` once. it uses some api's to build a list of like 400 items current values 1 time. Then, whenever you take a screenshot it sends it to a cheap ai to figure out what it actually says, then it checks the prices in from the list you made. 

**how to use it**
1) Required: only works in windowed, or windowed fullscreen. does not work in fullscreen & you need an ai api key to use
2) Run `python install_shortcut.py` once. After that, open **PoE2 expedition Price Checker** from the Start Menu like any other app (right-click it → Pin to taskbar if you want)
3) Optionally, you can hit f7 to show the screenshot area, you can adjust the size in the code
4) Hit f8 to do it

**the app window**: update prices, change league, change the minimum price, turn screenshot saving on/off, see which ai model is used, and quit. It also shows a log of what each scan read.

**configs.py settings** (everything, including what the app window doesn't have)
1) you can change the screenshot area in the code
2) you can change the minimum price. for example, if everything is under 50 exalt, it'll say nothing is good. you can change this value from 50 to anything
3) you can change the league you're in
4) use whatever ai model you want
5) choose to save or not to save screenshots

Settings changed in the app window are saved to `settings.json` and override `config.py`. Delete `settings.json` to go back to the `config.py` values.

============================================================================

# PoE2 Expedition Price Checker

Press F8 on the Expedition reward screen. The script screenshots the reward
list, has Claude Haiku read the item names, looks them up in poe.ninja prices,
and shows a small always-on-top popup: valuable rewards in gold, items with no
known price in grey. The popup never takes focus from the game, lets clicks pass
through, and hides itself after a few seconds.

## Setup

```
pip install -r requirements.txt
python install_shortcut.py     # adds "PoE2 Price Checker" to the Start Menu
```

Then start it from the Start Menu (or `python main.py`). It opens a small
settings window; closing it or pressing Quit stops the hotkeys. Starting it
again while it's running just brings the window back.

- Run the game in **Windowed Fullscreen** (exclusive fullscreen blocks overlays).
- The Claude API key is read from `..\secrets\claude_api_key.txt`.
- Prices are downloaded once from poe.ninja on first run into `data/prices.json`.
  Refresh with the **Update prices** button (or `python update_prices.py`).
- If the game runs as administrator, this app must too, or the hotkey won't fire.
- `python install_shortcut.py --desktop` also adds a desktop shortcut;
  `--remove` deletes them. Re-run it if you move this folder or reinstall Python.

## Hotkeys

| Key | Action |
|-----|--------|
| F8  | Scan the reward list |
| F7  | Flash a red outline around the scan area |

Quit with the window's Quit button (or Ctrl+C when started from a console).

## Tuning

All settings are in `config.py`: scan area, monitor, highlight threshold, popup
position/duration, league, and `SAVE_SCREENSHOTS` (saves every scan to
`screenshots/`). League, highlight threshold and screenshot saving changed in
the app window are stored in `settings.json`, which overrides `config.py`.

To check a scan area against a saved full-monitor screenshot without the game:

```
python main.py --image shot.png --dry-run   # just saves the crop
python main.py --image shot.png             # crop + AI + prices, printed
```

## Manual prices

poe.ninja doesn't price everything (e.g. individual skill gems, rarely traded
runes). Add your own in `manual_prices.txt`, one per line: `Skyfall = 5 ex`.
Manual entries override downloaded prices.
