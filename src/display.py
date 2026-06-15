"""Display geometry and scaling helpers for Windows multi-monitor setups."""

from __future__ import annotations

import platform


def _is_windows():
    return platform.system() == "Windows"


def get_cursor_pos():
    """Return the current cursor position in virtual-screen coordinates."""
    if not _is_windows():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        point = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return int(point.x), int(point.y)
    except Exception:
        return None
    return None


def get_virtual_screen_rect():
    """Return (left, top, right, bottom) for the full virtual desktop."""
    if not _is_windows():
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        left = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
        top = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
        width = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
        height = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
        if width > 0 and height > 0:
            return left, top, left + width, top + height
    except Exception:
        return None
    return None


def get_monitor_rect_for_point(x=None, y=None):
    """Return the monitor rect nearest a point, or None on failure."""
    if not _is_windows():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        if x is None or y is None:
            pos = get_cursor_pos()
            if pos is None:
                return None
            x, y = pos

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        point = wintypes.POINT(int(x), int(y))
        monitor = user32.MonitorFromPoint(point, 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return None
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        rect = info.rcWork
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    except Exception:
        return None


def display_scale_for_point(x=None, y=None):
    """
    Return a conservative UI scale for the monitor nearest a point.

    Effective DPI follows Windows display scaling. Raw DPI helps on large
    high-resolution monitors that are left at 100% scaling, but is capped so
    tiny high-DPI laptop panels do not become comically large.
    """
    if not _is_windows():
        return 1.0
    try:
        import ctypes
        from ctypes import wintypes

        if x is None or y is None:
            pos = get_cursor_pos()
            if pos is None:
                return 1.0
            x, y = pos

        user32 = ctypes.windll.user32
        point = wintypes.POINT(int(x), int(y))
        monitor = user32.MonitorFromPoint(point, 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return 1.0

        shcore = ctypes.windll.shcore

        def dpi_for_type(dpi_type):
            dpi_x = ctypes.c_uint(96)
            dpi_y = ctypes.c_uint(96)
            if shcore.GetDpiForMonitor(monitor, dpi_type, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                return max(1.0, float(dpi_x.value) / 96.0)
            return 1.0

        effective = dpi_for_type(0)  # MDT_EFFECTIVE_DPI
        raw = dpi_for_type(2)  # MDT_RAW_DPI
        physical = min(max(raw, 1.0), 1.6)
        rect = get_monitor_rect_for_point(x, y)
        resolution = 1.0
        if rect:
            left, top, right, bottom = rect
            width = max(1, int(right) - int(left))
            height = max(1, int(bottom) - int(top))
            resolution = min(max(min(width / 1920.0, height / 1080.0), 1.0), 1.45)
        return min(max(effective, physical, resolution), 2.5)
    except Exception:
        return 1.0


def tk_scaling_for_current_monitor():
    """Return Tk pixels-per-point scaling for the monitor under the cursor."""
    return (96.0 / 72.0) * display_scale_for_point()
