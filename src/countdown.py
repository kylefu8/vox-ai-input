"""
录音倒计时浮窗模块

在录音即将到达最大时长时，在屏幕右下角显示醒目的半透明倒计时数字（5、4、3、2、1）。

Windows 实现：
- 使用 Win32 Layered Window + UpdateLayeredWindow API
- 支持逐像素 Alpha 透明（真正的半透明，无边框伪影）
- Pillow 4x 超采样渲染文字，缩小后边缘丝滑
- 持久线程 + queue 通信

其他平台：回退到 tkinter 实现。
"""

import platform
import queue
import threading
from src.logger import setup_logger

log = setup_logger(__name__)

COUNTDOWN_SECONDS = 5

# 每秒的文字颜色 (RGB)
_COUNTDOWN_COLORS = {
    5: (243, 156, 18),   # 金黄
    4: (230, 126, 34),   # 橙
    3: (231, 76, 60),    # 红
    2: (192, 57, 43),    # 深红
    1: (146, 43, 33),    # 暗红
}

_TEXT_ALPHA = 190        # 文字透明度 (0-255)
_WIN_SIZE = 180          # 窗口/图片像素
_RENDER_SCALE = 4        # 超采样倍率

_CMD_SHOW = "show"
_CMD_DISMISS = "dismiss"


