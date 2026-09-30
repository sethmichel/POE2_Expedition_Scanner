"""PoE2 Expedition price checker.

Live:     python main.py                  (F8 scans, F7 shows the scan area)
Offline:  python main.py --image shot.png [--dry-run]
          Runs the pipeline on a saved full-monitor screenshot instead of the
          screen. --dry-run only saves the cropped scan area (no AI call).
"""
import argparse
import queue
import signal
import threading
import time
import tkinter as tk

import keyboard
import win32gui
from PIL import Image

import config
from capture import enable_dpi_awareness, game_monitor_rect, grab, to_screen
from popup import Overlay
from prices import PriceBook, evaluate_rewards, fetch_prices, save_prices
from reader import ItemReader


def load_price_book():
    book = None
    if config.PRICES_FILE.is_file():
        book = PriceBook(config.PRICES_FILE, config.MANUAL_PRICES_FILE, config.FUZZY_MATCH_CUTOFF)
        if book.league != config.LEAGUE:
            print(f"Price file is for {book.league}, but config says {config.LEAGUE}.")
            book = None
    if book is None:
        print(f"Downloading {config.LEAGUE} prices from poe.ninja...")
        save_prices(fetch_prices(config.LEAGUE), config.PRICES_FILE)
        book = PriceBook(config.PRICES_FILE, config.MANUAL_PRICES_FILE, config.FUZZY_MATCH_CUTOFF)
    print(f"Loaded {len(book)} prices ({book.league}, fetched {book.fetched_at}, "
          f"{book.manual_count} manual). 1 div = {book.ex_per_div:.0f} ex")
    return book


def save_screenshot(image):
    config.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.SCREENSHOT_DIR / f"scan_{time.strftime('%Y%m%d_%H%M%S')}.png"
    image.save(path)
    return path


def print_rewards(rewards, book, threshold_div):
    if not rewards:
        print("  (no reward text found)")
    for reward in rewards:
        if reward.total_div is None:
            price = "no price"
        else:
            price = book.format(reward.total_div)
            if reward.total_div >= threshold_div:
                price += "  <-- valuable"
        note = f"   [fuzzy match for {reward.text!r}]" if reward.fuzzy else ""
        name = reward.matched_name or reward.name
        qty = f"{reward.quantity}x " if reward.quantity > 1 else ""
        print(f"  {qty}{name:<40} {price}{note}")


class App:
    def __init__(self, book, reader):
        self.book = book
        self.reader = reader
        self.threshold_div = book.to_div(config.HIGHLIGHT_THRESHOLD)
        self.monitor = game_monitor_rect(config.MONITOR)
        self.scan_rect = to_screen(self.monitor, config.SCAN_REGION)
        popup_pos = to_screen(self.monitor, (*config.POPUP_POSITION, 0, 0))[:2]

        self.root = tk.Tk()
        self.root.withdraw()
        self.overlay = Overlay(self.root, popup_pos, config.POPUP_SECONDS,
                               config.POPUP_OPACITY, config.POPUP_CLICK_THROUGH)
        self.events = queue.Queue()
        self.busy = False

    def run(self):
        # Hotkey callbacks run on the keyboard hook's thread; hand them to Tk's.
        keyboard.add_hotkey(config.SCAN_HOTKEY, lambda: self.events.put(("scan", None)))
        if config.SHOW_REGION_HOTKEY:
            keyboard.add_hotkey(config.SHOW_REGION_HOTKEY, lambda: self.events.put(("region", None)))
        signal.signal(signal.SIGINT, lambda *_: self.root.quit())

        print(f"Game monitor {self.monitor}, scan area {self.scan_rect}.")
        print(f"Ready. {config.SCAN_HOTKEY.upper()} = scan"
              + (f", {config.SHOW_REGION_HOTKEY.upper()} = show scan area" if config.SHOW_REGION_HOTKEY else "")
              + ". Ctrl+C to quit.")
        self.root.after(50, self._poll)
        self.root.mainloop()
        keyboard.unhook_all()

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "scan":
                    self._start_scan()
                elif kind == "region":
                    self.overlay.flash_region(self.scan_rect)
                elif kind == "result":
                    self._finish_scan(payload)
                elif kind == "error":
                    self.busy = False
                    print(f"Scan failed: {payload}")
                    self.overlay.show_message("Scan failed", payload, color="#ff5a4f")
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _start_scan(self):
        if self.busy:
            return
        self.busy = True
        # Get our own windows out of the way, give the compositor a frame, then grab.
        self.overlay.hide()
        self.overlay.hide_region()
        self.root.after(60, self._capture)

    def _capture(self):
        foreground = win32gui.GetForegroundWindow()
        image = grab(self.scan_rect)
        if config.SAVE_SCREENSHOTS:
            print(f"Saved {save_screenshot(image)}")
        self.overlay.show_message("Scanning rewards...", auto_hide=False)
        self._restore_focus(foreground)
        threading.Thread(target=self._work, args=(image,), daemon=True).start()

    def _work(self, image):
        try:
            lines = self.reader.read(image)
            rewards = evaluate_rewards(lines, self.book, config.STRIP_TEXT_BEFORE_COLON)
            self.events.put(("result", (lines, rewards)))
        except Exception as error:  # shown in the popup; the app keeps running
            self.events.put(("error", f"{type(error).__name__}: {error}"))

    def _finish_scan(self, payload):
        lines, rewards = payload
        self.busy = False
        print(f"Read: {lines}")
        print_rewards(rewards, self.book, self.threshold_div)
        foreground = win32gui.GetForegroundWindow()
        self.overlay.show_results(rewards, self.book, self.threshold_div, config.HIGHLIGHT_THRESHOLD)
        self._restore_focus(foreground)

    @staticmethod
    def _restore_focus(hwnd):
        """Safety net in case showing a popup stole focus from the game."""
        if hwnd and win32gui.GetForegroundWindow() != hwnd:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except win32gui.error:
                pass


def run_offline(image_path, dry_run, book):
    """Run one scan against a saved full-monitor screenshot."""
    image = Image.open(image_path).convert("RGB")
    crop = image.crop(config.SCAN_REGION)
    path = save_screenshot(crop)
    print(f"Cropped scan area saved to {path}")
    if dry_run:
        return
    reader = ItemReader(config.API_KEY_PATH, config.MODEL)
    lines = reader.read(crop)
    print(f"Read: {lines}")
    rewards = evaluate_rewards(lines, book, config.STRIP_TEXT_BEFORE_COLON)
    print_rewards(rewards, book, book.to_div(config.HIGHLIGHT_THRESHOLD))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", help="full-monitor screenshot to scan instead of the live screen")
    parser.add_argument("--dry-run", action="store_true", help="with --image: only save the crop")
    args = parser.parse_args()

    enable_dpi_awareness()
    book = load_price_book()
    if args.image:
        run_offline(args.image, args.dry_run, book)
        return
    App(book, ItemReader(config.API_KEY_PATH, config.MODEL)).run()


if __name__ == "__main__":
    main()
