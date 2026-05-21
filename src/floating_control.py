"""
Draggable floating recording control.

The control is intentionally thin: it owns only the tiny always-on-top window,
drag persistence, and click callbacks. Recording state still lives in
AIInputApp so hotkeys, tray, preview overlays, and this control stay in sync.
"""

import platform
import queue
import threading
import time

from src.i18n import normalize_ui_language, t
from src.logger import setup_logger
from src.tray import STATE_IDLE, STATE_RECORDING, STATE_PROCESSING

log = setup_logger(__name__)

_CMD_SHOW = "show"
_CMD_HIDE = "hide"
_CMD_STATE = "state"
_CMD_CONFIG = "config"
_CMD_STOP = "stop"

_WIDTH = 86
_HEIGHT = 44
_MARGIN = 24

_PALETTES = {
    "dark": {
        "bg": "#242A33",
        "bg_hover": "#2D3540",
        "border": "#4A5564",
        "text": "#F6F8FA",
        "muted": "#B7C2D0",
        "idle": "#7DD3F0",
        "recording": "#FF6B7A",
        "processing": "#F7D47A",
    },
    "light": {
        "bg": "#FFFFFF",
        "bg_hover": "#F1F5F9",
        "border": "#CBD5E1",
        "text": "#1E293B",
        "muted": "#64748B",
        "idle": "#0EA5E9",
        "recording": "#EF4444",
        "processing": "#D97706",
    },
}


def _normalize_theme(theme):
    theme = str(theme or "dark").strip().lower()
    return theme if theme in _PALETTES else "dark"


