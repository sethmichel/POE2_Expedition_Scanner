"""Monitor lookup and screen capture via the Win32 GDI (no mss).

All coordinates are physical pixels in the virtual-screen space, where the
primary monitor's top-left is (0, 0) and monitors to its left are negative.
"""
import ctypes

import win32api
import win32con
import win32gui
import win32ui
from PIL import Image


def enable_dpi_awareness():
    """Make Windows report real pixels instead of DPI-scaled ones.

    Must run before any window (including tkinter) is created.
    """
    try:
        # Per-monitor aware v2.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def list_monitors():
    """Monitors sorted left to right as dicts with 'rect' and 'primary'."""
    monitors = []
    for handle, _dc, _rect in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(handle)
        monitors.append({
            "device": info["Device"],
            "rect": info["Monitor"],
            "primary": bool(info["Flags"] & win32con.MONITORINFOF_PRIMARY),
        })
    return sorted(monitors, key=lambda m: (m["rect"][0], m["rect"][1]))


def game_monitor_rect(setting):
    """Resolve the MONITOR config setting to a (left, top, right, bottom) rect."""
    monitors = list_monitors()
    if setting == "primary":
        return next(m["rect"] for m in monitors if m["primary"])
    if setting == "middle":
        return monitors[len(monitors) // 2]["rect"]
    return monitors[int(setting)]["rect"]


def to_screen(monitor_rect, rel_rect):
    """Convert a monitor-relative rect to virtual-screen coordinates."""
    ox, oy = monitor_rect[0], monitor_rect[1]
    left, top, right, bottom = rel_rect
    return (ox + left, oy + top, ox + right, oy + bottom)


def grab(rect):
    """Screenshot a virtual-screen rect and return it as an RGB PIL image."""
    left, top, right, bottom = rect
    width, height = right - left, bottom - top
    screen_dc = win32gui.GetDC(0)
    src_dc = win32ui.CreateDCFromHandle(screen_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(src_dc, width, height)
        mem_dc.SelectObject(bitmap)
        mem_dc.BitBlt((0, 0), (width, height), src_dc, (left, top), win32con.SRCCOPY)
        bits = bitmap.GetBitmapBits(True)
        return Image.frombuffer("RGB", (width, height), bits, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        mem_dc.DeleteDC()
        src_dc.DeleteDC()
        win32gui.ReleaseDC(0, screen_dc)
