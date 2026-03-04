"""
系统托盘图标模块

在系统托盘显示一个状态图标，让用户随时知道当前状态：
- 空闲（灰色圆点）
- 录音中（红色圆点）
- 处理中（黄色圆点）

同时提供右键菜单，支持退出操作。
跨平台兼容 macOS 和 Windows。

PIL 和 pystray 均延迟导入，缺少时只降级（不显示图标），不影响核心功能。
"""

import threading

from src.logger import setup_logger

log = setup_logger(__name__)

# 状态常量
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"

# 状态对应的颜色和提示文字
_STATE_CONFIG = {
    STATE_IDLE: {
        "color": "#6C7A89",
        "color2": "#95A5A6",
        "title": "Vox AI Input — 空闲",
    },
    STATE_RECORDING: {
        "color": "#E74C3C",
        "color2": "#FF6B6B",
        "title": "Vox AI Input — 录音中...",
    },
    STATE_PROCESSING: {
        "color": "#F39C12",
        "color2": "#F1C40F",
        "title": "Vox AI Input — 处理中...",
    },
}

# 图标尺寸（用更大画布绘制后缩小，获得抗锯齿效果）
_ICON_SIZE = 64
_RENDER_SIZE = 256


def _create_icon_image(color, color2=None):
    """
    生成一个精致的麦克风托盘图标。

    4x 超采样绘制后缩小到 64x64，自带抗锯齿。
    图标为：渐变圆形背景 + 白色麦克风 + 柔和阴影。

    Args:
        color: 主色（十六进制字符串）
        color2: 渐变终止色（可选，默认同 color）

    Returns:
        PIL.Image: 生成的图标图像
    """
    from PIL import Image, ImageDraw, ImageFilter

    S = _RENDER_SIZE  # 256px 绘制画布
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # ---- 1. 圆形背景（径向渐变模拟） ----
    c1 = _hex_to_rgb(color2 or color)
    c2 = _hex_to_rgb(color)
    cx, cy = S // 2, S // 2
    radius = S // 2 - 4

    # 从外到内画同心圆，颜色从 c2 渐变到 c1
    for r in range(radius, 0, -1):
        t = 1.0 - (r / radius)  # 0(边缘) → 1(中心)
        # 用 ease-out 让亮色集中在中心偏上
        t = t ** 0.6
        rc = int(c2[0] + (c1[0] - c2[0]) * t)
        gc = int(c2[1] + (c1[1] - c2[1]) * t)
        bc = int(c2[2] + (c1[2] - c2[2]) * t)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(rc, gc, bc, 255),
        )

    # ---- 2. 白色麦克风图案 ----
    white = "#FFFFFF"
    shadow = (0, 0, 0, 60)

    # 麦克风头部（圆角矩形）
    mic_w, mic_h = 64, 100
    mic_left = cx - mic_w // 2
    mic_top = 40
    mic_right = mic_left + mic_w
    mic_bottom = mic_top + mic_h
    mic_r = 28  # 圆角

    # 阴影层
    shadow_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    offset = 4
    shadow_draw.rounded_rectangle(
        [mic_left + offset, mic_top + offset, mic_right + offset, mic_bottom + offset],
        radius=mic_r, fill=shadow,
    )
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=6))
    image = Image.alpha_composite(image, shadow_img)
    draw = ImageDraw.Draw(image)

    # 麦克风主体
    draw.rounded_rectangle(
        [mic_left, mic_top, mic_right, mic_bottom],
        radius=mic_r, fill=white,
    )

    # 高光条（左侧，半透明白色增加立体感）
    hl_x = mic_left + 14
    draw.rounded_rectangle(
        [hl_x, mic_top + 14, hl_x + 8, mic_bottom - 14],
        radius=4,
        fill=(255, 255, 255, 120),
    )

    # 麦克风格栅线（三条细横线）
    grill_color = _hex_to_rgb(color) + (80,)  # 带透明度的主题色
    for gy in [mic_top + 30, mic_top + 46, mic_top + 62]:
        draw.line(
            [(mic_left + 16, gy), (mic_right - 16, gy)],
            fill=grill_color, width=3,
        )

    # U 形支架弧（白色）
    arc_pad = 18
    arc_w = 8
    draw.arc(
        [mic_left - arc_pad, mic_bottom - 30, mic_right + arc_pad, mic_bottom + 50],
        start=0, end=180,
        fill=white, width=arc_w,
    )

    # 竖线
    stem_top = mic_bottom + 10
    stem_bottom = mic_bottom + 54
    draw.line([(cx, stem_top), (cx, stem_bottom)], fill=white, width=arc_w)

    # 底座
    base_hw = 30
    draw.rounded_rectangle(
        [cx - base_hw, stem_bottom - 2, cx + base_hw, stem_bottom + 6],
        radius=4, fill=white,
    )

    # ---- 3. 缩小到 64x64（LANCZOS 抗锯齿） ----
    image = image.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)

    return image


