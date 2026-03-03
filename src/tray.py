"""
系统托盘图标模块

在系统托盘显示一个状态图标，让用户随时知道当前状态：
- 空闲（灰色圆点）
- 录音中（红色圆点）
- 处理中（黄色圆点）

同时提供右键菜单，支持退出操作。
跨平台兼容 macOS 和 Windows。
"""

import sys
import threading

from PIL import Image, ImageDraw

from src.logger import setup_logger

log = setup_logger(__name__)

# 状态常量
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"

# 状态对应的颜色和提示文字
_STATE_CONFIG = {
    STATE_IDLE: {
        "color": "#888888",
        "title": "AI-Input — 空闲",
    },
    STATE_RECORDING: {
        "color": "#FF3333",
        "title": "AI-Input — 录音中...",
    },
    STATE_PROCESSING: {
        "color": "#FFAA00",
        "title": "AI-Input — 处理中...",
    },
}

# 图标尺寸
_ICON_SIZE = 64


def _create_icon_image(color):
    """
    生成一个简单的圆形图标。

    Args:
        color: 圆形的颜色（十六进制字符串）

    Returns:
        PIL.Image: 生成的图标图像
    """
    image = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 画一个带白色边框的实心圆
    margin = 4
    draw.ellipse(
        [margin, margin, _ICON_SIZE - margin, _ICON_SIZE - margin],
        fill=color,
        outline="#FFFFFF",
        width=2,
    )

    return image


class TrayIcon:
    """
    系统托盘图标管理器。

    在后台线程运行 pystray 事件循环，提供状态切换方法供主控制器调用。
    """

    def __init__(self, on_quit=None):
        """
        初始化托盘图标。

        Args:
            on_quit: 用户点击"退出"菜单项时的回调函数
        """
        self._on_quit = on_quit
        self._icon = None
        self._thread = None
        self._current_state = STATE_IDLE

        # 预生成所有状态的图标缓存
        self._icon_cache = {}
        for state, cfg in _STATE_CONFIG.items():
            self._icon_cache[state] = _create_icon_image(cfg["color"])

    def start(self):
        """
        在后台线程中启动托盘图标。

        不阻塞调用线程。
        """
        try:
            import pystray

            menu = pystray.Menu(
                pystray.MenuItem(
                    "AI-Input 语音输入法",
                    None,
                    enabled=False,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "退出",
                    self._handle_quit,
                ),
            )

            self._icon = pystray.Icon(
                name="ai-input",
                icon=self._icon_cache[STATE_IDLE],
                title=_STATE_CONFIG[STATE_IDLE]["title"],
                menu=menu,
            )

            # pystray.run() 会阻塞，所以放在后台线程
            self._thread = threading.Thread(
                target=self._icon.run,
                daemon=True,
            )
            self._thread.start()

            log.info("系统托盘图标已启动")

        except Exception as e:
            log.warning("系统托盘图标启动失败（不影响核心功能）: %s", e)

    def stop(self):
        """停止托盘图标。"""
        try:
            if self._icon:
                self._icon.stop()
                log.info("系统托盘图标已停止")
        except Exception as e:
            log.warning("停止托盘图标时出错: %s", e)

    def set_state(self, state):
        """
        切换托盘图标的状态。

        Args:
            state: 状态常量，可选 STATE_IDLE / STATE_RECORDING / STATE_PROCESSING
        """
        if state not in _STATE_CONFIG:
            log.warning("未知的托盘状态: %s", state)
            return

        self._current_state = state

        try:
            if self._icon:
                self._icon.icon = self._icon_cache[state]
                self._icon.title = _STATE_CONFIG[state]["title"]
        except Exception as e:
            # 托盘更新失败不应影响核心功能
            log.warning("更新托盘图标失败: %s", e)

    def _handle_quit(self, icon, item):
        """
        处理用户点击"退出"菜单项。

        Args:
            icon: pystray 图标实例
            item: 被点击的菜单项
        """
        log.info("用户通过托盘菜单退出程序")
        self.stop()

        if self._on_quit:
            try:
                self._on_quit()
            except Exception as e:
                log.error("退出回调执行失败: %s", e)

        sys.exit(0)
