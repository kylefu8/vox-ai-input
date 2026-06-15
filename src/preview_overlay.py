"""
结果预览胶囊模块。

在屏幕上显示一枚和悬浮录音按钮同一视觉体系的结果预览胶囊，用来展示
流式转写中间文本、转写/润色状态、最终结果和降级提示。

设计要点：
- Windows 优先使用原生 layered window + per-pixel alpha，避免圆角毛边。
- Tk 仅作为非 Windows 或原生窗口失败时的 fallback。
- 外部通过 queue 通信（参考 countdown.py 的成熟模式）。
- 位置优先锚定在悬浮录音胶囊下方；没有锚点时回退到底部居中。
- 10 秒无更新自动 dismiss，防止异常导致永驻。
"""

import math
import platform
import queue
import threading
import time

from src.display import display_scale_for_point
from src.floating_control import (
    _ICON_RING_RADIUS,
    _ICON_RING_WIDTH,
    _PALETTES,
    _TRANSPARENT,
    _draw_mic,
    _draw_ring,
    _load_render_font,
    _normalize_theme,
    _normalize_ui_scale,
    _rgba,
    _ring_box,
    _sc,
    _scaled_dim,
    _scaled_pixel,
)
from src.logger import setup_logger
from src.tk_runtime import acquire_tk_root, release_tk_root

log = setup_logger(__name__)

# ==================== 命令常量 ====================
_CMD_SHOW = "show"
_CMD_UPDATE = "update"
_CMD_DISMISS = "dismiss"
_CMD_CONFIG = "config"

# ==================== 胶囊样式 ====================
_RENDER_SCALE = 4
_MIN_WIDTH = 236
_MAX_WIDTH = 520
_MAX_TEXT_LINES = 3
_HEIGHT_STATUS_ONLY = 42
_PADDING_X = 16
_BODY_LINE_HEIGHT = 18
_BODY_TOP = 42
_BODY_BOTTOM_PADDING = 10
_AUTO_DISMISS_SEC = 10
_ANCHOR_GAP = 8
_BOTTOM_MARGIN = 88
_SCREEN_MARGIN = 10

def _get_virtual_screen_bounds():
    """
    获取虚拟屏幕边界（多显示器下覆盖所有屏幕的总范围）。

    Returns:
        tuple[int, int, int, int]: (left, top, right, bottom) 像素坐标
    """
    if platform.system() == "Windows":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            vs_x = user32.GetSystemMetrics(76)
            vs_y = user32.GetSystemMetrics(77)
            vs_w = user32.GetSystemMetrics(78)
            vs_h = user32.GetSystemMetrics(79)
            if vs_w > 0 and vs_h > 0:
                return (vs_x, vs_y, vs_x + vs_w, vs_y + vs_h)
        except Exception:
            pass

    return (0, 0, 1920, 1080)


def _normalize_anchor(anchor):
    """把外部锚点标准化为 (x, y, width, height)。"""
    if not anchor:
        return None
    try:
        if isinstance(anchor, dict):
            values = (
                anchor.get("x"),
                anchor.get("y"),
                anchor.get("width"),
                anchor.get("height"),
            )
        else:
            values = tuple(anchor)
        if len(values) != 4:
            return None
        x, y, width, height = (int(round(float(value))) for value in values)
        if width <= 0 or height <= 0:
            return None
        return (x, y, width, height)
    except Exception:
        return None


def _ui_scale_for_anchor(anchor):
    anchor = _normalize_anchor(anchor)
    if anchor:
        x, y, width, height = anchor
        return _normalize_ui_scale(display_scale_for_point(x + width / 2, y + height / 2))
    return _normalize_ui_scale(display_scale_for_point())


