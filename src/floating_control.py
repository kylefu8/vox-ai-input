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
import math
from functools import lru_cache

from src.debug_trace import trace_floating_state
from src.display import display_scale_for_point, get_virtual_screen_rect
from src.i18n import normalize_ui_language, t
from src.logger import setup_logger
from src.tk_runtime import acquire_tk_root, release_tk_root
from src.tray import STATE_IDLE, STATE_RECORDING, STATE_PROCESSING
from src.ui_theme import FLOATING_THEMES, normalize_ui_theme

log = setup_logger(__name__)

_CMD_SHOW = "show"
_CMD_HIDE = "hide"
_CMD_STATE = "state"
_CMD_CONFIG = "config"
_CMD_LEVEL = "level"
_CMD_RESET_IDLE = "reset_idle"
_CMD_STOP = "stop"
_WM_WAKE = 0x8000 + 71

_IDLE_WIDTH = 42
_PROCESSING_WIDTH = 134
_ACTIVE_WIDTH = 178
_WIDTH = _ACTIVE_WIDTH
_HEIGHT = 42
_MARGIN = 24
_TRANSPARENT = "#010203"
_RENDER_SCALE = 4
_ICON_RING_RADIUS = 12.0
_ICON_RING_WIDTH = 3.0
_MIN_UI_SCALE = 1.0
_MAX_UI_SCALE = 2.5

_PALETTES = FLOATING_THEMES


def _normalize_theme(theme):
    return normalize_ui_theme(theme)


def _control_width(current, hover=False, flash_visible=False):
    if current == STATE_RECORDING:
        return _ACTIVE_WIDTH
    if current == STATE_PROCESSING:
        return _PROCESSING_WIDTH
    if hover or flash_visible:
        return _PROCESSING_WIDTH
    return _IDLE_WIDTH


def _normalize_ui_scale(scale):
    try:
        value = float(scale)
    except (TypeError, ValueError):
        return 1.0
    return min(max(value, _MIN_UI_SCALE), _MAX_UI_SCALE)


def _scaled_dim(value, ui_scale=1.0):
    return max(1, int(round(float(value) * _normalize_ui_scale(ui_scale))))


def _scaled_pixel(value, scale):
    try:
        return max(1, int(round(float(value) * float(scale))))
    except (TypeError, ValueError):
        return max(1, int(round(float(value))))


def _control_width_scaled(current, hover=False, flash_visible=False, ui_scale=1.0):
    return _scaled_dim(_control_width(current, hover, flash_visible), ui_scale)


def _control_height_scaled(ui_scale=1.0):
    return _scaled_dim(_HEIGHT, ui_scale)


def _ui_scale_for_point(x=None, y=None):
    return _normalize_ui_scale(display_scale_for_point(x, y))


def _clamp_position_for_screen(x, y, width, screen_width, screen_height, height=_HEIGHT):
    return (
        min(max(0, int(x)), max(0, int(screen_width) - int(width))),
        min(max(0, int(y)), max(0, int(screen_height) - int(height))),
    )


def _clamp_position_for_rect(x, y, width, rect, height=_HEIGHT):
    left, top, right, bottom = rect
    return (
        min(max(int(left), int(x)), max(int(left), int(right) - int(width))),
        min(max(int(top), int(y)), max(int(top), int(bottom) - int(height))),
    )


def _default_position_for_rect(rect, width, height=_HEIGHT):
    left, top, right, bottom = rect
    return (
        max(int(left), int(right) - int(width) - _MARGIN),
        max(int(top), int(top) + (int(bottom) - int(top) - int(height)) // 2),
    )


def _default_position_for_screen(screen_width, screen_height, width, height=_HEIGHT):
    return (
        max(0, int(screen_width) - int(width) - _MARGIN),
        max(0, (int(screen_height) - int(height)) // 2),
    )


def _window_position_from_resting(rest_x, rest_y, width, screen_width, screen_height):
    """Convert the saved idle-button position to the current rendered width."""
    if rest_x is None or rest_y is None:
        return _default_position_for_screen(screen_width, screen_height, width)
    x = int(rest_x) + _IDLE_WIDTH - int(width)
    return _clamp_position_for_screen(x, rest_y, width, screen_width, screen_height)


def _window_position_from_resting_rect(rest_x, rest_y, width, rect, idle_width=_IDLE_WIDTH, height=_HEIGHT):
    """Convert the saved idle-button position to current width on a virtual desktop."""
    if rest_x is None or rest_y is None:
        return _default_position_for_rect(rect, width, height=height)
    x = int(rest_x) + int(idle_width) - int(width)
    return _clamp_position_for_rect(x, rest_y, width, rect, height=height)


def _resting_position_from_window(left, top, width, screen_width, screen_height):
    """Convert any expanded window rect back to the saved idle-button position."""
    x = int(left) + int(width) - _IDLE_WIDTH
    return _clamp_position_for_screen(x, top, _IDLE_WIDTH, screen_width, screen_height)


def _resting_position_from_window_rect(left, top, width, rect, idle_width=_IDLE_WIDTH, height=_HEIGHT):
    """Convert expanded rect back to idle-button position on a virtual desktop."""
    x = int(left) + int(width) - int(idle_width)
    return _clamp_position_for_rect(x, top, idle_width, rect, height=height)


def _rgba(hex_color, alpha=255):
    value = hex_color.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
        int(alpha),
    )


@lru_cache(maxsize=64)
def _load_render_font(size, scale, bold=False, icon=False):
    from PIL import ImageFont

    if icon:
        candidates = (
            r"C:\Windows\Fonts\segmdl2.ttf",
            r"C:\Windows\Fonts\SegoeIcons.ttf",
            "arial.ttf",
        )
    elif bold:
        candidates = (
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\segoeuisb.ttf",
            "arialbd.ttf",
        )
    else:
        candidates = (
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\segoeui.ttf",
            "arial.ttf",
        )
    for name in candidates:
        try:
            return ImageFont.truetype(name, int(round(size * scale)))
        except Exception:
            continue
    return ImageFont.load_default()


def _sc(value, scale):
    return int(round(value * scale))


def _text_width(draw, text, font):
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    if _text_width(draw, text, font) <= max_width:
        return text
    suffix = "..."
    for length in range(max(0, len(text) - 1), 0, -1):
        candidate = text[:length].rstrip() + suffix
        if _text_width(draw, candidate, font) <= max_width:
            return candidate
    return suffix


def _draw_center_text(draw, xy, text, font, fill, scale):
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (
            _sc(xy[0], scale) - (bbox[0] + bbox[2]) / 2,
            _sc(xy[1], scale) - (bbox[1] + bbox[3]) / 2,
        ),
        text,
        font=font,
        fill=fill,
    )


def _draw_left_center_text(draw, x, center_y, text, font, fill, scale):
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (
            _sc(x, scale) - bbox[0],
            _sc(center_y, scale) - (bbox[1] + bbox[3]) / 2,
        ),
        text,
        font=font,
        fill=fill,
    )