class FloatingControl:
    """Small topmost draggable button that mirrors the app recording state."""

    def __init__(
        self,
        enabled=True,
        x=None,
        y=None,
        theme="dark",
        language=None,
        on_toggle=None,
        on_cancel=None,
        on_settings=None,
        on_position=None,
    ):
        self._enabled = bool(enabled)
        self._x = x
        self._y = y
        self._theme = _normalize_theme(theme)
        self._language = normalize_ui_language(language)
        self._on_toggle = on_toggle
        self._on_cancel = on_cancel
        self._on_settings = on_settings
        self._on_position = on_position

        self._state = STATE_IDLE
        self._message = ""
        self._recording_started_at = None

        self._cmd_queue = queue.Queue()
        self._thread = None
        self._started = False
        self._lock = threading.Lock()

    def start(self):
        """Start the UI thread when the floating control is enabled."""
        if not self._enabled:
            return
        self._ensure_thread()
        self._cmd_queue.put((_CMD_SHOW, None))
        self._cmd_queue.put((_CMD_STATE, {"state": self._state, "message": self._message}))

    def stop(self):
        """Stop and destroy the floating window."""
        if self._started:
            self._cmd_queue.put((_CMD_STOP, None))

    def configure(self, enabled=None, x=None, y=None, theme=None, language=None):
        """Update visibility, position, theme, and language after settings save."""
        if enabled is not None:
            self._enabled = bool(enabled)
        if x is not None:
            self._x = x
        if y is not None:
            self._y = y
        if theme is not None:
            self._theme = _normalize_theme(theme)
        if language is not None:
            self._language = normalize_ui_language(language)

        if self._enabled:
            self._ensure_thread()
            self._cmd_queue.put((
                _CMD_CONFIG,
                {
                    "x": self._x,
                    "y": self._y,
                    "theme": self._theme,
                    "language": self._language,
                },
            ))
            self._cmd_queue.put((_CMD_SHOW, None))
            self._cmd_queue.put((_CMD_STATE, {"state": self._state, "message": self._message}))
        elif self._started:
            self._cmd_queue.put((_CMD_HIDE, None))

    def set_state(self, state, message=None):
        """Mirror the current app state."""
        if state not in (STATE_IDLE, STATE_RECORDING, STATE_PROCESSING):
            state = STATE_IDLE
        self._state = state
        self._message = message or ""
        if state == STATE_RECORDING and self._recording_started_at is None:
            self._recording_started_at = time.monotonic()
        elif state != STATE_RECORDING:
            self._recording_started_at = None

        if self._enabled and self._started:
            self._cmd_queue.put((_CMD_STATE, {"state": state, "message": self._message}))

    def _ensure_thread(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _call_callback(self, callback, *args):
        if not callback:
            return

        def _run_callback():
            try:
                callback(*args)
            except Exception as e:
                log.warning("Floating control callback failed: %s", e)

        threading.Thread(target=_run_callback, daemon=True).start()

    def _run(self):
        try:
            import tkinter as tk
        except ImportError:
            log.warning("tkinter 不可用，悬浮按钮已禁用")
            return

        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            root.title("Vox Floating Control")
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.resizable(False, False)

            if platform.system() == "Windows":
                root.after(0, lambda: self._set_no_activate(root))

            state = {
                "visible": False,
                "hover": False,
                "dragged": False,
                "press_x": 0,
                "press_y": 0,
                "win_x": 0,
                "win_y": 0,
                "current": self._state,
                "flash_until": 0.0,
                "flash_text": "",
            }

            frame = tk.Frame(
                root,
                bg=_PALETTES[self._theme]["bg"],
                width=_WIDTH,
                height=_HEIGHT,
                highlightthickness=1,
                highlightbackground=_PALETTES[self._theme]["border"],
                cursor="hand2",
            )
            frame.pack(fill="both", expand=True)
            frame.pack_propagate(False)

            row = tk.Frame(frame, bg=_PALETTES[self._theme]["bg"])
            row.pack(fill="both", expand=True, padx=9, pady=7)

            dot = tk.Canvas(row, width=14, height=14, bg=_PALETTES[self._theme]["bg"], bd=0, highlightthickness=0)
            dot.pack(side="left", padx=(0, 8), pady=(7, 0))
            dot_id = dot.create_oval(2, 2, 12, 12, fill=_PALETTES[self._theme]["idle"], outline="")

            text_col = tk.Frame(row, bg=_PALETTES[self._theme]["bg"])
            text_col.pack(side="left", fill="both", expand=True)
            title = tk.Label(
                text_col,
                text="MIC",
                bg=_PALETTES[self._theme]["bg"],
                fg=_PALETTES[self._theme]["text"],
                font=("Segoe UI Semibold", 9),
                anchor="w",
            )
            title.pack(fill="x")
            detail = tk.Label(
                text_col,
                text=t("点击录音", self._language),
                bg=_PALETTES[self._theme]["bg"],
                fg=_PALETTES[self._theme]["muted"],
                font=("Segoe UI", 8),
                anchor="w",
            )
            detail.pack(fill="x")

            def palette():
                return _PALETTES[self._theme]

            def apply_theme():
                p = palette()
                bg = p["bg_hover"] if state["hover"] else p["bg"]
                for widget in (frame, row, text_col, title, detail, dot):
                    try:
                        widget.configure(bg=bg)
                    except Exception:
                        pass
                frame.configure(highlightbackground=p["border"])
                title.configure(fg=p["text"])
                detail.configure(fg=p["muted"])

            def default_position():
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                return max(0, sw - _WIDTH - _MARGIN), max(0, (sh - _HEIGHT) // 2)

            def clamp_position(x, y):
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                return (
                    min(max(0, int(x)), max(0, sw - _WIDTH)),
                    min(max(0, int(y)), max(0, sh - _HEIGHT)),
                )

            def set_geometry(x=None, y=None):
                if x is None or y is None:
                    x0, y0 = default_position()
                else:
                    x0, y0 = clamp_position(x, y)
                root.geometry(f"{_WIDTH}x{_HEIGHT}+{x0}+{y0}")

            def elapsed_text():
                if self._recording_started_at is None:
                    return "00:00"
                elapsed = max(0, int(time.monotonic() - self._recording_started_at))
                return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

            def render_state():
                p = palette()
                current = state["current"]
                flash_active = time.monotonic() < state["flash_until"]
                if current == STATE_RECORDING:
                    dot_color = p["recording"]
                    label = "REC"
                    sub = elapsed_text()
                elif current == STATE_PROCESSING:
                    dot_color = p["processing"]
                    label = "AI"
                    sub = state["flash_text"] if flash_active else t("处理中", self._language)
                else:
                    dot_color = p["idle"]
                    label = "MIC"
                    sub = state["flash_text"] if flash_active else t("点击录音", self._language)
                dot.itemconfigure(dot_id, fill=dot_color)
                title.configure(text=label)
                detail.configure(text=sub)

            def show():
                state["visible"] = True
                if self._x is None or self._y is None:
                    set_geometry()
                else:
                    set_geometry(self._x, self._y)
                root.deiconify()
                root.lift()

            def hide():
                state["visible"] = False
                root.withdraw()

            def handle_click():
                if state["current"] == STATE_PROCESSING:
                    state["flash_until"] = time.monotonic() + 1.2
                    state["flash_text"] = t("处理中", self._language)
                    render_state()
                    return
                self._call_callback(self._on_toggle)

            def on_press(event):
                state["dragged"] = False
                state["press_x"] = event.x_root
                state["press_y"] = event.y_root
                state["win_x"] = root.winfo_x()
                state["win_y"] = root.winfo_y()

            def on_motion(event):
                dx = event.x_root - state["press_x"]
                dy = event.y_root - state["press_y"]
                if abs(dx) + abs(dy) > 3:
                    state["dragged"] = True
                x, y = clamp_position(state["win_x"] + dx, state["win_y"] + dy)
                root.geometry(f"{_WIDTH}x{_HEIGHT}+{x}+{y}")

            def on_release(_event):
                if state["dragged"]:
                    self._x = root.winfo_x()
                    self._y = root.winfo_y()
                    self._call_callback(self._on_position, self._x, self._y)
                    return
                handle_click()

            def on_enter(_event):
                state["hover"] = True
                apply_theme()

            def on_leave(_event):
                state["hover"] = False
                apply_theme()

            def on_right_click(_event):
                if state["current"] == STATE_RECORDING:
                    self._call_callback(self._on_cancel)
                else:
                    self._call_callback(self._on_settings)

            for widget in (frame, row, text_col, title, detail, dot):
                widget.bind("<ButtonPress-1>", on_press, add="+")
                widget.bind("<B1-Motion>", on_motion, add="+")
                widget.bind("<ButtonRelease-1>", on_release, add="+")
                widget.bind("<Enter>", on_enter, add="+")
                widget.bind("<Leave>", on_leave, add="+")
                widget.bind("<Button-3>", on_right_click, add="+")

            set_geometry(self._x, self._y)
            apply_theme()
            render_state()

            def poll_queue():
                try:
                    while True:
                        cmd, payload = self._cmd_queue.get_nowait()
                        if cmd == _CMD_SHOW:
                            show()
                        elif cmd == _CMD_HIDE:
                            hide()
                        elif cmd == _CMD_STATE:
                            state["current"] = payload.get("state", STATE_IDLE)
                            if state["current"] == STATE_RECORDING and self._recording_started_at is None:
                                self._recording_started_at = time.monotonic()
                            elif state["current"] != STATE_RECORDING:
                                self._recording_started_at = None
                            state["flash_text"] = payload.get("message") or ""
                            state["flash_until"] = time.monotonic() + 1.4 if state["flash_text"] else 0.0
                            render_state()
                        elif cmd == _CMD_CONFIG:
                            self._x = payload.get("x")
                            self._y = payload.get("y")
                            self._theme = _normalize_theme(payload.get("theme"))
                            self._language = normalize_ui_language(payload.get("language"))
                            apply_theme()
                            render_state()
                            if state["visible"]:
                                show()
                        elif cmd == _CMD_STOP:
                            root.destroy()
                            return
                except queue.Empty:
                    pass
                if root.winfo_exists():
                    root.after(80, poll_queue)

            def tick():
                if root.winfo_exists():
                    if state["current"] == STATE_RECORDING or state["flash_until"]:
                        render_state()
                    root.after(500, tick)

            root.after(80, poll_queue)
            root.after(500, tick)
            root.mainloop()
        except Exception as e:
            log.warning("悬浮按钮运行失败: %s", e)
        finally:
            self._started = False
            try:
                if root and root.winfo_exists():
                    root.destroy()
            except Exception:
                pass

    def _set_no_activate(self, root):
        """Prevent the floating window from stealing focus on Windows."""
        if platform.system() != "Windows":
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = root.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOPMOST = 0x00000008
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:
            log.debug("设置悬浮按钮 no-activate 失败: %s", e)