def _position_preview(size, anchor=None, bounds=None):
    """
    计算预览胶囊位置。

    优先贴在主悬浮胶囊下方，空间不足则放上方；没有锚点时放到底部居中。
    """
    width, height = size
    vs_left, vs_top, vs_right, vs_bottom = bounds or _get_virtual_screen_bounds()
    anchor = _normalize_anchor(anchor)

    if anchor:
        ax, ay, aw, ah = anchor
        x = ax + aw / 2 - width / 2
        y = ay + ah + _ANCHOR_GAP
        if y + height > vs_bottom - _SCREEN_MARGIN:
            y = ay - height - _ANCHOR_GAP
    else:
        x = vs_left + (vs_right - vs_left - width) / 2
        y = vs_bottom - height - _BOTTOM_MARGIN

    x = min(max(vs_left + _SCREEN_MARGIN, int(round(x))), vs_right - width - _SCREEN_MARGIN)
    y = min(max(vs_top + _SCREEN_MARGIN, int(round(y))), vs_bottom - height - _SCREEN_MARGIN)
    return x, y


def _text_width(draw, text, font):
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


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


def _draw_body_text(draw, x, y, text, font, fill, scale):
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (_sc(x, scale) - bbox[0], _sc(y, scale) - bbox[1]),
        text,
        font=font,
        fill=fill,
    )


def _ellipsize(draw, text, font, max_width):
    text = str(text or "")
    if _text_width(draw, text, font) <= max_width:
        return text
    suffix = "..."
    for length in range(max(0, len(text) - 1), 0, -1):
        candidate = text[:length].rstrip() + suffix
        if _text_width(draw, candidate, font) <= max_width:
            return candidate
    return suffix


def _wrap_text(draw, text, font, max_width, max_lines=_MAX_TEXT_LINES):
    """按实际像素宽度折行，兼容中文无空格文本。"""
    text = str(text or "").strip()
    if not text:
        return []

    lines = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        line = ""
        for index, char in enumerate(paragraph):
            candidate = line + char
            if not line or _text_width(draw, candidate, font) <= max_width:
                line = candidate
                continue
            lines.append(line.rstrip())
            if len(lines) >= max_lines:
                lines[-1] = _ellipsize(draw, lines[-1] + paragraph[index:], font, max_width)
                return lines
            line = char
        if line:
            lines.append(line.rstrip())
            if len(lines) >= max_lines:
                if paragraph != line:
                    lines[-1] = _ellipsize(draw, lines[-1] + "...", font, max_width)
                return lines
    return lines[:max_lines]


def _clean_status(status):
    status = str(status or "").strip()
    for prefix in ("🎤", "📡", "🤖", "✅", "⚠️", "⚠", "🚫"):
        status = status.replace(prefix, "").strip()
    return status


def _status_kind(status):
    raw = str(status or "")
    if any(token in raw for token in ("失败", "错误", "未就绪", "⚠")):
        return "warning"
    if "录音" in raw:
        return "recording"
    if any(token in raw for token in ("转写", "润色", "处理", "中...")):
        return "processing"
    if any(token in raw for token in ("完成", "✅")):
        return "done"
    return "idle"


def _draw_check(draw, cx, cy, color, scale):
    width = max(1, _sc(2.2, scale))
    draw.line(
        (
            _sc(cx - 5.0, scale),
            _sc(cy + 0.4, scale),
            _sc(cx - 1.4, scale),
            _sc(cy + 4.1, scale),
            _sc(cx + 5.8, scale),
            _sc(cy - 5.2, scale),
        ),
        fill=color,
        width=width,
        joint="curve",
    )


def _draw_warning_mark(draw, cx, cy, color, scale):
    width = max(1, _sc(2.0, scale))
    draw.line(
        (_sc(cx, scale), _sc(cy - 5.5, scale), _sc(cx, scale), _sc(cy + 1.6, scale)),
        fill=color,
        width=width,
    )
    dot = _sc(1.4, scale)
    draw.ellipse(
        (_sc(cx, scale) - dot, _sc(cy + 5.0, scale) - dot, _sc(cx, scale) + dot, _sc(cy + 5.0, scale) + dot),
        fill=color,
    )


