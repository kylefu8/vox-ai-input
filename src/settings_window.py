"""
设置窗口模块

基于 tkinter + ttk 的设置 UI，从系统托盘菜单打开。
提供以下功能：
- 状态显示（当前状态 + 上次结果摘要）
- API 配置（endpoint、key、模型名等）
- 快捷键（按键捕捉 + 冲突检测）、润色开关、开机自启等常用设置
- 高级设置（采样率、声道、时长等，默认折叠）

线程说明：
    整个窗口在独立线程中运行，只有该线程操作 tkinter，线程安全。
    用 _settings_open 标志防止重复打开。
"""

import platform
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from src.autostart import check_autostart, set_autostart, get_autostart_supported
from src.logger import setup_logger

log = setup_logger(__name__)

# 全局标志：是否已有设置窗口打开（防止重复打开）
_settings_open = False

# ==================== 快捷键录制相关常量 ====================

# tkinter keysym → 修饰键名称（与 hotkey.py 的 modifier_map 对应）
_KEYSYM_TO_MODIFIER = {
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Shift_L": "shift", "Shift_R": "shift",
    "Alt_L": "alt", "Alt_R": "alt",
    "Meta_L": "cmd", "Meta_R": "cmd",     # macOS Cmd
    "Super_L": "win", "Super_R": "win",   # Windows Win
    "Win_L": "win", "Win_R": "win",       # 某些 Windows 环境
}

# tkinter keysym → 触发键名称（与 hotkey.py 的 special_key_map 对应）
_KEYSYM_TO_TRIGGER = {
    "space": "space",
    "Tab": "tab",
    "Return": "enter",
    "Escape": "esc",
    "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4",
    "F5": "f5", "F6": "f6", "F7": "f7", "F8": "f8",
    "F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",
    "BackSpace": "backspace",
    "Delete": "delete",
    "Insert": "insert",
    "Home": "home",
    "End": "end",
    "Prior": "pageup",    # tkinter 中 Page Up 的 keysym
    "Next": "pagedown",   # tkinter 中 Page Down 的 keysym
}

# 修饰键的排序优先级（保证输出一致）
_MODIFIER_ORDER = ["ctrl", "alt", "shift", "cmd", "win"]