def _hex_to_rgb(hex_color):
    """将 '#RRGGBB' 格式的颜色转为 (R, G, B) 元组。"""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


class TrayIcon:
    """
    系统托盘图标管理器。

    在后台线程运行 pystray 事件循环，提供状态切换方法供主控制器调用。
    如果 Pillow 或 pystray 未安装，所有方法静默降级为空操作。
    """

    def __init__(self, on_quit=None, on_settings=None, on_log=None, on_update=None):
        """
        初始化托盘图标。

        Args:
            on_quit: 用户点击"退出"菜单项时的回调函数
            on_settings: 用户点击"设置"菜单项时的回调函数
            on_log: 用户点击"日志"菜单项时的回调函数
            on_update: 用户点击"检查更新"菜单项时的回调函数
        """
        self._on_quit = on_quit
        self._on_settings = on_settings
        self._on_log = on_log
        self._on_update = on_update
        self._icon = None
        self._thread = None
        self._current_state = STATE_IDLE
        self._available = True  # Pillow/pystray 是否可用

        # 尝试预生成所有状态的图标缓存
        self._icon_cache = {}
        try:
            for state, cfg in _STATE_CONFIG.items():
                self._icon_cache[state] = _create_icon_image(
                    cfg["color"], cfg.get("color2"),
                )
        except ImportError:
            log.warning("Pillow 未安装，系统托盘图标不可用（不影响核心功能）")
            self._available = False
        except Exception as e:
            log.warning("生成托盘图标失败: %s（不影响核心功能）", e)
            self._available = False

    def start(self):
        """
        在后台线程中启动托盘图标。

        不阻塞调用线程。如果 Pillow/pystray 不可用则静默跳过。
        """
        if not self._available:
            return

        try:
            import pystray

            from run import __version__

            menu = pystray.Menu(
                pystray.MenuItem(
                    f"v{__version__}",
                    None,
                    enabled=False,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "设置",
                    self._handle_settings,
                ),
                pystray.MenuItem(
                    "日志",
                    self._handle_log,
                ),
                pystray.MenuItem(
                    "检查更新",
                    self._handle_update,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "退出",
                    self._handle_quit,
                ),
            )

            self._icon = pystray.Icon(
                name="vox_ai_input",
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

            log.debug("系统托盘图标已启动")

        except ImportError:
            log.warning("pystray 未安装，系统托盘图标不可用（不影响核心功能）")
            self._available = False
        except Exception as e:
            log.warning("系统托盘图标启动失败（不影响核心功能）: %s", e)

    def stop(self):
        """停止托盘图标。"""
        try:
            if self._icon:
                self._icon.stop()
                log.debug("系统托盘图标已停止")
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
                self._icon.icon = self._icon_cache.get(state)
                self._icon.title = _STATE_CONFIG[state]["title"]
        except Exception as e:
            # 托盘更新失败不应影响核心功能
            log.warning("更新托盘图标失败: %s", e)

    def _handle_settings(self, icon, item):
        """
        处理用户点击"设置"菜单项。

        Args:
            icon: pystray 图标实例
            item: 被点击的菜单项
        """
        if self._on_settings:
            try:
                self._on_settings()
            except Exception as e:
                log.error("打开设置窗口失败: %s", e)

    def _handle_log(self, icon, item):
        """
        处理用户点击"日志"菜单项。

        Args:
            icon: pystray 图标实例
            item: 被点击的菜单项
        """
        if self._on_log:
            try:
                self._on_log()
            except Exception as e:
                log.error("打开日志窗口失败: %s", e)

    def _handle_update(self, icon, item):
        """处理用户点击"检查更新"菜单项。"""
        if self._on_update:
            try:
                self._on_update()
            except Exception as e:
                log.error("检查更新失败: %s", e)

    def _handle_quit(self, icon, item):
        """
        处理用户点击"退出"菜单项。

        先停止托盘图标，然后调用退出回调（由 app.py 负责优雅关闭）。
        设置 3 秒超时安全网，确保所有线程都能终止。

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

        # 安全网：3 秒后若主线程未自然退出，强制终止
        # （避免 daemon 线程阻止程序关闭）
        def _force_exit_fallback():
            import os
            log.warning("优雅退出超时，强制终止")
            os._exit(0)

        timer = threading.Timer(3.0, _force_exit_fallback)
        timer.daemon = True
        timer.start()