def _draw_status_icon(draw, cx, cy, kind, palette, scale, phase=0.0):
    if kind == "recording":
        draw.ellipse(_ring_box(cx, cy, scale), fill=_rgba(palette["recording"], 72))
        _draw_ring(draw, cx, cy, palette["recording"], 255, scale)
        _draw_mic(draw, cx, cy, _rgba("#FFFFFF", 255), scale, strong=True)
        return

    if kind == "processing":
        start = int((phase * 120) % 360)
        ring_box = _ring_box(cx, cy, scale)
        draw.ellipse(
            ring_box,
            outline=_rgba(palette["processing"], 52),
            width=max(1, _sc(_ICON_RING_WIDTH, scale)),
        )
        draw.arc(
            ring_box,
            start=start,
            end=start + 248,
            fill=_rgba(palette["processing"], 232),
            width=max(1, _sc(_ICON_RING_WIDTH, scale)),
        )
        return

    if kind == "done":
        draw.ellipse(_ring_box(cx, cy, scale), fill=_rgba(palette["success"], 42))
        _draw_ring(draw, cx, cy, palette["success"], 230, scale)
        _draw_check(draw, cx, cy, _rgba(palette["icon"], 252), scale)
        return

    if kind == "warning":
        draw.ellipse(_ring_box(cx, cy, scale), fill=_rgba(palette["warning"], 62))
        _draw_ring(draw, cx, cy, palette["warning"], 244, scale)
        _draw_warning_mark(draw, cx, cy, _rgba(palette["icon"], 255), scale)
        return

    draw.ellipse(_ring_box(cx, cy, scale), fill=_rgba(palette["icon_bg"], 156))
    _draw_ring(draw, cx, cy, palette["idle"], 174, scale)
    _draw_mic(draw, cx, cy, _rgba(palette["icon"], 244), scale)


