"""Always-on-top overlay windows that never take focus from the game.

Visibility is controlled with ShowWindow(SW_SHOWNOACTIVATE / SW_HIDE) rather than
tkinter's deiconify/withdraw, because deiconify activates the window and would
pull keyboard focus away from the game. All methods must run on the Tk thread.
"""
import tkinter as tk

import win32con
import win32gui

BG = "#15120e"
BORDER = "#6b5a3a"
TEXT = "#d8d0c0"
DIM = "#8a8378"
GOLD = "#ffcf4d"
RED = "#ff5a4f"
FONT = "Segoe UI"
TRANSPARENT_KEY = "#010203"


def _hwnd(window):
    window.update_idletasks()
    return win32gui.GetParent(window.winfo_id())


def _make_overlay(window, click_through):
    """Give a Toplevel no-activate / tool-window (/ click-through) styles."""
    hwnd = _hwnd(window)
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    style |= win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_TOPMOST
    if click_through:
        style |= win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
    return hwnd


def _show(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
    )


def _hide(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)


class Overlay:
    def __init__(self, root, position, seconds, opacity, click_through):
        self.root = root
        self.position = position
        self.seconds = seconds
        self._hide_job = None
        self._region_job = None

        # Results popup.
        self.popup = tk.Toplevel(root)
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        self.popup.attributes("-alpha", opacity)
        self.popup.configure(bg=BORDER)
        self.body = tk.Frame(self.popup, bg=BG, padx=12, pady=8)
        self.body.pack(padx=2, pady=2)
        self.popup_hwnd = _make_overlay(self.popup, click_through)
        _hide(self.popup_hwnd)

        # Scan-area outline (everything but the red border is see-through).
        self.region = tk.Toplevel(root)
        self.region.overrideredirect(True)
        self.region.attributes("-topmost", True)
        self.region.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.region_canvas = tk.Canvas(self.region, bg=TRANSPARENT_KEY, highlightthickness=0)
        self.region_canvas.pack(fill="both", expand=True)
        self.region_hwnd = _make_overlay(self.region, click_through=True)
        _hide(self.region_hwnd)

    # --- results popup ---

    def hide(self):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        _hide(self.popup_hwnd)

    def _present(self, auto_hide=True):
        self.popup.geometry(f"+{self.position[0]}+{self.position[1]}")
        self.popup.update_idletasks()
        _show(self.popup_hwnd)
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        if auto_hide:
            self._hide_job = self.root.after(int(self.seconds * 1000), self.hide)

    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _label(self, text, color=TEXT, size=11, bold=False, **grid):
        weight = "bold" if bold else "normal"
        label = tk.Label(self.body, text=text, fg=color, bg=BG, font=(FONT, size, weight),
                         justify="left", anchor="w")
        label.grid(sticky="w", **grid)
        return label

    def show_message(self, title, message="", color=TEXT, auto_hide=True):
        self._clear()
        self._label(title, color=color, size=12, bold=True, row=0, column=0)
        if message:
            label = self._label(message, color=DIM, size=10, row=1, column=0)
            label.configure(wraplength=420)
        self._present(auto_hide)

    def show_results(self, rewards, book, threshold_div, threshold_text):
        self._clear()
        valuable = [r for r in rewards if r.total_div is not None and r.total_div >= threshold_div]
        unknown = [r for r in rewards if r.total_div is None]

        if not rewards:
            headline, color = "No reward text found", RED
        elif valuable:
            best = valuable[0]
            headline = f"★ {best.matched_name}  —  {book.format(best.total_div)}"
            color = GOLD
        else:
            headline, color = f"Nothing over {threshold_text}", TEXT
        self._label(headline, color=color, size=13, bold=True, row=0, column=0, columnspan=2, pady=(0, 6))

        row = 1
        for reward in rewards:
            if reward.total_div is None:
                name, price, name_color, price_color = reward.name, "no price", DIM, DIM
            else:
                name = reward.matched_name
                price = book.format(reward.total_div)
                is_valuable = reward.total_div >= threshold_div
                name_color = price_color = GOLD if is_valuable else TEXT
            if reward.quantity > 1:
                name = f"{reward.quantity}x {name}"
                if reward.unit_div is not None:
                    price += f"  ({book.format(reward.unit_div)} ea)"
            self._label(name, color=name_color, row=row, column=0, padx=(0, 18))
            self._label(price, color=price_color, row=row, column=1)
            row += 1
            if reward.fuzzy:
                self._label(f"   read as: {reward.text}", color=DIM, size=8, row=row, column=0, columnspan=2)
                row += 1

        if unknown:
            self._label(f"{len(unknown)} unknown — add to manual_prices.txt", color=DIM, size=9,
                        row=row, column=0, columnspan=2, pady=(6, 0))
        self._present()

    # --- scan-area outline ---

    def flash_region(self, rect, seconds=2.0):
        left, top, right, bottom = rect
        pad = 3  # draw just outside the scanned pixels
        width, height = right - left + 2 * pad, bottom - top + 2 * pad
        self.region.geometry(f"{width}x{height}+{left - pad}+{top - pad}")
        self.region_canvas.delete("all")
        self.region_canvas.create_rectangle(1, 1, width - 2, height - 2, outline=RED, width=3)
        self.region.update_idletasks()
        _show(self.region_hwnd)
        if self._region_job:
            self.root.after_cancel(self._region_job)
        self._region_job = self.root.after(int(seconds * 1000), lambda: _hide(self.region_hwnd))

    def hide_region(self):
        _hide(self.region_hwnd)