# 常见系统保留/高冲突快捷键（警告，不阻止）
_RESERVED_HOTKEYS = {
    # 剪贴板基本操作
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+a",
    "cmd+c", "cmd+v", "cmd+x", "cmd+z", "cmd+a",
    # 系统级
    "alt+f4", "alt+tab",
    "cmd+q", "cmd+w", "cmd+tab", "cmd+space",
    # 常用应用快捷键
    "ctrl+s", "ctrl+p", "ctrl+f", "ctrl+n", "ctrl+w",
    "ctrl+t", "ctrl+r",
}


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
        self._root.title("Vox AI Input 设置")
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

    # ==================== 快捷键录制 ====================

    def _start_hotkey_recording(self):
        """开始录制快捷键：绑定键盘事件，等待用户按下组合键。"""
        self._is_recording_hotkey = True
        self._recording_modifiers = set()

        # 切换 UI 状态
        self._hotkey_var.set("按下快捷键组合...")
        self._record_btn.config(
            text="取消", command=self._cancel_hotkey_recording
        )

        # 绑定键盘事件到窗口
        self._root.bind("<KeyPress>", self._on_hotkey_key_press)
        self._root.bind("<KeyRelease>", self._on_hotkey_key_release)

        # 聚焦到窗口（确保能接收键盘事件）
        self._root.focus_force()

    def _cancel_hotkey_recording(self):
        """取消录制，恢复原来的快捷键。"""
        self._stop_hotkey_recording()
        # 恢复为原来的配置值
        original = self._config.get("hotkey", {}).get(
            "combination", "ctrl+shift+space"
        )
        self._hotkey_var.set(original)

    def _stop_hotkey_recording(self):
        """停止录制：解除键盘绑定，恢复按钮状态。"""
        self._is_recording_hotkey = False
        self._recording_modifiers = set()

        # 解除键盘绑定
        self._root.unbind("<KeyPress>")
        self._root.unbind("<KeyRelease>")

        # 恢复按钮
        self._record_btn.config(
            text="录制", command=self._start_hotkey_recording
        )

    def _on_hotkey_key_press(self, event):
        """
        录制模式下的按键按下处理。

        修饰键按下 → 加入集合，实时更新显示。
        非修饰键按下 → 组合出完整快捷键字符串，完成录制。
        """
        if not self._is_recording_hotkey:
            return "break"

        keysym = event.keysym

        # 检查是否是修饰键
        modifier = _KEYSYM_TO_MODIFIER.get(keysym)
        if modifier:
            self._recording_modifiers.add(modifier)
            # 实时显示当前按下的修饰键
            parts = self._sort_modifiers(self._recording_modifiers)
            self._hotkey_var.set("+".join(parts) + "+...")
            return "break"

        # 非修饰键 → 组合出完整快捷键
        trigger = self._keysym_to_trigger(keysym)
        if not trigger:
            # 无法识别的键，忽略
            return "break"

        # 组合出完整的快捷键字符串
        parts = self._sort_modifiers(self._recording_modifiers) + [trigger]
        combination = "+".join(parts)

        # 停止录制
        self._stop_hotkey_recording()
        self._hotkey_var.set(combination)

        # 检查冲突
        self._check_hotkey_conflict(combination)

        return "break"

    def _on_hotkey_key_release(self, event):
        """
        录制模式下的按键松开处理。

        修饰键松开 → 从集合移除。
        """
        if not self._is_recording_hotkey:
            return "break"

        keysym = event.keysym
        modifier = _KEYSYM_TO_MODIFIER.get(keysym)
        if modifier:
            self._recording_modifiers.discard(modifier)
            # 更新显示
            if self._recording_modifiers:
                parts = self._sort_modifiers(self._recording_modifiers)
                self._hotkey_var.set("+".join(parts) + "+...")
            else:
                self._hotkey_var.set("按下快捷键组合...")

        return "break"

    @staticmethod
    def _sort_modifiers(modifiers):
        """
        按固定顺序排列修饰键，保证输出一致（如 ctrl+shift 而不是 shift+ctrl）。

        Args:
            modifiers: 修饰键名称集合

        Returns:
            list: 排序后的修饰键名称列表
        """
        return [m for m in _MODIFIER_ORDER if m in modifiers]

    @staticmethod
    def _keysym_to_trigger(keysym):
        """
        将 tkinter keysym 转换为 hotkey.py 能识别的触发键名称。

        Args:
            keysym: tkinter 的按键标识

        Returns:
            str | None: 转换后的键名，无法识别则返回 None
        """
        # 先查特殊键表
        trigger = _KEYSYM_TO_TRIGGER.get(keysym)
        if trigger:
            return trigger

        # 单个可打印字符（字母、数字）
        if len(keysym) == 1 and keysym.isprintable():
            return keysym.lower()

        # 不认识的键
        return None

    def _check_hotkey_conflict(self, combination):
        """
        检查快捷键是否与常见系统快捷键冲突。

        冲突时弹出警告对话框（不阻止，让用户决定）。

        Args:
            combination: 快捷键字符串，如 "ctrl+c"
        """
        normalized = combination.lower()
        warnings = []

        # 检查是否在保留快捷键列表中
        if normalized in _RESERVED_HOTKEYS:
            warnings.append(
                f"\"{combination}\" 是常用的系统/应用快捷键，"
                "使用后可能影响正常操作。"
            )

        # 检查是否没有修饰键（纯单键）
        parts = normalized.split("+")
        has_modifier = any(
            p in ("ctrl", "alt", "shift", "cmd", "win") for p in parts
        )
        if not has_modifier:
            warnings.append(
                f"快捷键 \"{combination}\" 没有修饰键（Ctrl/Alt/Shift 等），"
                "可能与正常打字冲突。"
            )

        # macOS 特有的 Ctrl+Space 冲突
        if platform.system() == "Darwin" and normalized == "ctrl+space":
            warnings.append(
                "macOS 上 Ctrl+Space 默认用于切换输入法，可能导致冲突。"
            )

        if warnings:
            message = "\n\n".join(warnings)
            message += "\n\n确定使用这个快捷键吗？"
            if not messagebox.askyesno(
                "快捷键冲突警告", message, parent=self._root,
                icon="warning",
            ):
                # 用户取消，恢复原来的值
                original = self._config.get("hotkey", {}).get(
                    "combination", "ctrl+shift+space"
                )
                self._hotkey_var.set(original)

    # ==================== 常用设置区域 ====================

    def _build_common_section(self, parent):
        """构建常用设置区域。"""
        frame = ttk.LabelFrame(parent, text="常用设置", padding=8)
        frame.pack(fill="x", pady=4)

        hotkey = self._config.get("hotkey", {})
        polish = self._config.get("polish", {})

        # ---- 快捷键（按键捕捉） ----
        row_frame = ttk.Frame(frame)
        row_frame.pack(fill="x", pady=2)
        ttk.Label(row_frame, text="快捷键").pack(side="left")

        self._hotkey_var = tk.StringVar(
            value=hotkey.get("combination", "ctrl+shift+space")
        )

        # 快捷键显示标签（只读展示当前组合键）
        self._hotkey_display = ttk.Label(
            row_frame, textvariable=self._hotkey_var,
            width=22, anchor="center", relief="sunken", padding=(4, 2),
        )
        self._hotkey_display.pack(side="left", padx=(8, 0))

        # 录制 / 取消 按钮
        self._record_btn = ttk.Button(
            row_frame, text="录制", width=5,
            command=self._start_hotkey_recording,
        )
        self._record_btn.pack(side="left", padx=(4, 0))

        # 录制状态标志
        self._is_recording_hotkey = False
        self._recording_modifiers = set()

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