def _render_digits(win_size, scale):
    """
    预渲染 1-9 的数字 RGBA 图片，4x 超采样。

    Returns:
        dict[int, PIL.Image.Image]: {数字: RGBA 图片}
    """
    from PIL import Image, ImageDraw, ImageFont

    big = win_size * scale
    font_size = int(big * 0.78)

    font = None
    for name in ("segoeuib.ttf", "arialbd.ttf", "impact.ttf"):
        try:
            font = ImageFont.truetype(name, font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    results = {}
    for digit in range(1, 10):
        rgb = _COUNTDOWN_COLORS.get(digit, (146, 43, 33))
        fill = rgb + (_TEXT_ALPHA,)

        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        text = str(digit)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (big - tw) // 2 - bbox[0]
        y = (big - th) // 2 - bbox[1]
        draw.text((x, y), text, font=font, fill=fill)

        img = img.resize((win_size, win_size), Image.LANCZOS)
        results[digit] = img

    return results


class CountdownOverlay:
    """屏幕右下角半透明倒计时浮窗。"""

    def __init__(self):
        self._cmd_queue = queue.Queue()
        self._thread = None
        self._started = False

    def _ensure_thread(self):
        """懒启动后台线程（首次 show/dismiss 时才创建）。"""
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def show(self, seconds=COUNTDOWN_SECONDS):
        """开始显示倒计时。"""
        self._ensure_thread()
        self._cmd_queue.put((_CMD_SHOW, seconds))

    def dismiss(self):
        """立即关闭倒计时。"""
        if self._started:
            self._cmd_queue.put((_CMD_DISMISS, None))

    def _run(self):
        """根据平台选择实现。"""
        if platform.system() == "Windows":
            self._run_win32()
        else:
            self._run_tkinter()

    # ----------------------------------------------------------------
    #  Windows: Win32 Layered Window（逐像素 Alpha，无边框伪影）
    # ----------------------------------------------------------------
    def _run_win32(self):
        """用 Win32 API 创建 Layered Window 并处理消息循环。"""
        try:
            import ctypes
            from ctypes import wintypes, byref, sizeof
            from PIL import Image
        except ImportError:
            log.debug("ctypes 或 Pillow 不可用，回退到 tkinter")
            self._run_tkinter()
            return

        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            kernel32 = ctypes.windll.kernel32

            # --- 常量 ---
            WS_EX_LAYERED = 0x00080000
            WS_EX_TOPMOST = 0x00000008
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_NOACTIVATE = 0x08000000
            WS_POPUP = 0x80000000
            ULW_ALPHA = 0x02
            AC_SRC_OVER = 0x00
            AC_SRC_ALPHA = 0x01
            WM_TIMER = 0x0113
            WM_USER = 0x0400
            WM_QUIT = 0x0012
            SW_HIDE = 0
            SW_SHOWNOACTIVATE = 4
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010

            MSG_CHECK_QUEUE = WM_USER + 1
            TIMER_TICK = 1
            TIMER_POLL = 2

            class BLENDFUNCTION(ctypes.Structure):
                _fields_ = [
                    ("BlendOp", ctypes.c_byte),
                    ("BlendFlags", ctypes.c_byte),
                    ("SourceConstantAlpha", ctypes.c_byte),
                    ("AlphaFormat", ctypes.c_byte),
                ]

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class SIZE(ctypes.Structure):
                _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

            # --- 预渲染数字图片 ---
            pil_images = _render_digits(_WIN_SIZE, _RENDER_SCALE)

            # --- 注册窗口类 ---
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_longlong, ctypes.c_void_p, wintypes.UINT,
                ctypes.c_ulonglong, ctypes.c_longlong
            )

            # 设置 DefWindowProcW 参数/返回类型
            user32.DefWindowProcW.argtypes = [
                ctypes.c_void_p, wintypes.UINT,
                ctypes.c_ulonglong, ctypes.c_longlong,
            ]
            user32.DefWindowProcW.restype = ctypes.c_longlong

            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == WM_TIMER:
                    if wparam == TIMER_POLL:
                        _process_queue()
                    elif wparam == TIMER_TICK:
                        _on_tick()
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            wnd_proc_cb = WNDPROC(wnd_proc)

            class WNDCLASSEXW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("style", wintypes.UINT),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR),
                    ("hIconSm", wintypes.HICON),
                ]

            hinstance = kernel32.GetModuleHandleW(None)
            class_name = "VoxCountdownOverlay"

            wc = WNDCLASSEXW()
            wc.cbSize = sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = wnd_proc_cb
            wc.hInstance = hinstance
            wc.lpszClassName = class_name
            user32.RegisterClassExW(byref(wc))

            # --- 计算窗口位置（屏幕右下角） ---
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
            win_x = screen_w - _WIN_SIZE - 40
            win_y = screen_h - _WIN_SIZE - 80

            # --- 创建 Layered Window ---
            ex_style = (WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
                        | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            hwnd = user32.CreateWindowExW(
                ex_style, class_name, "VoxCountdown",
                WS_POPUP,
                win_x, win_y, _WIN_SIZE, _WIN_SIZE,
                None, None, hinstance, None,
            )

            if not hwnd:
                log.debug("CreateWindowExW 失败")
                return

            # --- 状态 ---
            state = {"remaining": 0, "visible": False}

            def _update_image(digit):
                """将 Pillow RGBA 图片更新到 layered window。"""
                pil_img = pil_images.get(digit)
                if not pil_img:
                    return

                # BGRA 字节序（Win32 要求）
                r, g, b, a = pil_img.split()
                bgra = Image.merge("RGBA", (b, g, r, a))
                raw = bgra.tobytes()

                # 创建 DIB
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

                bmi = BITMAPINFOHEADER()
                bmi.biSize = sizeof(BITMAPINFOHEADER)
                bmi.biWidth = _WIN_SIZE
                bmi.biHeight = -_WIN_SIZE  # top-down
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0  # BI_RGB

                hdc_screen = user32.GetDC(None)
                hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

                ppvBits = ctypes.c_void_p()
                hbmp = gdi32.CreateDIBSection(
                    hdc_mem, byref(bmi), 0, byref(ppvBits), None, 0
                )
                gdi32.SelectObject(hdc_mem, hbmp)

                # 复制像素数据
                ctypes.memmove(ppvBits, raw, len(raw))

                # UpdateLayeredWindow
                pt_src = POINT(0, 0)
                pt_dst = POINT(win_x, win_y)
                sz = SIZE(_WIN_SIZE, _WIN_SIZE)
                blend = BLENDFUNCTION()
                blend.BlendOp = AC_SRC_OVER
                blend.SourceConstantAlpha = 255
                blend.AlphaFormat = AC_SRC_ALPHA

                user32.UpdateLayeredWindow(
                    hwnd, hdc_screen, byref(pt_dst), byref(sz),
                    hdc_mem, byref(pt_src), 0, byref(blend), ULW_ALPHA,
                )

                gdi32.DeleteObject(hbmp)
                gdi32.DeleteDC(hdc_mem)
                user32.ReleaseDC(None, hdc_screen)

            def _show_window(seconds):
                state["remaining"] = seconds
                _update_image(seconds)
                user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )
                state["visible"] = True
                # 启动 1 秒定时器
                user32.SetTimer(hwnd, TIMER_TICK, 1000, None)

            def _hide_window():
                user32.KillTimer(hwnd, TIMER_TICK)
                user32.ShowWindow(hwnd, SW_HIDE)
                state["visible"] = False
                state["remaining"] = 0

            def _on_tick():
                state["remaining"] -= 1
                if state["remaining"] <= 0:
                    _hide_window()
                    return
                _update_image(state["remaining"])

            def _process_queue():
                try:
                    while not self._cmd_queue.empty():
                        cmd, arg = self._cmd_queue.get_nowait()
                        if cmd == _CMD_SHOW:
                            _show_window(arg)
                        elif cmd == _CMD_DISMISS:
                            if state["visible"]:
                                _hide_window()
                except Exception:
                    pass

            # 100ms 定时器轮询队列
            user32.SetTimer(hwnd, TIMER_POLL, 100, None)

            # --- 消息循环 ---
            msg = wintypes.MSG()
            while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))

        except Exception as e:
            log.debug("Win32 倒计时窗口异常: %s，回退到 tkinter", e)
            self._run_tkinter()

    # ----------------------------------------------------------------
    #  非 Windows 回退：tkinter 实现
    # ----------------------------------------------------------------
    def _run_tkinter(self):
        """tkinter 回退实现（macOS / Linux）。"""
        try:
            import tkinter as tk
            from PIL import ImageTk
        except ImportError:
            log.debug("tkinter 或 Pillow 不可用，跳过倒计时浮窗")
            return

        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.withdraw()

            bg = "#010101"
            try:
                root.attributes("-transparentcolor", bg)
                root.attributes("-alpha", 0.75)
            except Exception:
                pass
            root.configure(bg=bg)

            label = tk.Label(root, bg=bg, borderwidth=0, highlightthickness=0)
            label.pack()

            pil_imgs = _render_digits(_WIN_SIZE, _RENDER_SCALE)
            tk_imgs = {d: ImageTk.PhotoImage(img) for d, img in pil_imgs.items()}

            root.update_idletasks()
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            root.geometry(f"{_WIN_SIZE}x{_WIN_SIZE}+{sw - _WIN_SIZE - 40}+{sh - _WIN_SIZE - 80}")

            remaining = [0]
            tick_id = [None]

            def poll():
                try:
                    while not self._cmd_queue.empty():
                        cmd, arg = self._cmd_queue.get_nowait()
                        if cmd == _CMD_SHOW:
                            if tick_id[0]:
                                root.after_cancel(tick_id[0])
                            remaining[0] = arg
                            img = tk_imgs.get(arg)
                            if img:
                                label.configure(image=img)
                            root.deiconify()
                            tick_id[0] = root.after(1000, tick)
                        elif cmd == _CMD_DISMISS:
                            if tick_id[0]:
                                root.after_cancel(tick_id[0])
                                tick_id[0] = None
                            root.withdraw()
                except Exception:
                    pass
                root.after(100, poll)

            def tick():
                remaining[0] -= 1
                if remaining[0] <= 0:
                    root.withdraw()
                    tick_id[0] = None
                    return
                img = tk_imgs.get(remaining[0])
                if img:
                    label.configure(image=img)
                tick_id[0] = root.after(1000, tick)

            root.after(100, poll)
            root.mainloop()
        except Exception as e:
            log.debug("tkinter 倒计时异常: %s", e)