def _draw_mic(draw, cx, cy, color, scale, strong=False):
    """Draw a tiny vector mic that fits the shared 12px icon ring."""
    stroke = max(1, _sc(1.55 if strong else 1.35, scale))
    half_w = 3.35 if strong else 2.85
    top = 7.25 if strong else 6.9
    bottom = 2.0 if strong else 1.55
    body = (
        _sc(cx - half_w, scale),
        _sc(cy - top, scale),
        _sc(cx + half_w, scale),
        _sc(cy + bottom, scale),
    )
    draw.rounded_rectangle(
        body,
        radius=_sc(half_w, scale),
        fill=color,
    )
    draw.line(
        (_sc(cx, scale), _sc(cy + bottom + 1.0, scale), _sc(cx, scale), _sc(cy + 6.05, scale)),
        fill=color,
        width=stroke,
    )
    draw.line(
        (_sc(cx - 4.55, scale), _sc(cy + 6.05, scale), _sc(cx + 4.55, scale), _sc(cy + 6.05, scale)),
        fill=color,
        width=stroke,
    )


def _ring_box(cx, cy, scale, radius=_ICON_RING_RADIUS):
    return (
        _sc(cx - radius, scale),
        _sc(cy - radius, scale),
        _sc(cx + radius, scale),
        _sc(cy + radius, scale),
    )


def _draw_ring(draw, cx, cy, color, alpha, scale, radius=_ICON_RING_RADIUS, width=_ICON_RING_WIDTH):
    draw.ellipse(
        _ring_box(cx, cy, scale, radius=radius),
        outline=_rgba(color, alpha),
        width=max(1, _sc(width, scale)),
    )


def _draw_cancel(draw, cx, cy, p, cancel_hover, scale):
    cx = _sc(cx, scale)
    cy = _sc(cy, scale)
    bg_alpha = 174 if cancel_hover else 128
    ring_alpha = 255 if cancel_hover else 238
    draw.ellipse(
        (cx - _sc(_ICON_RING_RADIUS, scale), cy - _sc(_ICON_RING_RADIUS, scale), cx + _sc(_ICON_RING_RADIUS, scale), cy + _sc(_ICON_RING_RADIUS, scale)),
        fill=_rgba(p["recording"], bg_alpha),
        outline=_rgba(p["recording"], ring_alpha),
        width=max(1, _sc(_ICON_RING_WIDTH, scale)),
    )
    x_len = 4.75
    x_width = max(1, _sc(2.05, scale))
    draw.line((cx - _sc(x_len, scale), cy - _sc(x_len, scale), cx + _sc(x_len, scale), cy + _sc(x_len, scale)), fill=_rgba("#FFFFFF", 255), width=x_width)
    draw.line((cx + _sc(x_len, scale), cy - _sc(x_len, scale), cx - _sc(x_len, scale), cy + _sc(x_len, scale)), fill=_rgba("#FFFFFF", 255), width=x_width)


def _draw_level_meter(draw, x0, center_y, values, p, scale):
    bar_w = 4.0
    gap = 7.0
    for i, value in enumerate(values[:7]):
        value = max(0.0, min(1.0, float(value)))
        height = max(5.0, min(18.0, 5.0 + value * 17.0))
        x = x0 + i * gap
        alpha = 128 + int(value * 104)
        draw.rounded_rectangle(
            (
                _sc(x, scale),
                _sc(center_y - height / 2, scale),
                _sc(x + bar_w, scale),
                _sc(center_y + height / 2, scale),
            ),
            radius=_sc(2.0, scale),
            fill=_rgba(p["bars"], alpha),
        )


def _elapsed_text(recording_started_at, now):
    if recording_started_at is None:
        return "00:00"
    elapsed = max(0, int(now - recording_started_at))
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"


