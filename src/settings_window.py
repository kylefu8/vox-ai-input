"""
设置窗口模块

基于 tkinter + ttk 的设置 UI，从系统托盘菜单打开。
提供以下功能：
- 状态显示（当前状态 + 上次结果摘要）
- API 配置（endpoint、key、模型名等）
- 快捷键、润色开关、开机自启等常用设置
- 高级设置（采样率、声道、时长等，默认折叠）

线程说明：
    整个窗口在独立线程中运行，只有该线程操作 tkinter，线程安全。
    用 _settings_open 标志防止重复打开。
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from src.autostart import check_autostart, set_autostart, get_autostart_supported
from src.logger import setup_logger

log = setup_logger(__name__)

# 全局标志：是否已有设置窗口打开（防止重复打开）
_settings_open = False


class SettingsWindow:
    """
    设置窗口。

    在独立 Tk 实例中运行，不依赖外部事件循环。

    Args:
        current_config: 当前配置字典（与 config.yaml 结构一致）
        status_info: 状态信息字典 {"state": str, "last_text": str, "last_duration": float}
        on_save: 保存回调，接收新配置字典，返回 (bool, str) 表示成功/失败及消息
    """

    def __init__(self, current_config, status_info=None, on_save=None):
        global _settings_open
        _settings_open = True

        self._config = current_config
        self._status_info = status_info or {}
        self._on_save = on_save

        # 高级设置区域是否展开
        self._advanced_visible = False

        self._build_ui()

    def _build_ui(self):
        """构建完整的窗口 UI。"""
        self._root = tk.Tk()
        self._root.title("AI-Input 设置")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 窗口居中
        self._root.withdraw()  # 先隐藏，等布局完成后再显示

        # 主框架（带内边距）
        main_frame = ttk.Frame(self._root, padding=15)
        main_frame.pack(fill="both", expand=True)

        # ---- 状态区域 ----
        self._build_status_section(main_frame)

        # ---- 分割线 ----
        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=8)

        # ---- API 配置区域 ----
        self._build_api_section(main_frame)

        # ---- 分割线 ----
        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=8)

        # ---- 常用设置区域 ----
        self._build_common_section(main_frame)

        # ---- 分割线 ----
        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=8)

        # ---- 高级设置区域（可折叠） ----
        self._build_advanced_section(main_frame)

        # ---- 分割线 ----
        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=8)

        # ---- 底部按钮 ----
        self._build_buttons(main_frame)

        # 布局完成，计算窗口大小并居中显示
        self._root.update_idletasks()
        self._center_window()
        self._root.deiconify()

    # ==================== 状态区域 ====================

    def _build_status_section(self, parent):
        """构建状态显示区域。"""
        frame = ttk.LabelFrame(parent, text="当前状态", padding=8)
        frame.pack(fill="x", pady=(0, 4))

        # 状态行
        state_frame = ttk.Frame(frame)
        state_frame.pack(fill="x")

        state = self._status_info.get("state", "idle")
        state_map = {
            "idle": ("空闲", "#888888"),
            "recording": ("录音中...", "#FF3333"),
            "processing": ("处理中...", "#FFAA00"),
        }
        state_text, state_color = state_map.get(state, ("未知", "#888888"))

        # 使用 Canvas 画一个小圆点作为状态指示
        canvas = tk.Canvas(state_frame, width=12, height=12,
                           highlightthickness=0, bg=frame.winfo_toplevel().cget("bg"))
        canvas.pack(side="left", padx=(0, 6), pady=2)
        canvas.create_oval(1, 1, 11, 11, fill=state_color, outline="")

        ttk.Label(state_frame, text=state_text).pack(side="left")

        # 上次结果摘要
        last_text = self._status_info.get("last_text", "")
        last_duration = self._status_info.get("last_duration", 0)

        if last_text:
            # 截断过长文字
            display_text = last_text if len(last_text) <= 40 else last_text[:37] + "..."
            duration_str = f"（{last_duration:.1f}秒）" if last_duration else ""
            result_label = ttk.Label(
                frame,
                text=f"上次结果: \"{display_text}\"{duration_str}",
                foreground="#666666",
            )
            result_label.pack(fill="x", pady=(4, 0))

    # ==================== API 配置区域 ====================

    def _build_api_section(self, parent):
        """构建 API 配置区域。"""
        frame = ttk.LabelFrame(parent, text="API 配置", padding=8)
        frame.pack(fill="x", pady=4)

        azure = self._config.get("azure", {})

        # 端点 URL
        ttk.Label(frame, text="端点 URL").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self._endpoint_var = tk.StringVar(value=azure.get("endpoint", ""))
        ttk.Entry(frame, textvariable=self._endpoint_var, width=45).grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=2, padx=(8, 0)
        )

        # API Key（带遮掩切换）
        ttk.Label(frame, text="API Key").grid(
            row=1, column=0, sticky="w", pady=2
        )
        self._apikey_var = tk.StringVar(value=azure.get("api_key", ""))
        self._apikey_entry = ttk.Entry(
            frame, textvariable=self._apikey_var, width=38, show="*"
        )
        self._apikey_entry.grid(
            row=1, column=1, sticky="ew", pady=2, padx=(8, 0)
        )
        self._show_key = False
        self._toggle_key_btn = ttk.Button(
            frame, text="显示", width=5, command=self._toggle_api_key
        )
        self._toggle_key_btn.grid(row=1, column=2, padx=(4, 0), pady=2)

        # 转写模型
        ttk.Label(frame, text="转写模型").grid(
            row=2, column=0, sticky="w", pady=2
        )
        self._whisper_var = tk.StringVar(
            value=azure.get("whisper_deployment", "")
        )
        ttk.Entry(frame, textvariable=self._whisper_var, width=45).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=2, padx=(8, 0)
        )

        # 润色模型
        ttk.Label(frame, text="润色模型").grid(
            row=3, column=0, sticky="w", pady=2
        )
        self._gpt_var = tk.StringVar(
            value=azure.get("gpt_deployment", "")
        )
        ttk.Entry(frame, textvariable=self._gpt_var, width=45).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=2, padx=(8, 0)
        )

        # 让输入框列自动伸缩
        frame.columnconfigure(1, weight=1)

    def _toggle_api_key(self):
        """切换 API Key 的显示/隐藏。"""
        self._show_key = not self._show_key
        self._apikey_entry.config(show="" if self._show_key else "*")
        self._toggle_key_btn.config(text="隐藏" if self._show_key else "显示")

    # ==================== 常用设置区域 ====================

    def _build_common_section(self, parent):
        """构建常用设置区域。"""
        frame = ttk.LabelFrame(parent, text="常用设置", padding=8)
        frame.pack(fill="x", pady=4)

        hotkey = self._config.get("hotkey", {})
        polish = self._config.get("polish", {})

        # 快捷键
        row_frame = ttk.Frame(frame)
        row_frame.pack(fill="x", pady=2)
        ttk.Label(row_frame, text="快捷键").pack(side="left")
        self._hotkey_var = tk.StringVar(
            value=hotkey.get("combination", "ctrl+shift+space")
        )
        ttk.Entry(row_frame, textvariable=self._hotkey_var, width=25).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(row_frame, text="(改后需重启)", foreground="#999999").pack(
            side="left", padx=(6, 0)
        )

        # 启用润色
        row_frame2 = ttk.Frame(frame)
        row_frame2.pack(fill="x", pady=2)
        self._polish_var = tk.BooleanVar(
            value=polish.get("enabled", True)
        )
        ttk.Checkbutton(
            row_frame2, text="启用 AI 润色", variable=self._polish_var
        ).pack(side="left")

        # 开机自启（如果平台支持）
        if get_autostart_supported():
            row_frame3 = ttk.Frame(frame)
            row_frame3.pack(fill="x", pady=2)
            self._autostart_var = tk.BooleanVar(value=check_autostart())
            ttk.Checkbutton(
                row_frame3, text="开机自启动", variable=self._autostart_var
            ).pack(side="left")
        else:
            self._autostart_var = None

    # ==================== 高级设置区域（可折叠） ====================

    def _build_advanced_section(self, parent):
        """构建可折叠的高级设置区域。"""
        # 展开/收起按钮
        self._toggle_btn = ttk.Button(
            parent, text="▶ 高级设置（谨慎修改）",
            command=self._toggle_advanced,
        )
        self._toggle_btn.pack(fill="x", pady=(4, 0))

        # 高级设置内容框架（初始隐藏）
        self._advanced_frame = ttk.LabelFrame(parent, text="高级设置", padding=8)

        azure = self._config.get("azure", {})
        recording = self._config.get("recording", {})
        polish = self._config.get("polish", {})

        # 警告提示
        warn_label = ttk.Label(
            self._advanced_frame,
            text="  修改以下设置可能影响程序运行",
            foreground="#CC6600",
        )
        warn_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        # API 版本
        ttk.Label(self._advanced_frame, text="API 版本").grid(
            row=1, column=0, sticky="w", pady=2
        )
        self._api_version_var = tk.StringVar(
            value=azure.get("api_version", "2024-06-01")
        )
        ttk.Entry(
            self._advanced_frame, textvariable=self._api_version_var, width=30
        ).grid(row=1, column=1, sticky="ew", pady=2, padx=(8, 0))

        # 采样率
        ttk.Label(self._advanced_frame, text="采样率 (Hz)").grid(
            row=2, column=0, sticky="w", pady=2
        )
        self._sample_rate_var = tk.StringVar(
            value=str(recording.get("sample_rate", 16000))
        )
        ttk.Entry(
            self._advanced_frame, textvariable=self._sample_rate_var, width=30
        ).grid(row=2, column=1, sticky="ew", pady=2, padx=(8, 0))

        # 声道数
        ttk.Label(self._advanced_frame, text="声道数").grid(
            row=3, column=0, sticky="w", pady=2
        )
        self._channels_var = tk.StringVar(
            value=str(recording.get("channels", 1))
        )
        ttk.Entry(
            self._advanced_frame, textvariable=self._channels_var, width=30
        ).grid(row=3, column=1, sticky="ew", pady=2, padx=(8, 0))

        # 最大录音时长
        ttk.Label(self._advanced_frame, text="最大时长 (秒)").grid(
            row=4, column=0, sticky="w", pady=2
        )
        self._max_duration_var = tk.StringVar(
            value=str(recording.get("max_duration", 60))
        )
        ttk.Entry(
            self._advanced_frame, textvariable=self._max_duration_var, width=30
        ).grid(row=4, column=1, sticky="ew", pady=2, padx=(8, 0))

        # 识别语言
        ttk.Label(self._advanced_frame, text="识别语言").grid(
            row=5, column=0, sticky="w", pady=2
        )
        self._language_var = tk.StringVar(
            value=polish.get("language", "")
        )
        lang_frame = ttk.Frame(self._advanced_frame)
        lang_frame.grid(row=5, column=1, sticky="ew", pady=2, padx=(8, 0))
        ttk.Entry(lang_frame, textvariable=self._language_var, width=10).pack(
            side="left"
        )
        ttk.Label(
            lang_frame, text="(留空=自动检测, zh=中文, en=英文)",
            foreground="#999999",
        ).pack(side="left", padx=(6, 0))

        self._advanced_frame.columnconfigure(1, weight=1)

    def _toggle_advanced(self):
        """切换高级设置区域的展开/收起。"""
        self._advanced_visible = not self._advanced_visible

        if self._advanced_visible:
            self._toggle_btn.config(text="▼ 高级设置（谨慎修改）")
            self._advanced_frame.pack(fill="x", pady=(4, 0), after=self._toggle_btn)
        else:
            self._toggle_btn.config(text="▶ 高级设置（谨慎修改）")
            self._advanced_frame.pack_forget()

        # 重新计算窗口大小
        self._root.update_idletasks()
        self._center_window()

    # ==================== 底部按钮 ====================

    def _build_buttons(self, parent):
        """构建底部按钮区域。"""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", pady=(4, 0))

        ttk.Button(
            btn_frame, text="取消", command=self._on_close
        ).pack(side="right", padx=(6, 0))

        ttk.Button(
            btn_frame, text="保存", command=self._on_save_click
        ).pack(side="right")

    # ==================== 保存逻辑 ====================

    def _on_save_click(self):
        """用户点击保存时的处理。"""
        try:
            new_config = self._collect_config()
        except ValueError as e:
            messagebox.showerror("输入错误", str(e), parent=self._root)
            return

        # 处理开机自启（独立于配置文件）
        if self._autostart_var is not None:
            try:
                set_autostart(self._autostart_var.get())
            except Exception as e:
                log.warning("设置开机自启失败: %s", e)

        # 检查快捷键是否变更
        old_hotkey = self._config.get("hotkey", {}).get("combination", "")
        new_hotkey = new_config.get("hotkey", {}).get("combination", "")
        hotkey_changed = old_hotkey != new_hotkey

        # 调用保存回调
        if self._on_save:
            try:
                success, msg = self._on_save(new_config)
                if success:
                    if hotkey_changed:
                        messagebox.showinfo(
                            "保存成功",
                            "配置已保存。\n\n快捷键已更改，需要重启程序才能生效。",
                            parent=self._root,
                        )
                    else:
                        messagebox.showinfo(
                            "保存成功", "配置已保存并立即生效。",
                            parent=self._root,
                        )
                    self._on_close()
                else:
                    messagebox.showerror(
                        "保存失败", msg or "未知错误",
                        parent=self._root,
                    )
            except Exception as e:
                messagebox.showerror(
                    "保存失败", f"保存出错: {e}",
                    parent=self._root,
                )
        else:
            # 没有保存回调，直接关闭
            self._on_close()

    def _collect_config(self):
        """
        从 UI 字段收集配置字典。

        Returns:
            dict: 新的配置字典

        Raises:
            ValueError: 如果必填字段为空
        """
        # 基本验证
        endpoint = self._endpoint_var.get().strip()
        api_key = self._apikey_var.get().strip()
        whisper = self._whisper_var.get().strip()
        gpt = self._gpt_var.get().strip()

        if not endpoint:
            raise ValueError("端点 URL 不能为空")
        if not api_key:
            raise ValueError("API Key 不能为空")
        if not whisper:
            raise ValueError("转写模型不能为空")
        if not gpt:
            raise ValueError("润色模型不能为空")

        # 验证数值字段
        try:
            sample_rate = int(self._sample_rate_var.get().strip())
            if sample_rate <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("采样率必须是正整数")

        try:
            channels = int(self._channels_var.get().strip())
            if channels <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("声道数必须是正整数")

        try:
            max_duration = int(self._max_duration_var.get().strip())
            if max_duration <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("最大录音时长必须是正整数")

        return {
            "azure": {
                "endpoint": endpoint,
                "api_key": api_key,
                "api_version": self._api_version_var.get().strip(),
                "whisper_deployment": whisper,
                "gpt_deployment": gpt,
            },
            "recording": {
                "sample_rate": sample_rate,
                "channels": channels,
                "max_duration": max_duration,
            },
            "hotkey": {
                "combination": self._hotkey_var.get().strip(),
            },
            "polish": {
                "enabled": self._polish_var.get(),
                "language": self._language_var.get().strip(),
            },
        }

    # ==================== 窗口管理 ====================

    def _center_window(self):
        """将窗口居中显示在屏幕上。"""
        self._root.update_idletasks()
        w = self._root.winfo_reqwidth()
        h = self._root.winfo_reqheight()
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close(self):
        """关闭窗口，重置全局标志。"""
        global _settings_open
        _settings_open = False
        try:
            self._root.destroy()
        except Exception:
            pass

    def run(self):
        """启动 tkinter 事件循环（应在独立线程中调用）。"""
        try:
            self._root.mainloop()
        except Exception as e:
            log.error("设置窗口异常退出: %s", e)
        finally:
            global _settings_open
            _settings_open = False


def open_settings(current_config, status_info=None, on_save=None):
    """
    在新线程中打开设置窗口。

    如果已有窗口打开，则忽略。

    Args:
        current_config: 当前配置字典
        status_info: 状态信息字典
        on_save: 保存回调函数，接收新配置字典，返回 (bool, str)
    """
    global _settings_open
    if _settings_open:
        log.debug("设置窗口已打开，忽略重复请求")
        return

    def _run():
        try:
            window = SettingsWindow(
                current_config=current_config,
                status_info=status_info,
                on_save=on_save,
            )
            window.run()
        except Exception as e:
            log.error("打开设置窗口失败: %s", e)
            global _settings_open
            _settings_open = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
