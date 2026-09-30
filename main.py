"""PoE2 Expedition price checker.

Live:     python main.py  (or pythonw / the Start Menu shortcut: no console)
          Opens the settings window; F8 scans, F7 shows the scan area.
Offline:  python main.py --image shot.png [--dry-run]
          Runs the pipeline on a saved full-monitor screenshot instead of the
          screen. --dry-run only saves the cropped scan area (no AI call).
"""
import argparse
import ctypes
import queue
import signal
import sys
import threading
import time
import tkinter as tk

import keyboard
import win32api
import win32con
import win32event
import win32gui
import winerror
from PIL import Image

import config
from capture import enable_dpi_awareness, game_monitor_rect, grab, to_screen
from popup import Overlay
from prices import PriceBook, evaluate_rewards, fetch_leagues, fetch_prices, parse_amount, save_prices
from reader import ItemReader
from window import APP_ID, APP_NAME, ControlPanel, LogWriter


def load_price_book(league, download=False):
    book = None
    if config.PRICES_FILE.is_file() and not download:
        book = PriceBook(config.PRICES_FILE, config.MANUAL_PRICES_FILE, config.FUZZY_MATCH_CUTOFF)
        if book.league != league:
            print(f"Price file is for {book.league}, but the league is set to {league}.")
            book = None
    if book is None:
        print(f"Downloading {league} prices from poe.ninja...")
        save_prices(fetch_prices(league), config.PRICES_FILE)
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
    def __init__(self):
        self.book = None
        self.reader = None
        self.reader_error = None
        self.threshold_div = None
        self.monitor = game_monitor_rect(config.MONITOR)
        self.scan_rect = to_screen(self.monitor, config.SCAN_REGION)
        popup_pos = to_screen(self.monitor, (*config.POPUP_POSITION, 0, 0))[:2]

        self.events = queue.Queue()
        sys.stdout = LogWriter(self.events, sys.__stdout__)
        sys.stderr = LogWriter(self.events, sys.__stderr__)

        self.root = tk.Tk()
        self.panel = ControlPanel(self.root, self.change_league, self.update_prices,
                                  self.set_threshold, self.set_save_screenshots, self.root.quit)
        self.overlay = Overlay(self.root, popup_pos, config.POPUP_SECONDS,
                               config.POPUP_OPACITY, config.POPUP_CLICK_THROUGH)
        self.busy = False
        self.downloading = False

    def run(self):
        # Hotkey callbacks run on the keyboard hook's thread; hand them to Tk's.
        keyboard.add_hotkey(config.SCAN_HOTKEY, lambda: self.events.put(("scan", None)))
        if config.SHOW_REGION_HOTKEY:
            keyboard.add_hotkey(config.SHOW_REGION_HOTKEY, lambda: self.events.put(("region", None)))
        signal.signal(signal.SIGINT, lambda *_: self.root.quit())

        print(f"Game monitor {self.monitor}, scan area {self.scan_rect}.")
        try:
            self.reader = ItemReader(config.API_KEY_PATH, config.MODEL)
        except (OSError, ValueError) as error:
            self.reader_error = str(error)
            print(self.reader_error)
        self._load_prices(config.LEAGUE, download=False)
        threading.Thread(target=self._fetch_leagues, daemon=True).start()

        self.root.after(50, self._poll)
        self.root.mainloop()
        keyboard.unhook_all()

    # --- settings window actions ---

    def change_league(self, league):
        if league and league != (self.book and self.book.league):
            self._load_prices(league, download=True)

    def update_prices(self):
        self._load_prices(config.LEAGUE, download=True)

    def set_threshold(self, text):
        text = text.strip()
        try:
            parse_amount(text)
        except ValueError as error:
            self.panel.set_status(f"Minimum price: {error}", "error")
            return
        config.save(HIGHLIGHT_THRESHOLD=text)
        if self.book:
            self.threshold_div = self.book.to_div(text)
        print(f"Minimum price set to {text}.")
        self._show_ready()

    def set_save_screenshots(self, enabled):
        config.save(SAVE_SCREENSHOTS=enabled)
        print(f"Screenshots will {'' if enabled else 'not '}be saved.")

    # --- background work ---

    def _load_prices(self, league, download):
        if self.downloading:
            return
        self.downloading = True
        self.panel.set_downloading(True)
        self.panel.set_status(f"Loading {league} prices...", "busy")
        threading.Thread(target=self._price_worker, args=(league, download), daemon=True).start()

    def _price_worker(self, league, download):
        try:
            self.events.put(("book", load_price_book(league, download)))
        except Exception as error:  # shown in the window; the old prices stay in use
            self.events.put(("book_error", f"{type(error).__name__}: {error}"))

    def _fetch_leagues(self):
        try:
            self.events.put(("leagues", fetch_leagues()))
        except Exception as error:  # the league box stays free-text
            print(f"Couldn't fetch the league list: {error}")

    def _set_book(self, book):
        self.downloading = False
        self.panel.set_downloading(False)
        self.book = book
        self.panel.set_book(book)
        if book.league != config.LEAGUE:
            config.save(LEAGUE=book.league)
        try:
            self.threshold_div = book.to_div(config.HIGHLIGHT_THRESHOLD)
        except ValueError as error:
            self.panel.set_status(f"Minimum price: {error}", "error")
            return
        self._show_ready()

    def _price_error(self, message):
        self.downloading = False
        self.panel.set_downloading(False)
        print(f"Price download failed: {message}")
        if self.book:
            self.panel.set_book(self.book)  # put the league box back
        self.panel.set_status("Price download failed (see log)", "error")

    def _show_ready(self):
        if self.reader_error:
            self.panel.set_status("No Claude API key (see log)", "error")
        elif self.book and self.threshold_div is not None:
            self.panel.set_status(f"Ready — press {config.SCAN_HOTKEY.upper()} on the reward screen")

    # --- event loop / scanning ---

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
                elif kind == "log":
                    self.panel.append_log(payload)
                elif kind == "book":
                    self._set_book(payload)
                elif kind == "book_error":
                    self._price_error(payload)
                elif kind == "leagues":
                    self.panel.set_leagues(payload)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _start_scan(self):
        if self.busy:
            return
        if self.reader is None or self.book is None or self.threshold_div is None:
            reason = self.reader_error or "Prices are still loading, or the minimum price is invalid."
            self.overlay.show_message("Not ready", reason, color="#ff5a4f")
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


def claim_single_instance():
    """Return a mutex handle to hold for the app's lifetime, or None if the app
    is already running (in which case its window is brought to the front)."""
    mutex = win32event.CreateMutex(None, False, APP_ID)
    if win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS:
        return mutex
    hwnd = win32gui.FindWindow(None, APP_NAME)
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except win32gui.error:
            pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", help="full-monitor screenshot to scan instead of the live screen")
    parser.add_argument("--dry-run", action="store_true", help="with --image: only save the crop")
    args = parser.parse_args()

    enable_dpi_awareness()
    if args.image:
        run_offline(args.image, args.dry_run, load_price_book(config.LEAGUE))
        return

    mutex = claim_single_instance()
    if mutex is None:
        return
    # Own taskbar button and icon instead of being grouped under Python's.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    App().run()


if __name__ == "__main__":
    main()
