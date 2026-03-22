"""
预览浮窗模块

在文本光标位置显示半透明深色气泡窗口，实时展示转写/润色状态和结果。
所有模式（Azure / SenseVoice / Whisper / 流式 Paraformer）都通过此浮窗
让用户提前看到处理状态和最终文字。

设计要点：
- tkinter Toplevel，overrideredirect + topmost
- Windows 上用 ctypes 设置 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW 防抢焦点
- 外部通过 queue 通信（参考 countdown.py 的成熟模式）
- 深色半透明背景，文字区域 + 状态行
- 10 秒无更新自动 dismiss（防异常导致永驻）

光标位置获取（Windows）：
- GetGUIThreadInfo + ClientToScreen 获取前台窗口文本光标位置
- 回退：GetCursorPos 取鼠标位置
"""

import platform
import queue
import threading
import time

from src.logger import setup_logger

log = setup_logger(__name__)

# ==================== 命令常量 ====================
_CMD_SHOW = "show"
_CMD_UPDATE = "update"
_CMD_DISMISS = "dismiss"

# ==================== 浮窗样式 ====================
_BG_COLOR = "#1E1E2E"           # 深色背景
_TEXT_COLOR = "#E8ECF4"         # 主文字颜色
_STATUS_COLOR = "#8B92B0"       # 状态行颜色（灰色）
_MAX_WIDTH = 500                # 最大宽度
_WRAP_LENGTH = 400              # 文字自动换行宽度
_PADDING_X = 16                 # 水平内边距
_PADDING_Y = 12                 # 垂直内边距
_AUTO_DISMISS_SEC = 10          # 无更新自动消失（秒）
_OFFSET_X = 10                  # 光标偏移 X
_OFFSET_Y = 20                  # 光标偏移 Y


def _get_caret_position():
    """
    获取浮窗应该出现的位置。

    优先级：
    1. 文本光标位置（GetGUIThreadInfo）— 在记事本等传统应用中精准
    2. 鼠标位置 — 最可靠的通用回退方案

    对文本光标结果做合理性校验：如果坐标为 (0,0) 或超出虚拟屏幕范围，
    说明获取失败，回退到鼠标位置。

    Returns:
        tuple[int, int]: (x, y) 屏幕坐标
    """
    if platform.system() != "Windows":
        return _get_mouse_position()

    try:
        import ctypes
        from ctypes import wintypes, byref, sizeof

        user32 = ctypes.windll.user32

        # 获取前台窗口的线程 ID
        hwnd_fg = user32.GetForegroundWindow()
        if not hwnd_fg:
            return _get_mouse_position()

        thread_id = user32.GetWindowThreadProcessId(hwnd_fg, None)
        if not thread_id:
            return _get_mouse_position()

        # GetGUIThreadInfo 结构体
        class GUITHREADINFO(ctypes.Structure):
            """Win32 GUITHREADINFO 结构体。"""
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT),
            ]

        gui_info = GUITHREADINFO()
        gui_info.cbSize = sizeof(GUITHREADINFO)

        if not user32.GetGUIThreadInfo(thread_id, byref(gui_info)):
            return _get_mouse_position()

        hwnd_caret = gui_info.hwndCaret
        if not hwnd_caret:
            return _get_mouse_position()

        # 将光标矩形的左下角从客户区坐标转为屏幕坐标
        pt = wintypes.POINT()
        pt.x = gui_info.rcCaret.left
        pt.y = gui_info.rcCaret.bottom
        user32.ClientToScreen(hwnd_caret, byref(pt))

        # 合理性校验：坐标 (0,0) 通常是获取失败
        if pt.x == 0 and pt.y == 0:
            return _get_mouse_position()

        # 校验是否在虚拟屏幕范围内
        vs = _get_virtual_screen_bounds()
        if pt.x < vs[0] or pt.x > vs[2] or pt.y < vs[1] or pt.y > vs[3]:
            return _get_mouse_position()

        return (pt.x, pt.y)

    except Exception:
        return _get_mouse_position()


def _get_mouse_position():
    """
    获取鼠标光标的屏幕坐标（跨平台回退方案）。

    Returns:
        tuple[int, int]: (x, y) 屏幕坐标
    """
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes, byref

            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(byref(pt))
            return (pt.x, pt.y)
        except Exception:
            pass

    # macOS / Linux 或 Windows 失败时的回退
    return (500, 500)