def _render_control_image(
    *,
    theme,
    language,
    current,
    hover=False,
    pressed=False,
    cancel_hover=False,
    flash_text="",
    flash_until=0.0,
    phase=0.0,
    bars=None,
    recording_started_at=None,
    now=None,
    ui_scale=1.0,
):
    from PIL import Image, ImageDraw

    now = time.monotonic() if now is None else now
    flash_visible = bool(flash_text) and now < flash_until
    width = _control_width(current, hover, flash_visible)
    ui_scale = _normalize_ui_scale(ui_scale)
    scale = _RENDER_SCALE * ui_scale
    out_width = _scaled_dim(width, ui_scale)
    out_height = _control_height_scaled(ui_scale)
    p = _PALETTES[_normalize_theme(theme)]
    bars = bars or [0.12] * 9

    img = Image.new("RGBA", (_scaled_pixel(width, scale), _scaled_pixel(_HEIGHT, scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    pulse = (math.sin(phase) + 1) / 2
    bg_key = "bg_press" if pressed else ("bg_hover" if hover else "bg")
    cx = width / 2 if width == _IDLE_WIDTH else 22
    cy = _HEIGHT / 2 if width == _IDLE_WIDTH else 20.0

    detail_font = _load_render_font(11, scale)
    timer_font = _load_render_font(10.5, scale, bold=True)

    if current == STATE_IDLE and width == _IDLE_WIDTH:
        body_radius = 15.0
        idle_fill = p["bg_press"] if pressed else p.get("idle_bg", p[bg_key])
        draw.ellipse(
            (
                _sc(cx - body_radius, scale),
                _sc(cy - body_radius, scale),
                _sc(cx + body_radius, scale),
                _sc(cy + body_radius, scale),
            ),
            fill=_rgba(idle_fill, 255),
        )
        _draw_ring(draw, cx, cy, p["idle"], 174, scale)
        _draw_mic(draw, cx, cy, _rgba(p["icon"], 246), scale)
        return img.resize((out_width, out_height), Image.Resampling.LANCZOS)

    shadow = (_sc(5, scale), _sc(7, scale), _sc(width - 2, scale), _sc(_HEIGHT - 1, scale))
    body = (_sc(2, scale), _sc(2, scale), _sc(width - 3, scale), _sc(_HEIGHT - 5, scale))
    draw.rounded_rectangle(shadow, radius=_sc(19, scale), fill=_rgba(p["shadow"], 34))

    draw.rounded_rectangle(
        body,
        radius=_sc(19, scale),
        fill=_rgba(p[bg_key], 244),
    )
    if current == STATE_RECORDING:
        ring = 13.0 + pulse * 2.2
        draw.ellipse(
            (_sc(cx - ring, scale), _sc(cy - ring, scale), _sc(cx + ring, scale), _sc(cy + ring, scale)),
            fill=_rgba(p["recording"], 34 + int(pulse * 24)),
        )
        draw.ellipse(_ring_box(cx, cy, scale), fill=_rgba(p["recording"], 72))
        _draw_ring(draw, cx, cy, p["recording"], 255, scale)
        _draw_mic(draw, cx, cy, _rgba("#FFFFFF", 255), scale, strong=True)

        _draw_level_meter(draw, 51, cy, bars, p, scale)

        _draw_center_text(draw, (124, cy), _elapsed_text(recording_started_at, now), timer_font, _rgba(p["text"], 232), scale)
        _draw_cancel(draw, width - 21, cy, p, cancel_hover, scale)

    elif current == STATE_PROCESSING:
        start = int((phase * 120) % 360)
        ring_box = _ring_box(cx, cy, scale)
        draw.ellipse(ring_box, outline=_rgba(p["processing"], 52), width=max(1, _sc(3, scale)))
        draw.arc(ring_box, start=start, end=start + 248, fill=_rgba(p["processing"], 232), width=max(1, _sc(3, scale)))
        sub = flash_text if flash_visible else t("处理中", language)
        sub = _fit_text(draw, sub, detail_font, _sc(78, scale))
        _draw_left_center_text(draw, 48, cy, sub, detail_font, _rgba(p["text"], 204 + int(pulse * 34)), scale)
        for i in range(3):
            dot_alpha = 76 + int(((math.sin(phase + i * 0.82) + 1) / 2) * 116)
            x = width - 31 + i * 7
            draw.ellipse((_sc(x, scale), _sc(cy - 2.3, scale), _sc(x + 4.4, scale), _sc(cy + 2.3, scale)), fill=_rgba(p["processing"], dot_alpha))

    else:
        draw.ellipse(_ring_box(cx, cy, scale), fill=_rgba(p["icon_bg"], 156))
        _draw_ring(draw, cx, cy, p["idle"], 174, scale)
        _draw_mic(draw, cx, cy, _rgba(p["icon"], 244), scale)
        sub = flash_text if flash_visible else t("点击录音", language)
        sub = _fit_text(draw, sub, detail_font, _sc(width - 66, scale))
        _draw_left_center_text(draw, 48, cy, sub, detail_font, _rgba(p["text"], 228), scale)
        handle_x = width - 18
        for i in range(3):
            y = cy - 6 + i * 6
            draw.ellipse(
                (_sc(handle_x - 1.7, scale), _sc(y - 1.7, scale), _sc(handle_x + 1.7, scale), _sc(y + 1.7, scale)),
                fill=_rgba(p["muted"], 112),
            )

    return img.resize((out_width, out_height), Image.Resampling.LANCZOS)


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
        self._state_seq = 0
        self._recording_started_at = None

        self._cmd_queue = queue.Queue()
        self._thread = None
        self._started = False
        self._lock = threading.Lock()
        self._reset_lock = threading.Lock()
        self._reset_pending = False
        self._window_x = None
        self._window_y = None
        self._window_width = None
        self._window_height = _HEIGHT
        self._window_scale = 1.0
        self._native_hwnd = None

    def get_preview_anchor_rect(self):
        """Return the current screen rect used to anchor the preview capsule."""
        if not self._enabled:
            return None

        ui_scale = _normalize_ui_scale(self._window_scale or _ui_scale_for_point(self._x, self._y))
        width = int(self._window_width or _control_width_scaled(
            self._state,
            hover=False,
            flash_visible=bool(self._message),
            ui_scale=ui_scale,
        ))
        height = int(self._window_height or _control_height_scaled(ui_scale))
        x = self._window_x
        y = self._window_y

        if x is None or y is None:
            rect = self._screen_rect()
            idle_width = _scaled_dim(_IDLE_WIDTH, ui_scale)
            x, y = _window_position_from_resting_rect(self._x, self._y, width, rect, idle_width, height)

        return (int(x), int(y), width, height)

    @staticmethod
    def _screen_rect():
        if platform.system() == "Windows":
            rect = get_virtual_screen_rect()
            if rect:
                return rect
        return (0, 0, 1920, 1080)

    def start(self):
        """Start the UI thread when the floating control is enabled."""
        if not self._enabled:
            return
        self._ensure_thread()
        self._cmd_queue.put((_CMD_SHOW, None))
        self._cmd_queue.put((_CMD_STATE, {"state": self._state, "message": self._message, "seq": self._state_seq}))
        self._wake_ui_thread()

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
            self._cmd_queue.put((_CMD_STATE, {"state": self._state, "message": self._message, "seq": self._state_seq}))
            self._wake_ui_thread()
        elif self._started:
            self._cmd_queue.put((_CMD_HIDE, None))
            self._wake_ui_thread()

    def set_state(self, state, message=None):
        """Mirror the current app state."""
        if state not in (STATE_IDLE, STATE_RECORDING, STATE_PROCESSING):
            state = STATE_IDLE
        previous_state = self._state
        previous_width = self._window_width
        self._state = state
        self._message = message or ""
        self._state_seq += 1
        trace_floating_state(
            "floating.set_state",
            state=state,
            message=self._message,
            seq=self._state_seq,
            enabled=self._enabled,
            started=self._started,
            hwnd=self._native_hwnd,
        )
        if state == STATE_RECORDING and self._recording_started_at is None:
            self._recording_started_at = time.monotonic()
        elif state != STATE_RECORDING:
            self._recording_started_at = None

        if self._enabled and self._started:
            previous_idle_width = _scaled_dim(_IDLE_WIDTH, self._window_scale)
            needs_native_idle_reset = (
                state == STATE_IDLE
                and platform.system() == "Windows"
                and self._native_hwnd
                and (
                    previous_state != STATE_IDLE
                    or (previous_width is not None and int(previous_width) != previous_idle_width)
                )
            )
            if needs_native_idle_reset:
                self._cmd_queue.put((
                    _CMD_RESET_IDLE,
                    {
                        "state": state,
                        "message": self._message,
                        "seq": self._state_seq,
                    },
                ))
                self._wake_ui_thread()
                self._schedule_native_idle_reset()
                return
            self._cmd_queue.put((
                _CMD_STATE,
                {
                    "state": state,
                    "message": self._message,
                    "seq": self._state_seq,
                },
            ))
            self._wake_ui_thread()

    def set_audio_level(self, level):
        """Update the live mic level used by the recording visualizer."""
        try:
            level = max(0.0, min(1.0, float(level)))
        except (TypeError, ValueError):
            return
        if self._enabled and self._started:
            self._cmd_queue.put((_CMD_LEVEL, {"level": level}))

    def _wake_ui_thread(self):
        """Wake the native floating window so state updates are not timer-dependent."""
        if platform.system() != "Windows" or not self._native_hwnd:
            trace_floating_state("floating.wake.skipped", hwnd=self._native_hwnd, platform=platform.system())
            return
        try:
            import ctypes

            result = ctypes.windll.user32.PostMessageW(int(self._native_hwnd), _WM_WAKE, 0, 0)
            trace_floating_state("floating.wake.posted", hwnd=self._native_hwnd, result=bool(result))
        except Exception as e:
            trace_floating_state("floating.wake.error", hwnd=self._native_hwnd, error=repr(e))
            pass

    def _schedule_native_idle_reset(self):
        """Restart the native layered window after an idle reset command closes it."""
        with self._reset_lock:
            if self._reset_pending:
                return
            self._reset_pending = True

        def _restart():
            try:
                for _ in range(30):
                    if not self._started and not self._native_hwnd:
                        break
                    time.sleep(0.05)

                if not self._enabled:
                    return

                trace_floating_state(
                    "floating.native_reset.restart",
                    state=self._state,
                    seq=self._state_seq,
                    started=self._started,
                    hwnd=self._native_hwnd,
                )
                self._ensure_thread()
                self._cmd_queue.put((_CMD_SHOW, None))
                self._cmd_queue.put((
                    _CMD_STATE,
                    {
                        "state": self._state,
                        "message": self._message,
                        "seq": self._state_seq,
                    },
                ))
                self._wake_ui_thread()
            finally:
                with self._reset_lock:
                    self._reset_pending = False

        threading.Thread(target=_restart, daemon=True, name="floating-idle-reset").start()

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
        if platform.system() == "Windows":
            try:
                self._run_windows_layered()
                return
            except ImportError as e:
                log.debug("原生悬浮按钮依赖不可用，回退 Tk: %s", e)
            except Exception as e:
                log.warning("原生悬浮按钮运行失败，回退 Tk: %s", e)
        self._run_tk()

    def _run_windows_layered(self):
        import ctypes
        from ctypes import wintypes

        import numpy as np
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        kernel32 = ctypes.windll.kernel32

        WS_POPUP = 0x80000000
        WS_EX_LAYERED = 0x00080000
        WS_EX_TOPMOST = 0x00000008
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        SW_HIDE = 0
        SW_SHOWNOACTIVATE = 4
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        HWND_TOPMOST = -1
        WM_DESTROY = 0x0002
        WM_LBUTTONDOWN = 0x0201
        WM_LBUTTONUP = 0x0202
        WM_RBUTTONUP = 0x0205
        WM_MOUSEMOVE = 0x0200
        WM_MOUSELEAVE = 0x02A3
        WM_TIMER = 0x0113
        WM_SETCURSOR = 0x0020
        WM_NCHITTEST = 0x0084
        HTCLIENT = 1
        IDC_HAND = 32649
        ULW_ALPHA = 0x00000002
        AC_SRC_OVER = 0
        AC_SRC_ALPHA = 1
        BI_RGB = 0
        DIB_RGB_COLORS = 0
        TME_LEAVE = 0x00000002
        HANDLE = wintypes.HANDLE
        UINT_PTR = getattr(wintypes, "UINT_PTR", ctypes.c_size_t)
        kernel32.GetModuleHandleW.restype = HANDLE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class SIZE(ctypes.Structure):
            _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [
                ("BlendOp", wintypes.BYTE),
                ("BlendFlags", wintypes.BYTE),
                ("SourceConstantAlpha", wintypes.BYTE),
                ("AlphaFormat", wintypes.BYTE),
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", HANDLE),
                ("hIcon", HANDLE),
                ("hCursor", HANDLE),
                ("hbrBackground", HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", POINT),
            ]

        class TRACKMOUSEEVENT(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("hwndTrack", wintypes.HWND),
                ("dwHoverTime", wintypes.DWORD),
            ]

        user32.DefWindowProcW.restype = ctypes.c_longlong
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            HANDLE,
            HANDLE,
            ctypes.c_void_p,
        ]
        user32.LoadCursorW.restype = HANDLE
        user32.LoadCursorW.argtypes = [HANDLE, ctypes.c_void_p]
        user32.GetDC.restype = HANDLE
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.ReleaseDC.argtypes = [wintypes.HWND, HANDLE]
        user32.UpdateLayeredWindow.restype = wintypes.BOOL
        user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND,
            HANDLE,
            ctypes.POINTER(POINT),
            ctypes.POINTER(SIZE),
            HANDLE,
            ctypes.POINTER(POINT),
            wintypes.DWORD,
            ctypes.POINTER(BLENDFUNCTION),
            wintypes.DWORD,
        ]
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.SetTimer.restype = UINT_PTR
        user32.SetTimer.argtypes = [wintypes.HWND, UINT_PTR, wintypes.UINT, ctypes.c_void_p]
        user32.KillTimer.argtypes = [wintypes.HWND, UINT_PTR]
        user32.SetCapture.argtypes = [wintypes.HWND]
        user32.ReleaseCapture.argtypes = []
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
        kernel32.GetLastError.restype = wintypes.DWORD
        gdi32.CreateCompatibleDC.restype = HANDLE
        gdi32.CreateCompatibleDC.argtypes = [HANDLE]
        gdi32.CreateDIBSection.restype = HANDLE
        gdi32.CreateDIBSection.argtypes = [
            HANDLE,
            ctypes.POINTER(BITMAPINFO),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            HANDLE,
            wintypes.DWORD,
        ]
        gdi32.SelectObject.restype = HANDLE
        gdi32.SelectObject.argtypes = [HANDLE, HANDLE]
        gdi32.DeleteObject.argtypes = [HANDLE]
        gdi32.DeleteDC.argtypes = [HANDLE]

        state = {
            "visible": False,
            "hover": False,
            "dragged": False,
            "pressed": False,
            "cancel_hover": False,
            "press_x": 0,
            "press_y": 0,
            "win_x": 0,
            "win_y": 0,
            "current": self._state,
            "flash_until": 0.0,
            "flash_text": "",
            "phase": 0.0,
            "level": 0.0,
            "level_target": 0.0,
            "last_level_at": 0.0,
            "bars": [0.12] * 9,
            "window_width": 0,
            "window_height": _HEIGHT,
            "ui_scale": 1.0,
            "seq": 0,
            "hwnd": None,
            "running": True,
            "last_trace_tick": 0.0,
        }

        def current_scale():
            return _normalize_ui_scale(state.get("ui_scale", 1.0))

        def current_height():
            return _control_height_scaled(current_scale())

        def current_width():
            return _control_width_scaled(
                state["current"],
                hover=state["hover"],
                flash_visible=bool(state["flash_text"]) and time.monotonic() < state["flash_until"],
                ui_scale=current_scale(),
            )

        def current_idle_width():
            return _scaled_dim(_IDLE_WIDTH, current_scale())

        def sync_ui_scale(x=None, y=None):
            if x is None or y is None:
                if self._x is not None and self._y is not None:
                    x, y = self._x, self._y
            state["ui_scale"] = _ui_scale_for_point(x, y)
            return state["ui_scale"]

        def draw_widget():
            return _render_control_image(
                theme=self._theme,
                language=self._language,
                current=state["current"],
                hover=state["hover"],
                pressed=state["pressed"],
                cancel_hover=state["cancel_hover"],
                flash_text=state["flash_text"],
                flash_until=state["flash_until"],
                phase=state["phase"],
                bars=state["bars"],
                recording_started_at=self._recording_started_at,
                ui_scale=current_scale(),
            )

        def screen_rect():
            return get_virtual_screen_rect() or (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))

        def default_position():
            width = current_width()
            return _default_position_for_rect(screen_rect(), width, height=current_height())

        def anchored_position(width=None):
            width = current_width() if width is None else width
            return _window_position_from_resting_rect(
                self._x,
                self._y,
                width,
                screen_rect(),
                idle_width=current_idle_width(),
                height=current_height(),
            )

        def clamp_position(x, y, width=None):
            width = current_width() if width is None else width
            return _clamp_position_for_rect(x, y, width, screen_rect(), height=current_height())

        def get_window_rect():
            rect = wintypes.RECT()
            user32.GetWindowRect(state["hwnd"], ctypes.byref(rect))
            return rect.left, rect.top, rect.right, rect.bottom

        def remember_resting_position(left=None, top=None, width=None):
            if left is None or top is None:
                left, top, right, _ = get_window_rect()
                width = right - left
            width = state["window_width"] or current_width() if width is None else width
            rest_x, rest_y = _resting_position_from_window_rect(
                left,
                top,
                width,
                screen_rect(),
                idle_width=current_idle_width(),
                height=current_height(),
            )
            self._x = int(rest_x)
            self._y = int(rest_y)
            self._window_x = int(rest_x)
            self._window_y = int(rest_y)
            self._window_width = current_idle_width()
            self._window_height = current_height()
            self._window_scale = current_scale()
            return self._x, self._y

        def collapse_for_idle(next_state):
            if next_state != STATE_IDLE:
                return
            if state["pressed"]:
                user32.ReleaseCapture()
            state["hover"] = False
            state["pressed"] = False
            state["dragged"] = False
            state["cancel_hover"] = False
            state["flash_text"] = ""
            state["flash_until"] = 0.0

        def update_layered(x=None, y=None, keep_right=False, trace_reason=None):
            hwnd = state["hwnd"]
            if not hwnd:
                return

            if x is None or y is None:
                if state["window_width"]:
                    left, top, _, _ = get_window_rect()
                    x, y = left, top
                elif self._x is None or self._y is None:
                    sync_ui_scale()
                    x, y = default_position()
                else:
                    sync_ui_scale(self._x, self._y)
                    width = current_width()
                    x, y = anchored_position(width)
            sync_ui_scale(x, y)
            width = current_width()
            height = current_height()
            old_width = state["window_width"] or width
            if keep_right and old_width != width:
                x += old_width - width
            x, y = clamp_position(x, y, width)

            img = draw_widget()
            arr = np.asarray(img, dtype=np.uint8)
            alpha = arr[:, :, 3:4].astype(np.uint16)
            rgb = (arr[:, :, :3].astype(np.uint16) * alpha // 255).astype(np.uint8)
            bgra = np.dstack((rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0], arr[:, :, 3])).copy()
            data = bgra.tobytes()

            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            bits = ctypes.c_void_p()
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB
            hbitmap = gdi32.CreateDIBSection(hdc_screen, ctypes.pointer(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
            if not hbitmap or not bits.value:
                gdi32.DeleteDC(hdc_mem)
                user32.ReleaseDC(0, hdc_screen)
                return
            ctypes.memmove(bits.value, data, len(data))
            old_obj = gdi32.SelectObject(hdc_mem, hbitmap)
            pt_dst = POINT(x, y)
            size = SIZE(width, height)
            pt_src = POINT(0, 0)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            ok = user32.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt_dst), ctypes.byref(size), hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA)
            gdi32.SelectObject(hdc_mem, old_obj)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
            if trace_reason or not ok:
                trace_floating_state(
                    "floating.ui.update_layered",
                    ok=bool(ok),
                    error=int(kernel32.GetLastError()) if not ok else 0,
                    reason=trace_reason,
                    current=state["current"],
                    hover=state["hover"],
                    width=width,
                    height=height,
                    scale=current_scale(),
                    x=int(x),
                    y=int(y),
                    hwnd=int(hwnd or 0),
                )
            state["window_width"] = width
            state["window_height"] = height
            self._window_x = int(x)
            self._window_y = int(y)
            self._window_width = int(width)
            self._window_height = int(height)
            self._window_scale = current_scale()

        def show():
            state["visible"] = True
            update_layered()
            user32.ShowWindow(state["hwnd"], SW_SHOWNOACTIVATE)
            user32.SetWindowPos(state["hwnd"], HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

        def hide():
            state["visible"] = False
            user32.ShowWindow(state["hwnd"], SW_HIDE)

        def handle_click():
            if state["current"] == STATE_PROCESSING:
                state["flash_until"] = time.monotonic() + 1.2
                state["flash_text"] = t("处理中", self._language)
                update_layered(keep_right=True)
                return
            self._call_callback(self._on_toggle)

        def is_cancel_hit(x, y):
            width = current_width()
            height = current_height()
            return (
                state["current"] == STATE_RECORDING
                and width - _scaled_dim(36, current_scale()) <= x <= width - _scaled_dim(8, current_scale())
                and _scaled_dim(6, current_scale()) <= y <= height - _scaled_dim(6, current_scale())
            )

        def signed_word(value):
            value &= 0xFFFF
            return value - 0x10000 if value & 0x8000 else value

        def client_xy(lparam):
            value = int(lparam)
            return signed_word(value), signed_word(value >> 16)

        def cursor_pos():
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y

        def track_leave(hwnd):
            event = TRACKMOUSEEVENT()
            event.cbSize = ctypes.sizeof(TRACKMOUSEEVENT)
            event.dwFlags = TME_LEAVE
            event.hwndTrack = hwnd
            event.dwHoverTime = 0
            user32.TrackMouseEvent(ctypes.byref(event))

        def process_queue():
            try:
                while True:
                    cmd, payload = self._cmd_queue.get_nowait()
                    if cmd == _CMD_SHOW:
                        show()
                    elif cmd == _CMD_HIDE:
                        hide()
                    elif cmd == _CMD_STATE:
                        seq = int(payload.get("seq", 0) or 0)
                        if seq and seq < state["seq"]:
                            trace_floating_state(
                                "floating.ui.drop_stale_state",
                                payload_state=payload.get("state"),
                                payload_seq=seq,
                                current=state["current"],
                                seq=state["seq"],
                            )
                            continue
                        old = state["current"]
                        next_state = payload.get("state", STATE_IDLE)
                        collapse_for_idle(next_state)
                        state["seq"] = max(state["seq"], seq)
                        state["current"] = next_state
                        if state["current"] == STATE_RECORDING and self._recording_started_at is None:
                            self._recording_started_at = time.monotonic()
                        elif state["current"] != STATE_RECORDING:
                            self._recording_started_at = None
                            state["level"] = 0.0
                            state["level_target"] = 0.0
                            state["bars"] = [0.0] * 9
                        state["flash_text"] = payload.get("message") or ""
                        state["flash_until"] = time.monotonic() + 1.4 if state["flash_text"] else 0.0
                        trace_floating_state(
                            "floating.ui.apply_state",
                            old=old,
                            current=state["current"],
                            seq=state["seq"],
                            payload_seq=seq,
                            visible=state["visible"],
                            hwnd=int(state["hwnd"] or 0),
                        )
                        update_layered(keep_right=True, trace_reason="state")
                    elif cmd == _CMD_LEVEL:
                        state["level_target"] = max(0.0, min(1.0, payload.get("level", 0.0)))
                        state["last_level_at"] = time.monotonic()
                    elif cmd == _CMD_CONFIG:
                        self._x = payload.get("x")
                        self._y = payload.get("y")
                        self._theme = _normalize_theme(payload.get("theme"))
                        self._language = normalize_ui_language(payload.get("language"))
                        sync_ui_scale(self._x, self._y)
                        x, y = anchored_position(current_width())
                        update_layered(x, y, trace_reason="config")
                        if state["visible"]:
                            show()
                    elif cmd == _CMD_RESET_IDLE:
                        seq = int(payload.get("seq", 0) or 0)
                        if seq and seq < self._state_seq and self._state != STATE_IDLE:
                            trace_floating_state(
                                "floating.ui.skip_idle_reset",
                                payload_seq=seq,
                                object_seq=self._state_seq,
                                object_state=self._state,
                            )
                            continue
                        collapse_for_idle(STATE_IDLE)
                        state["seq"] = max(state["seq"], seq)
                        state["current"] = STATE_IDLE
                        trace_floating_state(
                            "floating.ui.reset_idle",
                            seq=state["seq"],
                            hwnd=int(state["hwnd"] or 0),
                            width=state["window_width"],
                        )
                        remember_resting_position()
                        hide()
                        destroyed = bool(user32.DestroyWindow(state["hwnd"]))
                        trace_floating_state(
                            "floating.ui.reset_idle.destroy",
                            destroyed=destroyed,
                            error=int(kernel32.GetLastError()) if not destroyed else 0,
                            hwnd=int(state["hwnd"] or 0),
                        )
                        state["running"] = False
                        user32.PostQuitMessage(0)
                        return
                    elif cmd == _CMD_STOP:
                        user32.DestroyWindow(state["hwnd"])
                        return
            except queue.Empty:
                pass
            except Exception as e:
                log.warning("悬浮按钮处理状态队列失败: %s", e)

        def sync_latest_state():
            if state["seq"] >= self._state_seq and state["current"] == self._state:
                return
            old = state["current"]
            collapse_for_idle(self._state)
            state["seq"] = self._state_seq
            state["current"] = self._state
            if state["current"] == STATE_RECORDING and self._recording_started_at is None:
                self._recording_started_at = time.monotonic()
            elif state["current"] != STATE_RECORDING:
                self._recording_started_at = None
                state["level"] = 0.0
                state["level_target"] = 0.0
                state["bars"] = [0.0] * 9
            state["flash_text"] = self._message or ""
            state["flash_until"] = time.monotonic() + 1.4 if self._message else 0.0
            trace_floating_state(
                "floating.ui.sync_latest",
                old=old,
                current=state["current"],
                seq=state["seq"],
                object_state=self._state,
                object_seq=self._state_seq,
            )

        def tick():
            try:
                sync_latest_state()
                state["phase"] += 0.24
                now = time.monotonic()
                if now - state["last_level_at"] > 0.35:
                    state["level_target"] *= 0.78
                if state["current"] == STATE_RECORDING:
                    state["level"] = state["level"] * 0.72 + state["level_target"] * 0.28
                    for i, old in enumerate(state["bars"]):
                        wave = (math.sin(state["phase"] * 1.7 + i * 0.72) + 1) / 2
                        base = max(0.08, state["level"])
                        target = min(1.0, base * (0.58 + wave * 0.65) + 0.04)
                        state["bars"][i] = old * 0.55 + target * 0.45
                else:
                    state["level"] *= 0.76
                    state["bars"] = [value * 0.76 for value in state["bars"]]
                if state["visible"]:
                    update_layered(keep_right=True)
                if now - state["last_trace_tick"] > 1.0:
                    state["last_trace_tick"] = now
                    trace_floating_state(
                        "floating.ui.tick",
                        current=state["current"],
                        seq=state["seq"],
                        visible=state["visible"],
                        width=state["window_width"],
                        height=state["window_height"],
                        scale=current_scale(),
                        hwnd=int(state["hwnd"] or 0),
                    )
            except Exception as e:
                log.warning("悬浮按钮刷新失败: %s", e)

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_NCHITTEST:
                return HTCLIENT
            if msg == WM_SETCURSOR:
                user32.SetCursor(user32.LoadCursorW(None, IDC_HAND))
                return 1
            if msg == WM_MOUSEMOVE:
                x, y = client_xy(lparam)
                if not state["hover"]:
                    state["hover"] = True
                    track_leave(hwnd)
                    update_layered(keep_right=True)
                if state["pressed"]:
                    sx, sy = cursor_pos()
                    dx = sx - state["press_x"]
                    dy = sy - state["press_y"]
                    if abs(dx) + abs(dy) > 3:
                        state["dragged"] = True
                    proposed_x = state["win_x"] + dx
                    proposed_y = state["win_y"] + dy
                    sync_ui_scale(proposed_x, proposed_y)
                    width = current_width()
                    nx, ny = clamp_position(proposed_x, proposed_y, width)
                    update_layered(nx, ny)
                cancel_hover = is_cancel_hit(x, y)
                if cancel_hover != state["cancel_hover"]:
                    state["cancel_hover"] = cancel_hover
                    update_layered()
                return 0
            if msg == WM_MOUSELEAVE:
                if not state["pressed"]:
                    state["hover"] = False
                    state["cancel_hover"] = False
                    update_layered(keep_right=True)
                return 0
            if msg == WM_LBUTTONDOWN:
                sx, sy = cursor_pos()
                left, top, _, _ = get_window_rect()
                x, y = client_xy(lparam)
                state["pressed"] = True
                state["dragged"] = False
                state["press_x"] = sx
                state["press_y"] = sy
                state["win_x"] = left
                state["win_y"] = top
                state["cancel_hover"] = is_cancel_hit(x, y)
                user32.SetCapture(hwnd)
                update_layered()
                return 0
            if msg == WM_LBUTTONUP:
                x, y = client_xy(lparam)
                state["pressed"] = False
                user32.ReleaseCapture()
                if state["dragged"]:
                    left, top, _, _ = get_window_rect()
                    self._x, self._y = remember_resting_position(left, top, current_width())
                    self._call_callback(self._on_position, self._x, self._y)
                    update_layered()
                    return 0
                if is_cancel_hit(x, y):
                    self._call_callback(self._on_cancel)
                    update_layered()
                    return 0
                handle_click()
                update_layered()
                return 0
            if msg == WM_RBUTTONUP:
                if state["current"] == STATE_RECORDING:
                    self._call_callback(self._on_cancel)
                else:
                    self._call_callback(self._on_settings)
                return 0
            if msg == _WM_WAKE:
                trace_floating_state("floating.ui.wake_message", current=state["current"], seq=state["seq"])
                process_queue()
                tick()
                return 0
            if msg == WM_TIMER:
                process_queue()
                tick()
                return 0
            if msg == WM_DESTROY:
                state["running"] = False
                user32.KillTimer(hwnd, 1)
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wndproc_ref = WNDPROC(wndproc)
        hinstance = kernel32.GetModuleHandleW(None)
        class_name = f"VoxFloatingControl_{id(self)}_{threading.get_ident()}_{int(time.monotonic() * 1000)}"
        wc = WNDCLASS()
        wc.lpfnWndProc = ctypes.cast(wndproc_ref, ctypes.c_void_p).value
        wc.hInstance = hinstance
        wc.hCursor = user32.LoadCursorW(None, IDC_HAND)
        wc.lpszClassName = class_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError()

        sync_ui_scale(self._x, self._y)
        x0, y0 = anchored_position(current_width())
        w0 = current_width()
        h0 = current_height()
        hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            class_name,
            "Vox Floating Control",
            WS_POPUP,
            x0,
            y0,
            w0,
            h0,
            None,
            None,
            hinstance,
            None,
        )
        if not hwnd:
            raise ctypes.WinError()

        state["hwnd"] = hwnd
        self._native_hwnd = int(hwnd)
        state["wndproc_ref"] = wndproc_ref
        trace_floating_state("floating.ui.created", hwnd=int(hwnd), class_name=class_name)
        user32.SetTimer(hwnd, 1, 80, None)
        update_layered(x0, y0)
        process_queue()

        try:
            msg = MSG()
            while state["running"] and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            trace_floating_state(
                "floating.ui.finally",
                hwnd=int(state["hwnd"] or 0),
                current=state["current"],
                seq=state["seq"],
            )
            self._started = False
            self._native_hwnd = None
            try:
                if state.get("hwnd"):
                    user32.DestroyWindow(state["hwnd"])
            except Exception:
                pass

    def _run_tk(self):
        try:
            import tkinter as tk
            from PIL import ImageTk
        except ImportError:
            log.warning("tkinter/Pillow 不可用，悬浮按钮已禁用")
            return

        root = None
        guard_acquired = False
        try:
            acquire_tk_root("floating_control")
            guard_acquired = True
            root = tk.Tk()
            root.withdraw()
            root.title("Vox Floating Control")
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            try:
                root.attributes("-transparentcolor", _TRANSPARENT)
                root.attributes("-alpha", 0.98)
            except Exception:
                pass
            root.configure(bg=_TRANSPARENT)
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
                "pressed": False,
                "cancel_hover": False,
                "phase": 0.0,
                "level": 0.0,
                "level_target": 0.0,
                "last_level_at": 0.0,
                "bars": [0.12] * 9,
                "photo": None,
                "window_width": 0,
                "window_height": _HEIGHT,
                "ui_scale": 1.0,
                "seq": 0,
            }

            canvas = tk.Canvas(
                root,
                width=_ACTIVE_WIDTH,
                height=_HEIGHT,
                bg=_TRANSPARENT,
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            )
            canvas.pack(fill="both", expand=True)
            image_id = canvas.create_image(0, 0, anchor="nw")

            def current_scale():
                return _normalize_ui_scale(state.get("ui_scale", 1.0))

            def current_height():
                return _control_height_scaled(current_scale())

            def current_width():
                return _control_width_scaled(
                    state["current"],
                    hover=state["hover"],
                    flash_visible=bool(state["flash_text"]) and time.monotonic() < state["flash_until"],
                    ui_scale=current_scale(),
                )

            def current_idle_width():
                return _scaled_dim(_IDLE_WIDTH, current_scale())

            def sync_ui_scale(x=None, y=None):
                if x is None or y is None:
                    if self._x is not None and self._y is not None:
                        x, y = self._x, self._y
                state["ui_scale"] = _ui_scale_for_point(x, y)
                return state["ui_scale"]

            def draw_widget():
                return _render_control_image(
                    theme=self._theme,
                    language=self._language,
                    current=state["current"],
                    hover=state["hover"],
                    pressed=state["pressed"],
                    cancel_hover=state["cancel_hover"],
                    flash_text=state["flash_text"],
                    flash_until=state["flash_until"],
                    phase=state["phase"],
                    bars=state["bars"],
                    recording_started_at=self._recording_started_at,
                    ui_scale=current_scale(),
                )

            def render_state():
                image = draw_widget()
                state["photo"] = ImageTk.PhotoImage(image, master=root)
                canvas.itemconfigure(image_id, image=state["photo"])

            def tk_screen_rect():
                try:
                    left = int(root.winfo_vrootx())
                    top = int(root.winfo_vrooty())
                    width = int(root.winfo_vrootwidth())
                    height = int(root.winfo_vrootheight())
                    if width > 0 and height > 0:
                        return (left, top, left + width, top + height)
                except Exception:
                    pass
                return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())

            def default_position():
                width = current_width()
                return _default_position_for_rect(tk_screen_rect(), width, height=current_height())

            def anchored_position(width=None):
                width = current_width() if width is None else width
                return _window_position_from_resting_rect(
                    self._x,
                    self._y,
                    width,
                    tk_screen_rect(),
                    idle_width=current_idle_width(),
                    height=current_height(),
                )

            def clamp_position(x, y, width=None):
                width = current_width() if width is None else width
                return _clamp_position_for_rect(x, y, width, tk_screen_rect(), height=current_height())

            def remember_resting_position(left=None, top=None, width=None):
                if left is None or top is None:
                    left = root.winfo_x()
                    top = root.winfo_y()
                width = state["window_width"] or current_width() if width is None else width
                rest_x, rest_y = _resting_position_from_window_rect(
                    left,
                    top,
                    width,
                    tk_screen_rect(),
                    idle_width=current_idle_width(),
                    height=current_height(),
                )
                self._x = int(rest_x)
                self._y = int(rest_y)
                self._window_x = int(rest_x)
                self._window_y = int(rest_y)
                self._window_width = current_idle_width()
                self._window_height = current_height()
                self._window_scale = current_scale()
                return self._x, self._y

            def set_geometry(x=None, y=None):
                if x is None or y is None:
                    sync_ui_scale()
                    width = current_width()
                    x0, y0 = anchored_position(width)
                else:
                    sync_ui_scale(x, y)
                    width = current_width()
                    x0, y0 = clamp_position(x, y, width=width)
                height = current_height()
                canvas.configure(width=width, height=height)
                root.geometry(f"{width}x{height}+{x0}+{y0}")
                state["window_width"] = width
                state["window_height"] = height
                self._window_x = int(x0)
                self._window_y = int(y0)
                self._window_width = int(width)
                self._window_height = int(height)
                self._window_scale = current_scale()

            def resize_for_state(keep_right=False):
                sync_ui_scale(root.winfo_x(), root.winfo_y())
                width = current_width()
                height = current_height()
                old_width = state["window_width"] or width
                old_height = state["window_height"] or height
                if old_width == width and old_height == height:
                    canvas.configure(width=width, height=height)
                    self._window_x = int(root.winfo_x())
                    self._window_y = int(root.winfo_y())
                    self._window_width = int(width)
                    self._window_height = int(height)
                    self._window_scale = current_scale()
                    return
                x = root.winfo_x()
                y = root.winfo_y()
                if keep_right:
                    x += old_width - width
                x, y = clamp_position(x, y, width=width)
                canvas.configure(width=width, height=height)
                root.geometry(f"{width}x{height}+{x}+{y}")
                state["window_width"] = width
                state["window_height"] = height
                self._window_x = int(x)
                self._window_y = int(y)
                self._window_width = int(width)
                self._window_height = int(height)
                self._window_scale = current_scale()

            def show():
                state["visible"] = True
                set_geometry()
                root.deiconify()
                root.lift()

            def hide():
                state["visible"] = False
                root.withdraw()

            def collapse_for_idle(next_state):
                if next_state != STATE_IDLE:
                    return
                state["hover"] = False
                state["pressed"] = False
                state["dragged"] = False
                state["cancel_hover"] = False
                state["flash_text"] = ""
                state["flash_until"] = 0.0

            def handle_click():
                if state["current"] == STATE_PROCESSING:
                    state["flash_until"] = time.monotonic() + 1.2
                    state["flash_text"] = t("处理中", self._language)
                    render_state()
                    return
                self._call_callback(self._on_toggle)

            def is_cancel_hit(x, y):
                width = current_width()
                height = current_height()
                return (
                    state["current"] == STATE_RECORDING
                    and width - _scaled_dim(36, current_scale()) <= x <= width - _scaled_dim(8, current_scale())
                    and _scaled_dim(6, current_scale()) <= y <= height - _scaled_dim(6, current_scale())
                )

            def on_press(event):
                state["dragged"] = False
                state["pressed"] = True
                state["cancel_hover"] = is_cancel_hit(event.x, event.y)
                state["press_x"] = event.x_root
                state["press_y"] = event.y_root
                state["win_x"] = root.winfo_x()
                state["win_y"] = root.winfo_y()
                render_state()

            def on_motion(event):
                dx = event.x_root - state["press_x"]
                dy = event.y_root - state["press_y"]
                if abs(dx) + abs(dy) > 3:
                    state["dragged"] = True
                proposed_x = state["win_x"] + dx
                proposed_y = state["win_y"] + dy
                sync_ui_scale(proposed_x, proposed_y)
                width = current_width()
                height = current_height()
                x, y = clamp_position(proposed_x, proposed_y, width=width)
                root.geometry(f"{width}x{height}+{x}+{y}")
                self._window_x = int(x)
                self._window_y = int(y)
                self._window_width = int(width)
                self._window_height = int(height)
                self._window_scale = current_scale()
                cancel_hover = is_cancel_hit(event.x, event.y)
                if cancel_hover != state["cancel_hover"]:
                    state["cancel_hover"] = cancel_hover
                    render_state()

            def on_pointer_motion(event):
                cancel_hover = is_cancel_hit(event.x, event.y)
                if cancel_hover != state["cancel_hover"]:
                    state["cancel_hover"] = cancel_hover
                    render_state()

            def on_release(event):
                state["pressed"] = False
                if state["dragged"]:
                    self._x, self._y = remember_resting_position(root.winfo_x(), root.winfo_y(), current_width())
                    self._call_callback(self._on_position, self._x, self._y)
                    render_state()
                    return
                if is_cancel_hit(event.x, event.y):
                    self._call_callback(self._on_cancel)
                    render_state()
                    return
                handle_click()
                render_state()

            def on_enter(_event):
                state["hover"] = True
                resize_for_state(keep_right=True)
                render_state()

            def on_leave(_event):
                if not state["pressed"]:
                    state["hover"] = False
                    state["cancel_hover"] = False
                    resize_for_state(keep_right=True)
                    render_state()

            def on_right_click(_event):
                if state["current"] == STATE_RECORDING:
                    self._call_callback(self._on_cancel)
                else:
                    self._call_callback(self._on_settings)

            canvas.bind("<ButtonPress-1>", on_press, add="+")
            canvas.bind("<B1-Motion>", on_motion, add="+")
            canvas.bind("<ButtonRelease-1>", on_release, add="+")
            canvas.bind("<Motion>", on_pointer_motion, add="+")
            canvas.bind("<Enter>", on_enter, add="+")
            canvas.bind("<Leave>", on_leave, add="+")
            canvas.bind("<Button-3>", on_right_click, add="+")

            set_geometry()
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
                            seq = int(payload.get("seq", 0) or 0)
                            if seq and seq < state["seq"]:
                                continue
                            next_state = payload.get("state", STATE_IDLE)
                            collapse_for_idle(next_state)
                            state["seq"] = max(state["seq"], seq)
                            state["current"] = next_state
                            if state["current"] == STATE_RECORDING and self._recording_started_at is None:
                                self._recording_started_at = time.monotonic()
                            elif state["current"] != STATE_RECORDING:
                                self._recording_started_at = None
                                state["level"] = 0.0
                                state["level_target"] = 0.0
                                state["bars"] = [0.0] * 9
                            state["flash_text"] = payload.get("message") or ""
                            state["flash_until"] = time.monotonic() + 1.4 if state["flash_text"] else 0.0
                            resize_for_state(keep_right=True)
                            render_state()
                        elif cmd == _CMD_LEVEL:
                            state["level_target"] = max(0.0, min(1.0, payload.get("level", 0.0)))
                            state["last_level_at"] = time.monotonic()
                        elif cmd == _CMD_CONFIG:
                            self._x = payload.get("x")
                            self._y = payload.get("y")
                            self._theme = _normalize_theme(payload.get("theme"))
                            self._language = normalize_ui_language(payload.get("language"))
                            set_geometry()
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

            def sync_latest_state():
                if state["seq"] >= self._state_seq and state["current"] == self._state:
                    return
                state["seq"] = self._state_seq
                state["current"] = self._state
                if state["current"] == STATE_RECORDING and self._recording_started_at is None:
                    self._recording_started_at = time.monotonic()
                elif state["current"] != STATE_RECORDING:
                    self._recording_started_at = None
                    state["level"] = 0.0
                    state["level_target"] = 0.0
                    state["bars"] = [0.0] * 9
                state["flash_text"] = self._message or ""
                state["flash_until"] = time.monotonic() + 1.4 if self._message else 0.0

            def tick():
                if root.winfo_exists():
                    sync_latest_state()
                    state["phase"] += 0.24
                    now = time.monotonic()
                    if now - state["last_level_at"] > 0.35:
                        state["level_target"] *= 0.78

                    if state["current"] == STATE_RECORDING:
                        state["level"] = state["level"] * 0.72 + state["level_target"] * 0.28
                        for i, old in enumerate(state["bars"]):
                            wave = (math.sin(state["phase"] * 1.7 + i * 0.72) + 1) / 2
                            base = max(0.08, state["level"])
                            target = min(1.0, base * (0.58 + wave * 0.65) + 0.04)
                            state["bars"][i] = old * 0.55 + target * 0.45
                    else:
                        state["level"] *= 0.76
                        state["bars"] = [value * 0.76 for value in state["bars"]]

                    if state["visible"]:
                        if current_width() != state["window_width"] or current_height() != state["window_height"]:
                            resize_for_state(keep_right=True)
                        render_state()
                    root.after(80, tick)

            root.after(80, poll_queue)
            root.after(80, tick)
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
            if guard_acquired:
                release_tk_root("floating_control")

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
