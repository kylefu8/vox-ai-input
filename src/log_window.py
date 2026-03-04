"""
实时日志窗口模块

提供一个可滚动的日志查看窗口，通过 logging.Handler 接收日志，
在 tkinter Text 控件中实时滚动显示。

特性：
- 独立线程运行，不阻塞主程序
- 自动滚动到最新日志
- 不同级别用不同颜色标识
- 最多保留 2000 行，防止内存膨胀
- 关闭窗口只是隐藏，再次点击菜单重新显示
"""

import logging
import platform
import queue
import threading
from src.logger import setup_logger

log = setup_logger(__name__)

# 最大显示行数
_MAX_LINES = 2000

# 日志级别对应的颜色标签
_LEVEL_COLORS = {
    "DEBUG": "#888888",
    "INFO": "#D4D4D4",
    "WARNING": "#F39C12",
    "ERROR": "#E74C3C",
    "CRITICAL": "#FF0000",
}

_CMD_SHOW = "show"
_CMD_LOG = "log"


class _LogQueueHandler(logging.Handler):
    """将日志记录发送到 queue 的 Handler。"""

    def __init__(self, log_queue):
        super().__init__()
        self._queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname
            self._queue.put((_CMD_LOG, (level, msg)))
        except Exception:
            pass


class LogWindow:
    """
    实时日志查看窗口。

    在独立线程中运行 tkinter 窗口，通过 queue 接收日志消息。
    调用 show() 显示窗口，关闭按钮只是隐藏。
    """

    def __init__(self):
        """初始化并启动后台 tkinter 线程。"""
        self._cmd_queue = queue.Queue()
        self._handler = None
        self._thread = threading.Thread(target=self._tk_thread, daemon=True)
        self._thread.start()
        self._install_handler()

    def show(self):
        """显示日志窗口（如果已隐藏则重新显示）。"""
        self._cmd_queue.put((_CMD_SHOW, None))

    def _install_handler(self):
        """
        将日志 Handler 挂载到所有 src.* logger。

        因为各 logger 设置了 propagate=False，不会传播到根 logger，
        所以需要逐个挂载。同时也挂到根 logger 以捕获未来新建的 logger。
        """
        self._handler = _LogQueueHandler(self._cmd_queue)
        self._handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s",
            datefmt="%H:%M:%S",
        )
        self._handler.setFormatter(formatter)

        # 遍历已创建的 src.* logger，逐个挂载
        manager = logging.Logger.manager
        for name, logger_ref in list(manager.loggerDict.items()):
            if name.startswith("src.") and isinstance(logger_ref, logging.Logger):
                logger_ref.addHandler(self._handler)

        # 也挂到根 logger（捕获后续新建的、propagate=True 的 logger）
        logging.getLogger().addHandler(self._handler)

    def _tk_thread(self):
        """持久的 tkinter 线程。"""
        try:
            import tkinter as tk
            from tkinter import font as tkfont
        except ImportError:
            log.debug("tkinter 不可用，跳过日志窗口")
            return

        try:
            root = tk.Tk()
            root.title("Vox AI Input — 日志")
            root.geometry("860x480")
            root.configure(bg="#1E1E1E")

            # 窗口图标（可选）
            try:
                if platform.system() == "Windows":
                    root.iconbitmap(default="")
            except Exception:
                pass

            # 关闭按钮 = 隐藏，不退出
            root.protocol("WM_DELETE_WINDOW", lambda: root.withdraw())
            root.withdraw()  # 初始隐藏

            # 等宽字体
            mono_font = tkfont.Font(family="Consolas", size=10)

            # 主框架
            frame = tk.Frame(root, bg="#1E1E1E")
            frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

            # 文本控件 + 滚动条
            scrollbar = tk.Scrollbar(frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            text = tk.Text(
                frame,
                bg="#1E1E1E",
                fg="#D4D4D4",
                font=mono_font,
                wrap=tk.WORD,
                state=tk.DISABLED,
                insertbackground="#D4D4D4",
                selectbackground="#264F78",
                selectforeground="#FFFFFF",
                borderwidth=0,
                highlightthickness=0,
                padx=8,
                pady=4,
                yscrollcommand=scrollbar.set,
            )
            text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=text.yview)

            # 为每个级别配置颜色标签
            for level, color in _LEVEL_COLORS.items():
                text.tag_configure(level, foreground=color)

            # 底部状态栏
            status_frame = tk.Frame(root, bg="#2D2D2D", height=24)
            status_frame.pack(fill=tk.X, side=tk.BOTTOM)

            line_count_var = tk.StringVar(master=root, value="0 行")
            status_label = tk.Label(
                status_frame,
                textvariable=line_count_var,
                bg="#2D2D2D",
                fg="#888888",
                font=("Segoe UI", 9),
                padx=8,
            )
            status_label.pack(side=tk.RIGHT)

            auto_scroll = [True]

            def _on_scroll(*args):
                """检测用户是否手动滚动（关闭自动滚动）。"""
                # 如果滚动条在底部附近，恢复自动滚动
                try:
                    pos = text.yview()
                    auto_scroll[0] = pos[1] >= 0.98
                except Exception:
                    pass

            text.bind("<MouseWheel>", lambda e: _on_scroll())
            scrollbar.config(command=lambda *a: (text.yview(*a), _on_scroll()))

            total_lines = [0]

            def _append_log(level, msg):
                """向文本控件追加一行日志。"""
                text.configure(state=tk.NORMAL)
                tag = level if level in _LEVEL_COLORS else "INFO"
                text.insert(tk.END, msg + "\n", tag)

                total_lines[0] += 1

                # 超过最大行数时删除头部
                if total_lines[0] > _MAX_LINES:
                    text.delete("1.0", "2.0")
                    total_lines[0] -= 1

                text.configure(state=tk.DISABLED)

                # 自动滚动到底部
                if auto_scroll[0]:
                    text.see(tk.END)

                line_count_var.set(f"{total_lines[0]} 行")

            def _process_queue():
                """轮询队列。"""
                try:
                    count = 0
                    while not self._cmd_queue.empty() and count < 50:
                        cmd, arg = self._cmd_queue.get_nowait()
                        if cmd == _CMD_SHOW:
                            root.deiconify()
                            root.lift()
                            root.focus_force()
                        elif cmd == _CMD_LOG:
                            level, msg = arg
                            _append_log(level, msg)
                        count += 1
                except Exception:
                    pass
                root.after(100, _process_queue)

            root.after(100, _process_queue)
            root.mainloop()

        except Exception as e:
            log.debug("日志窗口异常: %s", e)