def _get_virtual_screen_bounds():
    """
    获取虚拟屏幕边界（多显示器下覆盖所有屏幕的总范围）。

    Windows 上使用 GetSystemMetrics 的 SM_XVIRTUALSCREEN 等参数。
    其他平台回退到单屏幕范围。

    Returns:
        tuple[int, int, int, int]: (left, top, right, bottom) 像素坐标
    """
    if platform.system() == "Windows":
        try:
            import ctypes
            user32 = ctypes.windll.user32

            # SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77
            # SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
            vs_x = user32.GetSystemMetrics(76)
            vs_y = user32.GetSystemMetrics(77)
            vs_w = user32.GetSystemMetrics(78)
            vs_h = user32.GetSystemMetrics(79)

            if vs_w > 0 and vs_h > 0:
                return (vs_x, vs_y, vs_x + vs_w, vs_y + vs_h)
        except Exception:
            pass

    # 回退：假设主屏幕从 (0,0) 开始，大小 1920x1080
    return (0, 0, 9999, 9999)


class PreviewOverlay:
    """
    预览浮窗 — 跟随文本光标显示转写/润色状态和结果。

    外部接口：
    - show(text, status): 显示浮窗（获取光标位置）
    - update_text(text, status): 更新内容（位置不动）
    - dismiss(): 关闭浮窗

    线程安全：所有 tkinter 操作在专属后台线程中执行，通过 queue 通信。
    """

    def __init__(self):
        """初始化预览浮窗（懒启动，首次 show 时才创建线程）。"""
        self._cmd_queue = queue.Queue()
        self._thread = None
        self._started = False

    def _ensure_thread(self):
        """懒启动后台线程（首次 show 时才创建）。"""
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def show(self, text="", status=""):
        """
        显示浮窗（获取光标位置定位）。

        Args:
            text: 主要文字内容
            status: 状态行文字（如 "转写中..."）
        """
        # 在调用线程中获取光标位置（tkinter 线程不一定能拿到前台窗口信息）
        pos = _get_caret_position()
        self._ensure_thread()
        self._cmd_queue.put((_CMD_SHOW, {"text": text, "status": status, "pos": pos}))

    def update_text(self, text, status=""):
        """
        更新浮窗内容（位置不变）。

        Args:
            text: 新的主要文字内容
            status: 新的状态行文字
        """
        if self._started:
            self._cmd_queue.put((_CMD_UPDATE, {"text": text, "status": status}))

    def dismiss(self):
        """关闭浮窗。"""
        if self._started:
            self._cmd_queue.put((_CMD_DISMISS, None))

    def _run(self):
        """后台线程：创建 tkinter 窗口并处理命令队列。"""
        try:
            import tkinter as tk
        except ImportError:
            log.warning("tkinter 不可用，预览浮窗已禁用")
            return

        try:
            root = tk.Tk()
            root.withdraw()
            root.overrideredirect(True)
            root.attributes("-topmost", True)

            # 深色背景
            root.configure(bg=_BG_COLOR)

            # Windows: 设置 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW 防抢焦点
            if platform.system() == "Windows":
                try:
                    self._set_no_activate(root)
                except Exception as e:
                    log.debug("设置 WS_EX_NOACTIVATE 失败: %s", e)

            # 主容器
            frame = tk.Frame(root, bg=_BG_COLOR, padx=_PADDING_X, pady=_PADDING_Y)
            frame.pack(fill="both", expand=True)

            # 文字标签
            text_label = tk.Label(
                frame,
                text="",
                bg=_BG_COLOR,
                fg=_TEXT_COLOR,
                font=("Segoe UI", 11),
                wraplength=_WRAP_LENGTH,
                justify="left",
                anchor="nw",
            )
            text_label.pack(fill="x", expand=True)

            # 状态行标签
            status_label = tk.Label(
                frame,
                text="",
                bg=_BG_COLOR,
                fg=_STATUS_COLOR,
                font=("Segoe UI", 9),
                anchor="w",
            )
            status_label.pack(fill="x", pady=(6, 0))

            # 半透明效果（Windows）
            try:
                root.attributes("-alpha", 0.92)
            except Exception:
                pass

            # 自动消失计时器
            last_update_time = [time.monotonic()]
            auto_dismiss_id = [None]

            def _check_auto_dismiss():
                """每 2 秒检查一次是否超时。"""
                elapsed = time.monotonic() - last_update_time[0]
                if elapsed >= _AUTO_DISMISS_SEC:
                    _do_dismiss()
                else:
                    auto_dismiss_id[0] = root.after(2000, _check_auto_dismiss)

            def _do_show(data):
                """显示浮窗。"""
                text = data.get("text", "")
                status = data.get("status", "")
                pos = data.get("pos", (500, 500))

                text_label.config(text=text if text else "")
                status_label.config(text=status if status else "")

                # 更新布局以获取实际尺寸
                root.update_idletasks()
                w = min(root.winfo_reqwidth(), _MAX_WIDTH)
                h = root.winfo_reqheight()

                # 计算位置：光标下方偏移
                x = pos[0] + _OFFSET_X
                y = pos[1] + _OFFSET_Y

                # 获取虚拟屏幕边界（多显示器下覆盖所有屏幕）
                vscreen = _get_virtual_screen_bounds()
                vs_left, vs_top, vs_right, vs_bottom = vscreen

                # 防止超出虚拟屏幕边界
                if x + w > vs_right:
                    x = vs_right - w - 10
                if y + h > vs_bottom:
                    # 放到光标上方
                    y = pos[1] - h - 10
                if x < vs_left:
                    x = vs_left + 10
                if y < vs_top:
                    y = vs_top + 10

                root.geometry(f"{w}x{h}+{x}+{y}")
                root.deiconify()

                # 重置自动消失计时器
                last_update_time[0] = time.monotonic()
                if auto_dismiss_id[0]:
                    root.after_cancel(auto_dismiss_id[0])
                auto_dismiss_id[0] = root.after(2000, _check_auto_dismiss)

            def _do_update(data):
                """更新浮窗内容（位置不变）。"""
                text = data.get("text", "")
                status = data.get("status", "")

                text_label.config(text=text if text else "")
                status_label.config(text=status if status else "")

                # 更新布局
                root.update_idletasks()
                # 保持 x, y 不变，只调整宽高
                w = min(root.winfo_reqwidth(), _MAX_WIDTH)
                h = root.winfo_reqheight()
                x = root.winfo_x()
                y = root.winfo_y()
                root.geometry(f"{w}x{h}+{x}+{y}")

                # 重置自动消失计时器
                last_update_time[0] = time.monotonic()

            def _do_dismiss():
                """隐藏浮窗。"""
                if auto_dismiss_id[0]:
                    root.after_cancel(auto_dismiss_id[0])
                    auto_dismiss_id[0] = None
                root.withdraw()

            def _poll_queue():
                """每 50ms 检查命令队列。"""
                try:
                    while not self._cmd_queue.empty():
                        cmd, data = self._cmd_queue.get_nowait()
                        if cmd == _CMD_SHOW:
                            _do_show(data)
                        elif cmd == _CMD_UPDATE:
                            _do_update(data)
                        elif cmd == _CMD_DISMISS:
                            _do_dismiss()
                except Exception as e:
                    log.debug("预览浮窗处理命令异常: %s", e)

                root.after(50, _poll_queue)

            # 启动轮询
            root.after(50, _poll_queue)
            root.mainloop()

        except Exception as e:
            log.error("预览浮窗线程异常: %s", e)

    @staticmethod
    def _set_no_activate(root):
        """
        Windows 专用：设置窗口为 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW。

        防止浮窗抢走前台应用的焦点。

        Args:
            root: tkinter Tk 或 Toplevel 窗口
        """
        import ctypes

        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_TOPMOST = 0x00000008
        GWL_EXSTYLE = -20

        user32 = ctypes.windll.user32

        # 需要先让窗口短暂显示以获取 HWND
        root.update_idletasks()
        hwnd = int(root.wm_frame(), 16) if root.wm_frame() else None

        if not hwnd:
            # 备选方法：通过 FindWindowW
            hwnd = user32.FindWindowW(None, root.title())

        if hwnd:
            # 读取当前扩展样式
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # 添加 NOACTIVATE + TOOLWINDOW
            ex_style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
