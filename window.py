"""The app's main window: common settings, status, and a log of recent scans.

All methods must run on the Tk thread.
"""
import os
import tkinter as tk
from tkinter import ttk

import config

APP_NAME = "PoE2 Expedition Price Checker"
# Ties the taskbar button to the Start Menu shortcut (see install_shortcut.py).
APP_ID = "SethMichel.PoE2ExpeditionPriceChecker"
ICON_FILE = config.BASE_DIR / "icon.ico"

STATUS_COLORS = {"ok": "#1e7b34", "busy": "#9a6700", "error": "#c62828"}
LOG_LINES = 500


class LogWriter:
    """Stands in for sys.stdout/stderr so print() output shows in the window.

    Safe to call from any thread: text is handed to the Tk thread through the
    app's event queue. Also echoes to the real console when there is one.
    """

    def __init__(self, events, console):
        self.events = events
        self.console = console

    def write(self, text):
        if self.console:
            self.console.write(text)
        if text:
            self.events.put(("log", text))

    def flush(self):
        if self.console:
            self.console.flush()


class ControlPanel:
    def __init__(self, root, on_change_league, on_update_prices, on_threshold, on_screenshots, on_quit):
        self.root = root
        root.title(APP_NAME)
        if ICON_FILE.is_file():
            root.iconbitmap(default=str(ICON_FILE))
        root.protocol("WM_DELETE_WINDOW", on_quit)
        root.minsize(460, 0)

        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(8, weight=1)

        self.status = tk.Label(frame, font=("Segoe UI", 11, "bold"), anchor="w")
        self.status.grid(row=0, column=0, columnspan=3, sticky="we")
        hotkeys = f"{config.SCAN_HOTKEY.upper()} scans the reward list"
        if config.SHOW_REGION_HOTKEY:
            hotkeys += f"  ·  {config.SHOW_REGION_HOTKEY.upper()} shows the scan area"
        ttk.Label(frame, text=hotkeys, foreground="#555").grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Separator(frame).grid(row=2, column=0, columnspan=3, sticky="we", pady=10)

        pad = {"pady": 4}
        ttk.Label(frame, text="AI model").grid(row=3, column=0, sticky="w", **pad)
        ttk.Label(frame, text=config.MODEL).grid(row=3, column=1, columnspan=2, sticky="w", padx=8, **pad)

        ttk.Label(frame, text="League").grid(row=4, column=0, sticky="w", **pad)
        self.league = tk.StringVar(value=config.LEAGUE)
        self.league_box = ttk.Combobox(frame, textvariable=self.league)
        self.league_box.grid(row=4, column=1, sticky="we", padx=8, **pad)
        self.league_button = ttk.Button(frame, text="Change league",
                                        command=lambda: on_change_league(self.league.get().strip()))
        self.league_button.grid(row=4, column=2, sticky="we", **pad)

        ttk.Label(frame, text="Prices").grid(row=5, column=0, sticky="w", **pad)
        self.prices = ttk.Label(frame, text="not loaded yet")
        self.prices.grid(row=5, column=1, sticky="w", padx=8, **pad)
        self.update_button = ttk.Button(frame, text="Update prices", command=on_update_prices)
        self.update_button.grid(row=5, column=2, sticky="we", **pad)

        ttk.Label(frame, text="Minimum price").grid(row=6, column=0, sticky="w", **pad)
        threshold_row = ttk.Frame(frame)
        threshold_row.grid(row=6, column=1, sticky="w", padx=8, **pad)
        self.threshold = tk.StringVar(value=config.HIGHLIGHT_THRESHOLD)
        entry = ttk.Entry(threshold_row, textvariable=self.threshold, width=12)
        entry.pack(side="left")
        entry.bind("<Return>", lambda _e: on_threshold(self.threshold.get()))
        ttk.Label(threshold_row, text="e.g. 50 ex or 0.5 div", foreground="#777").pack(side="left", padx=8)
        ttk.Button(frame, text="Save", command=lambda: on_threshold(self.threshold.get())).grid(
            row=6, column=2, sticky="we", **pad)

        ttk.Label(frame, text="Screenshots").grid(row=7, column=0, sticky="w", **pad)
        self.screenshots = tk.BooleanVar(value=config.SAVE_SCREENSHOTS)
        ttk.Checkbutton(frame, text="Save every scan", variable=self.screenshots,
                        command=lambda: on_screenshots(self.screenshots.get())).grid(
            row=7, column=1, sticky="w", padx=8, **pad)
        ttk.Button(frame, text="Open folder", command=self._open_screenshots).grid(
            row=7, column=2, sticky="we", **pad)

        log_frame = ttk.Frame(frame)
        log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        self.log = tk.Text(log_frame, height=10, width=64, font=("Consolas", 9), wrap="word",
                           state="disabled", relief="solid", borderwidth=1)
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Button(frame, text="Quit", command=on_quit).grid(row=9, column=2, sticky="we", pady=(12, 0))

    def set_status(self, text, kind="ok"):
        self.status.configure(text=text, fg=STATUS_COLORS[kind])

    def set_leagues(self, names):
        self.league_box.configure(values=names)

    def set_book(self, book):
        self.league.set(book.league)
        self.prices.configure(text=f"{len(book)} items, updated {book.fetched_at[:16]}  "
                                   f"(1 div = {book.ex_per_div:.0f} ex)")

    def set_downloading(self, downloading):
        state = "disabled" if downloading else "normal"
        self.league_button.configure(state=state)
        self.update_button.configure(state=state)

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        excess = int(self.log.index("end-1c").split(".")[0]) - LOG_LINES
        if excess > 0:
            self.log.delete("1.0", f"{excess + 1}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    @staticmethod
    def _open_screenshots():
        config.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(config.SCREENSHOT_DIR)