def _render_preview_image(*, text="", status="", theme="dark", phase=0.0, ui_scale=1.0):
    """离屏渲染结果预览胶囊。"""
    from PIL import Image, ImageDraw

    ui_scale = _normalize_ui_scale(ui_scale)
    scale = _RENDER_SCALE * ui_scale
    palette = _PALETTES[_normalize_theme(theme)]
    status_text = _clean_status(status)
    body_text = str(text or "").strip()
    kind = _status_kind(status)

    scratch = Image.new("RGBA", (_scaled_pixel(_MAX_WIDTH, scale), _scaled_pixel(160, scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch, "RGBA")
    status_font = _load_render_font(10.5, scale, bold=True)
    body_font = _load_render_font(10.5, scale)

    max_text_width = _sc(_MAX_WIDTH - _PADDING_X * 2, scale)
    body_lines = _wrap_text(draw, body_text, body_font, max_text_width)

    status_width = _text_width(draw, status_text, status_font)
    body_width = max((_text_width(draw, line, body_font) for line in body_lines), default=0)
    content_width = max(status_width + _sc(36, scale), body_width)

    if body_lines:
        width = max(_MIN_WIDTH, min(_MAX_WIDTH, math.ceil(content_width / scale) + _PADDING_X * 2))
        height = _BODY_TOP + len(body_lines) * _BODY_LINE_HEIGHT + _BODY_BOTTOM_PADDING
    else:
        width = max(220, min(_MAX_WIDTH, math.ceil(content_width / scale) + _PADDING_X * 2))
        height = _HEIGHT_STATUS_ONLY

    out_width = _scaled_dim(width, ui_scale)
    out_height = _scaled_dim(height, ui_scale)
    img = Image.new("RGBA", (_scaled_pixel(width, scale), _scaled_pixel(height, scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    radius = 19 if height <= _HEIGHT_STATUS_ONLY else 20

    shadow = (_sc(5, scale), _sc(7, scale), _sc(width - 2, scale), _sc(height - 1, scale))
    body = (_sc(2, scale), _sc(2, scale), _sc(width - 3, scale), _sc(height - 5, scale))
    draw.rounded_rectangle(shadow, radius=_sc(radius, scale), fill=_rgba(palette["shadow"], 34))
    draw.rounded_rectangle(body, radius=_sc(radius, scale), fill=_rgba(palette["bg"], 244))

    icon_cx = 22
    header_cy = _HEIGHT_STATUS_ONLY / 2
    _draw_status_icon(draw, icon_cx, header_cy, kind, palette, scale, phase=phase)

    label = status_text or "预览"
    available_status = _sc(width - 62, scale)
    label = _ellipsize(draw, label, status_font, available_status)
    _draw_left_center_text(draw, 48, header_cy, label, status_font, _rgba(palette["text"], 232), scale)

    if body_lines:
        y = _BODY_TOP
        for line in body_lines:
            _draw_body_text(draw, _PADDING_X, y, line, body_font, _rgba(palette["text"], 218), scale)
            y += _BODY_LINE_HEIGHT

    return img.resize((out_width, out_height), Image.Resampling.LANCZOS)


class PreviewOverlay:
    """
    结果预览胶囊。

    外部接口：
    - show(text, status): 显示胶囊
    - update_text(text, status): 更新内容
    - dismiss(): 隐藏胶囊
    """

    def __init__(self, theme="dark", anchor_provider=None):
        self._theme = _normalize_theme(theme)
        self._anchor_provider = anchor_provider
        self._cmd_queue = queue.Queue()
        self._thread = None
        self._started = False
        self._lock = threading.Lock()

    def configure(self, theme=None, anchor_provider=None):
        """更新视觉配置。"""
        if theme is not None:
            self._theme = _normalize_theme(theme)
        if anchor_provider is not None:
            self._anchor_provider = anchor_provider
        if self._started:
            self._cmd_queue.put((_CMD_CONFIG, {"anchor": self._get_anchor_rect()}))

    def _ensure_thread(self):
        """懒启动后台线程（首次 show 时才创建）。"""
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _get_anchor_rect(self):
        if not self._anchor_provider:
            return None
        try:
            return _normalize_anchor(self._anchor_provider())
        except Exception as e:
            log.debug("获取预览胶囊锚点失败: %s", e)
            return None

    def show(self, text="", status=""):
        """显示胶囊。"""
        self._ensure_thread()
        self._cmd_queue.put((
            _CMD_SHOW,
            {"text": text, "status": status, "anchor": self._get_anchor_rect()},
        ))

    def update_text(self, text, status=""):
        """更新胶囊内容。"""
        if self._started:
            self._cmd_queue.put((
                _CMD_UPDATE,
                {"text": text, "status": status, "anchor": self._get_anchor_rect()},
            ))

    def dismiss(self):
        """隐藏胶囊。"""
        if self._started:
            self._cmd_queue.put((_CMD_DISMISS, None))

    def _run(self):
        if platform.system() == "Windows":
            try:
                self._run_windows_layered()
                return
            except ImportError as e:
                log.debug("原生预览胶囊依赖不可用，回退 Tk: %s", e)
            except Exception as e:
                log.warning("原生预览胶囊运行失败，回退 Tk: %s", e)
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
        WM_TIMER = 0x0113
        ULW_ALPHA = 0x00000002
        AC_SRC_OVER = 0
        AC_SRC_ALPHA = 1
        BI_RGB = 0
        DIB_RGB_COLORS = 0
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
        user32.GetDC.restype = HANDLE
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.ReleaseDC.argtypes = [wintypes.HWND, HANDLE]
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
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.SetTimer.argtypes = [wintypes.HWND, UINT_PTR, wintypes.UINT, ctypes.c_void_p]
        user32.KillTimer.argtypes = [wintypes.HWND, UINT_PTR]
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
            "text": "",
            "status": "",
            "anchor": None,
            "last_update": time.monotonic(),
            "phase": 0.0,
            "hwnd": None,
            "running": True,
        }

        def render_image():
            return _render_preview_image(
                text=state["text"],
                status=state["status"],
                theme=self._theme,
                phase=state["phase"],
                ui_scale=_ui_scale_for_anchor(state["anchor"]),
            )

        def update_layered(image, x, y):
            hwnd = state["hwnd"]
            if not hwnd:
                return

            width, height = image.size
            arr = np.asarray(image, dtype=np.uint8)
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
            user32.UpdateLayeredWindow(
                hwnd,
                hdc_screen,
                ctypes.byref(pt_dst),
                ctypes.byref(size),
                hdc_mem,
                ctypes.byref(pt_src),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            )
            gdi32.SelectObject(hdc_mem, old_obj)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)

        def redraw():
            image = render_image()
            x, y = _position_preview(image.size, state["anchor"])
            update_layered(image, x, y)
            if state["visible"]:
                user32.ShowWindow(state["hwnd"], SW_SHOWNOACTIVATE)
                user32.SetWindowPos(
                    state["hwnd"],
                    HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )

        def show(payload):
            state["text"] = payload.get("text", "")
            state["status"] = payload.get("status", "")
            state["anchor"] = _normalize_anchor(payload.get("anchor"))
            state["last_update"] = time.monotonic()
            state["visible"] = True
            redraw()

        def update(payload):
            state["text"] = payload.get("text", "")
            state["status"] = payload.get("status", "")
            state["anchor"] = _normalize_anchor(payload.get("anchor")) or state["anchor"]
            state["last_update"] = time.monotonic()
            if state["visible"]:
                redraw()

        def hide():
            state["visible"] = False
            user32.ShowWindow(state["hwnd"], SW_HIDE)

        def should_animate():
            return _status_kind(state["status"]) == "processing"

        def process_queue():
            try:
                while True:
                    cmd, payload = self._cmd_queue.get_nowait()
                    if cmd == _CMD_SHOW:
                        show(payload or {})
                    elif cmd == _CMD_UPDATE:
                        update(payload or {})
                    elif cmd == _CMD_CONFIG:
                        state["anchor"] = _normalize_anchor((payload or {}).get("anchor")) or state["anchor"]
                        if state["visible"]:
                            redraw()
                    elif cmd == _CMD_DISMISS:
                        hide()
            except queue.Empty:
                pass

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_TIMER:
                process_queue()
                if state["visible"]:
                    if time.monotonic() - state["last_update"] >= _AUTO_DISMISS_SEC:
                        hide()
                    elif should_animate():
                        state["phase"] += 0.22
                        redraw()
                return 0
            if msg == WM_DESTROY:
                state["running"] = False
                user32.KillTimer(hwnd, 1)
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wndproc_ref = WNDPROC(wndproc)
        hinstance = kernel32.GetModuleHandleW(None)
        class_name = f"VoxPreviewOverlay_{id(self)}"
        wc = WNDCLASS()
        wc.lpfnWndProc = ctypes.cast(wndproc_ref, ctypes.c_void_p).value
        wc.hInstance = hinstance
        wc.lpszClassName = class_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError()

        hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            class_name,
            "Vox Preview Overlay",
            WS_POPUP,
            0,
            0,
            1,
            1,
            None,
            None,
            hinstance,
            None,
        )
        if not hwnd:
            raise ctypes.WinError()

        state["hwnd"] = hwnd
        state["wndproc_ref"] = wndproc_ref
        user32.SetTimer(hwnd, 1, 80, None)

        try:
            msg = MSG()
            while state["running"] and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._started = False
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
            log.warning("tkinter/Pillow 不可用，预览胶囊已禁用")
            return

        root = None
        guard_acquired = False
        try:
            acquire_tk_root("preview_overlay")
            guard_acquired = True
            root = tk.Tk()
            root.withdraw()
            root.title("Vox Preview Overlay")
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.configure(bg=_TRANSPARENT)
            root.resizable(False, False)
            try:
                root.attributes("-transparentcolor", _TRANSPARENT)
                root.attributes("-alpha", 0.98)
            except Exception:
                pass

            if platform.system() == "Windows":
                root.after(0, lambda: self._set_no_activate(root))

            state = {
                "visible": False,
                "text": "",
                "status": "",
                "anchor": None,
                "last_update": time.monotonic(),
                "phase": 0.0,
                "photo": None,
            }

            canvas = tk.Canvas(root, bg=_TRANSPARENT, bd=0, highlightthickness=0)
            canvas.pack(fill="both", expand=True)
            image_id = canvas.create_image(0, 0, anchor="nw")

            def render_and_place():
                image = _render_preview_image(
                    text=state["text"],
                    status=state["status"],
                    theme=self._theme,
                    phase=state["phase"],
                    ui_scale=_ui_scale_for_anchor(state["anchor"]),
                )
                width, height = image.size
                state["photo"] = ImageTk.PhotoImage(image, master=root)
                canvas.configure(width=width, height=height)
                canvas.itemconfigure(image_id, image=state["photo"])
                x, y = _position_preview((width, height), state["anchor"])
                root.geometry(f"{width}x{height}+{x}+{y}")

            def show(payload):
                state["text"] = payload.get("text", "")
                state["status"] = payload.get("status", "")
                state["anchor"] = _normalize_anchor(payload.get("anchor"))
                state["last_update"] = time.monotonic()
                state["visible"] = True
                render_and_place()
                root.deiconify()
                root.lift()

            def update(payload):
                state["text"] = payload.get("text", "")
                state["status"] = payload.get("status", "")
                state["anchor"] = _normalize_anchor(payload.get("anchor")) or state["anchor"]
                state["last_update"] = time.monotonic()
                if state["visible"]:
                    render_and_place()

            def hide():
                state["visible"] = False
                root.withdraw()

            def should_animate():
                return _status_kind(state["status"]) == "processing"

            def poll_queue():
                try:
                    while True:
                        cmd, payload = self._cmd_queue.get_nowait()
                        if cmd == _CMD_SHOW:
                            show(payload or {})
                        elif cmd == _CMD_UPDATE:
                            update(payload or {})
                        elif cmd == _CMD_CONFIG:
                            state["anchor"] = _normalize_anchor((payload or {}).get("anchor")) or state["anchor"]
                            if state["visible"]:
                                render_and_place()
                        elif cmd == _CMD_DISMISS:
                            hide()
                except queue.Empty:
                    pass

                if root.winfo_exists():
                    root.after(50, poll_queue)

            def tick():
                if root.winfo_exists():
                    if state["visible"]:
                        if time.monotonic() - state["last_update"] >= _AUTO_DISMISS_SEC:
                            hide()
                        elif should_animate():
                            state["phase"] += 0.22
                            render_and_place()
                    root.after(80, tick)

            root.after(50, poll_queue)
            root.after(80, tick)
            root.mainloop()

        except Exception as e:
            log.error("预览胶囊线程异常: %s", e)
        finally:
            self._started = False
            try:
                if root and root.winfo_exists():
                    root.destroy()
            except Exception:
                pass
            if guard_acquired:
                release_tk_root("preview_overlay")

    @staticmethod
    def _set_no_activate(root):
        """Windows 专用：设置窗口为 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW。"""
        import ctypes

        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_TOPMOST = 0x00000008
        GWL_EXSTYLE = -20

        user32 = ctypes.windll.user32
        root.update_idletasks()
        hwnd = int(root.wm_frame(), 16) if root.wm_frame() else None
        if not hwnd:
            hwnd = user32.FindWindowW(None, root.title())

        if hwnd:
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
