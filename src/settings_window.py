"""
设置窗口模块（现代深色主题）

基于 tkinter 的设置 UI，从系统托盘菜单打开。
深色主题 + 卡片式布局 + 彩色强调色，比传统 ttk 更现代。

功能：
- 本地转写模型、AI 润色 API、快捷键、历史记录等常用设置
- 快捷键（按键捕捉 + 冲突检测）、润色开关、翻译等常用设置

线程说明：
    整个窗口在独立线程中运行，只有该线程操作 tkinter，线程安全。
    用 _settings_open 标志防止重复打开。
"""

import platform
import re
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from src.autostart import check_autostart, set_autostart, get_autostart_supported
from src.logger import setup_logger

log = setup_logger(__name__)

_settings_open = False

# ==================== 主题定义 ====================
_THEMES = {
    "dark": {
        "bg": "#0F1217",
        "rail": "#12161D",
        "surface": "#171B22",
        "surface2": "#1D232C",
        "border": "#33404D",
        "text": "#F3F7FA",
        "text2": "#B3BECA",
        "muted": "#8895A4",
        "accent": "#87D7FF",
        "accent_soft": "#153041",
        "green": "#78D89B",
        "red": "#FF7A90",
        "yellow": "#F5C76B",
        "orange": "#F0A45D",
        "btn": "#222936",
        "btn_h": "#2D3645",
        "entry": "#10151D",
    },
    "light": {
        "bg": "#F8F9FC",
        "rail": "#EEF2F7",
        "surface": "#FFFFFF",
        "surface2": "#F4F7FB",
        "border": "#E2E8F0",
        "text": "#1E293B",
        "text2": "#64748B",
        "muted": "#94A3B8",
        "accent": "#0EA5E9",
        "accent_soft": "#E0F2FE",
        "green": "#22C55E",
        "red": "#EF4444",
        "yellow": "#EAB308",
        "orange": "#F97316",
        "btn": "#E2E8F0",
        "btn_h": "#CBD5E1",
        "entry": "#F1F5F9",
    },
}

# 当前主题（默认深色）
_current_theme = "dark"
_C = _THEMES[_current_theme].copy()

# ==================== 快捷键常量 ====================
_KEYSYM_MOD = {
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Shift_L": "shift", "Shift_R": "shift",
    "Alt_L": "alt", "Alt_R": "alt",
    "Meta_L": "cmd", "Meta_R": "cmd",
    "Super_L": "win", "Super_R": "win", "Win_L": "win", "Win_R": "win",
}
_KEYSYM_KEY = {
    "space": "space", "Tab": "tab", "Return": "enter", "Escape": "esc",
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
    "BackSpace": "backspace", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "Prior": "pageup", "Next": "pagedown",
}
_MOD_ORDER = ["ctrl", "alt", "shift", "cmd", "win"]
_RESERVED = {
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+a",
    "alt+f4", "alt+tab", "ctrl+s", "ctrl+p", "ctrl+f",
}

_PROFILE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _normalize_llm_profile_name(name):
    """Return a safe profile id for config.yaml."""
    normalized = _PROFILE_NAME_RE.sub("-", (name or "").strip()).strip("-_.").lower()
    if not normalized:
        raise ValueError("Profile 名称不能为空")
    return normalized


def _unique_llm_profile_name(base, existing):
    """Return a profile id that does not exist yet."""
    existing = set(existing)
    name = _normalize_llm_profile_name(base)
    if name not in existing:
        return name
    index = 2
    while f"{name}-{index}" in existing:
        index += 1
    return f"{name}-{index}"


def _default_llm_profile(provider="openai_compatible", azure=None):
    """Create a default profile for a provider."""
    azure = azure or {}
    if provider == "azure_openai":
        return {
            "provider": "azure_openai",
            "endpoint": azure.get("endpoint", ""),
            "api_key": azure.get("api_key", ""),
            "api_version": "2025-01-01-preview",
            "model": "gpt-5.4-nano",
        }
    if provider == "anthropic":
        return {
            "provider": "anthropic",
            "endpoint": "https://api.anthropic.com",
            "api_key": "",
            "api_version": "2023-06-01",
            "model": "claude-3-5-haiku-20241022",
        }
    return {
        "provider": "openai_compatible",
        "endpoint": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4.1-mini",
    }


def _infer_provider_from_endpoint(endpoint):
    endpoint = (endpoint or "").lower()
    if "anthropic" in endpoint:
        return "anthropic"
    if "openai.azure" in endpoint or ".azure.com" in endpoint:
        return "azure_openai"
    return "openai_compatible"


def _provider_label(provider):
    return {
        "auto": "未验证",
        "azure_openai": "Azure OpenAI",
        "openai_compatible": "OpenAI-compatible",
        "anthropic": "Anthropic",
    }.get(provider or "auto", provider or "未验证")


def _short_text(text, limit=220):
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_history_time(value):
    if not value:
        return "未知时间"
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)[:16]


def _coerce_positive_int(value, default):
    """Return value as positive int, falling back to default."""
    try:
        value = int(value)
        if value > 0:
            return value
    except Exception:
        pass
    return default


def _default_num_threads():
    """A conservative local inference default."""
    import os

    return max(1, (os.cpu_count() or 4) // 2)


# ==================== UI 工具函数 ====================

def _entry(parent, var=None, w=30, show="", **kw):
    """深色输入框。"""
    return tk.Entry(
        parent, textvariable=var, width=w, show=show,
        bg=_C["entry"], fg=_C["text"], insertbackground=_C["accent"],
        selectbackground=_C["accent"], selectforeground="#0F1217",
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=_C["border"], highlightcolor=_C["accent"],
        font=("Segoe UI", 10), **kw,
    )


def _btn(parent, text, cmd=None, accent=False, w=8, **kw):
    """风格化按钮。"""
    bg = _C["accent"] if accent else _C["btn"]
    fg = "#0F1217" if accent else _C["text"]
    hbg = "#B7E6FF" if accent else _C["btn_h"]
    b = tk.Button(
        parent, text=text, command=cmd, bg=bg, fg=fg,
        activebackground=hbg, activeforeground=fg,
        relief="flat", bd=0, padx=12, pady=6,
        font=("Segoe UI Semibold", 9), cursor="hand2", width=w, **kw,
    )
    b.bind("<Enter>", lambda e: b.config(bg=hbg))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def _lbl(parent, text, fg=None, font_size=10, bold=False, bg=None):
    """文字标签。"""
    f = ("Segoe UI Semibold" if bold else "Segoe UI", font_size)
    return tk.Label(parent, text=text, bg=bg or _C["surface"], fg=fg or _C["text2"], font=f, anchor="w")


def _card(parent):
    """卡片容器。"""
    return tk.Frame(
        parent,
        bg=_C["surface"],
        padx=18,
        pady=14,
        highlightthickness=1,
        highlightbackground=_C["border"],
    )


def _section_title(parent, title, subtitle=None, bg=None):
    """紧凑的分区标题。"""
    bg = bg or _C["bg"]
    frame = tk.Frame(parent, bg=bg)
    frame.pack(fill="x", pady=(0, 8))
    tk.Label(
        frame,
        text=title,
        bg=bg,
        fg=_C["accent"],
        font=("Segoe UI Semibold", 11),
        anchor="w",
    ).pack(anchor="w")
    if subtitle:
        tk.Label(
            frame,
            text=subtitle,
            bg=bg,
            fg=_C["text2"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
    return frame


def _pill(parent, text, fg=None, bg=None):
    """小状态标签。"""
    return tk.Label(
        parent,
        text=text,
        bg=bg or _C["surface2"],
        fg=fg or _C["text2"],
        font=("Segoe UI Semibold", 8),
        padx=8,
        pady=3,
    )


def _sep(parent):
    """间距。"""
    tk.Frame(parent, bg=_C["bg"], height=8).pack(fill="x")


class SettingsWindow:
    """现代深色主题设置窗口。"""

    def __init__(
        self,
        current_config,
        status_info=None,
        on_save=None,
        on_clear_history=None,
        on_get_history_entries=None,
        initial_page="transcribe",
        initial_tab=None,
    ):
        global _settings_open
        _settings_open = True
        self._config = current_config
        self._status_info = status_info or {}
        self._on_save = on_save
        self._on_clear_history = on_clear_history
        self._on_get_history_entries = on_get_history_entries
        self._initial_page = initial_page or "transcribe"
        self._initial_tab = initial_tab
        self._translate_options = [
            ("不翻译", ""), ("简体中文", "zh"), ("英语", "en"),
            ("日语", "ja"), ("韩语", "ko"), ("法语", "fr"),
            ("德语", "de"), ("西班牙语", "es"), ("俄语", "ru"),
            ("繁体中文", "zh-TW"),
        ]
        self._llm_profiles = self._build_llm_profiles()
        self._build_ui()

    # ==================== 构建 UI ====================

    def _build_ui(self):
        """构建窗口。"""
        self._root = tk.Tk()
        self._root.title("Vox AI Input")
        self._root.configure(bg=_C["bg"])
        self._root.resizable(True, True)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.minsize(860, 620)
        self._root.withdraw()
        self._configure_fonts()
        self._configure_ttk_style()

        # 设置窗口图标
        self._set_window_icon(self._root)

        m = tk.Frame(self._root, bg=_C["bg"], padx=22, pady=18)
        m.pack(fill="both", expand=True)
        self._rebuild_content(m)

        self._root.update_idletasks()
        self._center_window()
        self._root.deiconify()

    def _configure_fonts(self):
        """Use explicit Windows UI fonts so Tk text renders consistently."""
        try:
            base = ("Segoe UI", 10)
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
                tkfont.nametofont(name).configure(family=base[0], size=base[1])
            tkfont.nametofont("TkSmallCaptionFont").configure(family=base[0], size=9)
            self._root.option_add("*Font", base)
        except Exception:
            pass

    def _configure_ttk_style(self):
        """让 ttk 控件跟随当前主题。"""
        try:
            style = ttk.Style(self._root)
            style.theme_use("clam")
            style.configure(
                "TCombobox",
                fieldbackground=_C["entry"],
                background=_C["surface2"],
                foreground=_C["text"],
                arrowcolor=_C["accent"],
                bordercolor=_C["border"],
                lightcolor=_C["border"],
                darkcolor=_C["border"],
                padding=4,
            )
            style.map(
                "TCombobox",
                fieldbackground=[("readonly", _C["entry"])],
                foreground=[("readonly", _C["text"])],
                background=[("readonly", _C["surface2"])],
            )
            style.configure(
                "Vertical.TScrollbar",
                troughcolor=_C["bg"],
                background=_C["surface2"],
                bordercolor=_C["bg"],
                arrowcolor=_C["text2"],
            )
        except Exception:
            pass

    def _rebuild_content(self, m):
        """构建窗口内容（主题切换时可重建）。"""
        # ---- 标题 ----
        hdr = tk.Frame(m, bg=_C["bg"])
        hdr.pack(fill="x", pady=(0, 16))

        # 左侧：标题 + 版本
        from run import __version__
        left = tk.Frame(hdr, bg=_C["bg"])
        left.pack(side="left")
        tk.Label(left, text="Vox AI Input", bg=_C["bg"], fg=_C["text"],
                 font=("Segoe UI Semibold", 20)).pack(side="left")
        tk.Label(left, text=f"v{__version__}", bg=_C["bg"], fg=_C["text2"],
                 font=("Segoe UI", 11)).pack(side="left", padx=(10, 0), pady=(6, 0))
        _pill(left, "LOCAL FIRST", fg=_C["accent"], bg=_C["accent_soft"]).pack(
            side="left", padx=(12, 0), pady=(7, 0))

        # 右侧：介绍 + 链接 + 主题切换
        right = tk.Frame(hdr, bg=_C["bg"])
        right.pack(side="right")

        info_f = tk.Frame(right, bg=_C["bg"])
        info_f.pack(side="right")
        tk.Label(info_f, text="Local speech · optional polish · instant paste",
                 bg=_C["bg"], fg=_C["text2"], font=("Segoe UI", 9), anchor="e").pack(anchor="e")
        link = tk.Label(info_f, text="github.com/kylefu8/vox-ai-input",
                        bg=_C["bg"], fg=_C["accent"], font=("Segoe UI", 9),
                        cursor="hand2", anchor="e")
        link.pack(anchor="e")
        link.bind("<Button-1>", lambda e: __import__("webbrowser").open(
            "https://github.com/kylefu8/vox-ai-input"))

        body = tk.Frame(m, bg=_C["bg"])
        body.pack(fill="both", expand=True)

        sidebar = tk.Frame(
            body,
            bg=_C["rail"],
            width=154,
            padx=10,
            pady=12,
            highlightthickness=1,
            highlightbackground=_C["border"],
        )
        sidebar.pack(side="left", fill="y", padx=(0, 18))
        sidebar.pack_propagate(False)

        content = tk.Frame(body, bg=_C["bg"])
        content.pack(side="left", fill="both", expand=True)

        scroll_wrap = tk.Frame(content, bg=_C["bg"])
        scroll_wrap.pack(fill="both", expand=True)
        self._settings_canvas = tk.Canvas(
            scroll_wrap,
            bg=_C["bg"],
            highlightthickness=0,
            bd=0,
            yscrollincrement=24,
        )
        self._settings_scrollbar = ttk.Scrollbar(
            scroll_wrap,
            orient="vertical",
            command=self._settings_canvas.yview,
        )
        self._settings_canvas.configure(yscrollcommand=self._settings_scrollbar.set)
        self._settings_canvas.pack(side="left", fill="both", expand=True)
        self._settings_scrollbar.pack(side="right", fill="y")

        self._settings_scroll_frame = tk.Frame(self._settings_canvas, bg=_C["bg"], padx=2, pady=2)
        self._settings_canvas_window = self._settings_canvas.create_window(
            (0, 0),
            window=self._settings_scroll_frame,
            anchor="nw",
        )
        self._settings_scroll_frame.bind("<Configure>", self._on_settings_scroll_frame_configure)
        self._settings_canvas.bind("<Configure>", self._on_settings_canvas_configure)
        self._settings_canvas.bind("<Enter>", self._bind_settings_mousewheel)
        self._settings_canvas.bind("<Leave>", self._unbind_settings_mousewheel)

        self._settings_pages = {}
        self._settings_nav_buttons = {}
        self._settings_tab_frames = {}
        self._settings_tab_buttons = {}
        self._settings_default_tabs = {}

        def add_page(key, title, subtitle):
            page = tk.Frame(self._settings_scroll_frame, bg=_C["bg"])
            header = tk.Frame(page, bg=_C["bg"])
            header.pack(fill="x", pady=(0, 12))
            tk.Label(
                header, text=title, bg=_C["bg"], fg=_C["text"],
                font=("Segoe UI Semibold", 15), anchor="w",
            ).pack(anchor="w")
            tk.Label(
                header, text=subtitle, bg=_C["bg"], fg=_C["text2"],
                font=("Segoe UI", 9), anchor="w",
            ).pack(anchor="w", pady=(2, 0))
            tabbar = tk.Frame(page, bg=_C["bg"])
            tabbar.pack(fill="x", pady=(0, 12))
            body_frame = tk.Frame(page, bg=_C["bg"])
            body_frame.pack(fill="x", expand=True)
            self._settings_pages[key] = page
            self._settings_tab_frames[key] = {}
            self._settings_tab_buttons[key] = {}
            return page, tabbar, body_frame

        def add_tab(page_key, tabbar, body_frame, tab_key, title):
            btn = tk.Button(
                tabbar,
                text=title,
                command=lambda pk=page_key, tk_=tab_key: self._select_settings_tab(pk, tk_),
                bg=_C["surface2"], fg=_C["text2"],
                activebackground=_C["btn_h"], activeforeground=_C["text"],
                relief="flat", bd=0, padx=15, pady=6, cursor="hand2",
                font=("Segoe UI Semibold", 9),
            )
            btn.pack(side="left", padx=(0, 8))
            frame = tk.Frame(body_frame, bg=_C["bg"])
            self._settings_tab_frames[page_key][tab_key] = frame
            self._settings_tab_buttons[page_key][tab_key] = btn
            self._settings_default_tabs.setdefault(page_key, tab_key)
            return frame

        nav_items = [
            ("transcribe", "转写", "本地模型", "本地离线转写模型设置"),
            ("polish", "润色", "AI API", "润色、翻译和 LLM 配置"),
            ("operation", "操作", "快捷键", "触发按键和启动行为"),
            ("data", "数据", "历史记录", "历史浏览与复制"),
        ]

        tk.Label(
            sidebar,
            text="SETTINGS",
            bg=_C["rail"],
            fg=_C["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 8))

        for key, title, small, _subtitle in nav_items:
            btn = tk.Button(
                sidebar,
                text=f"{title}\n{small}",
                command=lambda k=key: self._select_settings_page(k),
                bg=_C["rail"], fg=_C["text2"],
                activebackground=_C["btn_h"], activeforeground=_C["text"],
                relief="flat", bd=0, anchor="w", justify="left",
                padx=12, pady=9, cursor="hand2",
                font=("Segoe UI", 10),
            )
            btn.pack(fill="x", pady=3)
            self._settings_nav_buttons[key] = btn

        tk.Frame(sidebar, bg=_C["border"], height=1).pack(fill="x", pady=14)
        _btn(sidebar, "切换主题", self._toggle_theme, w=12).pack(fill="x", pady=(0, 2))

        transcribe_page, transcribe_tabs, transcribe_body = add_page(
            "transcribe", "转写", "选择本地语音识别模型。")
        polish_page, polish_tabs, polish_body = add_page(
            "polish", "润色", "配置可选 AI 润色连接和翻译输出。")
        operation_page, operation_tabs, operation_body = add_page(
            "operation", "操作", "设置长按录音快捷键和启动行为。")
        data_page, data_tabs, data_body = add_page(
            "data", "数据", "查看、复制和清理最近输出。")

        transcribe_model_tab = add_tab("transcribe", transcribe_tabs, transcribe_body, "model", "本地模型")
        polish_api_tab = add_tab("polish", polish_tabs, polish_body, "api", "连接")
        operation_shortcut_tab = add_tab("operation", operation_tabs, operation_body, "shortcut", "快捷键")
        history_records_tab = add_tab("data", data_tabs, data_body, "records", "历史")

        # 每个主类目只保留一个页面时，隐藏横向 tab，避免重复导航。
        for tabbar in (transcribe_tabs, polish_tabs, operation_tabs, data_tabs):
            tabbar.pack_forget()

        # ---- 转写 ----
        self._build_stt_card(transcribe_model_tab)

        # ---- 润色 ----
        _section_title(polish_api_tab, "润色 API", "只保留连接所需字段，验证时自动识别 API 类型。")
        c_llm = _card(polish_api_tab)
        c_llm.pack(fill="x", pady=(0, 12))
        self._build_llm_profile_card(c_llm)

        hk = self._config.get("hotkey", {})
        po = self._config.get("polish", {})

        _section_title(polish_api_tab, "润色流程", "控制是否调用 AI，以及是否把结果翻译为其他语言。")
        c_polish = _card(polish_api_tab)
        c_polish.pack(fill="x", pady=(0, 12))
        r1 = tk.Frame(c_polish, bg=_C["surface2"], padx=12, pady=8)
        r1.pack(fill="x", pady=4)
        self._polish_var = tk.BooleanVar(master=self._root, value=po.get("enabled", False))
        tk.Checkbutton(
            r1, text="启用 AI 润色", variable=self._polish_var,
            bg=_C["surface2"], fg=_C["text"], selectcolor=_C["entry"],
            activebackground=_C["surface2"], activeforeground=_C["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        _pill(r1, "可选", fg=_C["text2"], bg=_C["surface"]).pack(side="right")

        r2 = tk.Frame(c_polish, bg=_C["surface"])
        r2.pack(fill="x", pady=(10, 4))
        tk.Label(r2, text="翻译", bg=_C["surface"], fg=_C["text2"], font=("Segoe UI Semibold", 9),
                 width=10, anchor="w").pack(side="left")
        tl = po.get("translate_to", "")
        cur = "不翻译"
        for lb, cd in self._translate_options:
            if cd == tl:
                cur = lb
                break
        self._translate_var = tk.StringVar(master=self._root, value=cur)
        cb = ttk.Combobox(r2, textvariable=self._translate_var,
                          values=[l for l, _ in self._translate_options],
                          state="readonly", width=12)
        cb.pack(side="left", padx=(10, 0))
        cb.bind("<<ComboboxSelected>>", self._on_translate_changed)
        _lbl(r2, "语音输入后自动翻译", font_size=9).pack(side="left", padx=(10, 0))

        r2b = tk.Frame(c_polish, bg=_C["surface"])
        r2b.pack(fill="x", pady=2)
        self._show_original_var = tk.BooleanVar(
            master=self._root, value=po.get("show_original", False))
        self._show_original_cb = tk.Checkbutton(
            r2b, text="翻译时同时输出原文", variable=self._show_original_var,
            bg=_C["surface"], fg=_C["text"], selectcolor=_C["entry"],
            activebackground=_C["surface"], activeforeground=_C["text"],
            font=("Segoe UI", 10), command=self._on_translate_changed,
        )
        self._show_original_cb.pack(side="left", padx=(20, 0))

        self._build_polish_options_card(polish_api_tab)

        # ---- 快捷键 ----
        _section_title(operation_shortcut_tab, "快捷键与启动", "控制录音触发方式和桌面启动行为。")
        c_shortcut = _card(operation_shortcut_tab)
        c_shortcut.pack(fill="x", pady=(0, 12))

        r0 = tk.Frame(c_shortcut, bg=_C["surface2"], padx=12, pady=10)
        r0.pack(fill="x", pady=(0, 10))
        tk.Label(
            r0,
            text="快捷键",
            bg=_C["surface2"],
            fg=_C["text2"],
            font=("Segoe UI Semibold", 9),
            width=10,
            anchor="w",
        ).pack(side="left")
        self._hotkey_var = tk.StringVar(master=self._root, value=hk.get("combination", "ctrl+shift+space"))
        self._hotkey_display = tk.Label(
            r0, textvariable=self._hotkey_var,
            bg=_C["entry"], fg=_C["accent"], font=("Consolas", 12, "bold"),
            width=16, anchor="center", padx=8, pady=3,
        )
        self._hotkey_display.pack(side="left", padx=(10, 0))
        self._record_btn = _btn(r0, "录制", self._start_hotkey_recording, w=5)
        self._record_btn.pack(side="left", padx=(8, 0))
        self._is_recording_hotkey = False
        self._recording_modifiers = set()

        if get_autostart_supported():
            r3 = tk.Frame(c_shortcut, bg=_C["surface"])
            r3.pack(fill="x", pady=4)
            self._autostart_var = tk.BooleanVar(master=self._root, value=check_autostart())
            tk.Checkbutton(
                r3, text="开机自启动", variable=self._autostart_var,
                bg=_C["surface"], fg=_C["text"], selectcolor=_C["entry"],
                activebackground=_C["surface"], activeforeground=_C["text"],
                font=("Segoe UI", 10),
            ).pack(side="left")
        else:
            self._autostart_var = None

        # ---- 历史 ----
        self._build_history_records_tab(history_records_tab)

        # ---- 按钮 ----
        bb = tk.Frame(
            m,
            bg=_C["surface"],
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=_C["border"],
        )
        bb.pack(fill="x", pady=(14, 0))
        tk.Label(
            bb,
            text="设置修改后点击保存立即生效",
            bg=_C["surface"],
            fg=_C["text2"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="left")
        _btn(bb, "取消", self._on_close, w=10).pack(side="right", padx=(8, 0))
        _btn(bb, "保存", self._on_save_click, accent=True, w=10).pack(side="right")
        self._select_settings_page(getattr(self, "_current_settings_page", self._initial_page), scroll=False)

    def _select_settings_page(self, key, scroll=True):
        """切换左侧主类目。"""
        if key not in self._settings_pages:
            key = "transcribe"
        self._current_settings_page = key

        for page_key, page in self._settings_pages.items():
            page.pack_forget()
            btn = self._settings_nav_buttons.get(page_key)
            if not btn:
                continue
            if page_key == key:
                btn.config(bg=_C["accent_soft"], fg=_C["accent"], activebackground=_C["btn_h"])
            else:
                btn.config(bg=_C["rail"], fg=_C["text2"], activebackground=_C["btn_h"])

        self._settings_pages[key].pack(fill="x", expand=True)
        tab_key = self._initial_tab if key == self._initial_page and self._initial_tab else None
        tab_key = tab_key or self._settings_default_tabs.get(key)
        self._select_settings_tab(key, tab_key, reset_scroll=scroll)
        self._root.update_idletasks()

    def _select_settings_tab(self, page_key, tab_key, reset_scroll=True):
        """切换右侧横向 tab。"""
        frames = self._settings_tab_frames.get(page_key, {})
        if not frames:
            return
        if tab_key not in frames:
            tab_key = next(iter(frames))
        self._current_settings_tab = (page_key, tab_key)

        for key, frame in frames.items():
            frame.pack_forget()
            btn = self._settings_tab_buttons.get(page_key, {}).get(key)
            if not btn:
                continue
            if key == tab_key:
                btn.config(bg=_C["accent"], fg="#0F1217", activebackground="#B7E6FF")
            else:
                btn.config(bg=_C["surface2"], fg=_C["text2"], activebackground=_C["btn_h"])

        frames[tab_key].pack(fill="x", expand=True)
        if reset_scroll and hasattr(self, "_settings_canvas"):
            self._settings_canvas.yview_moveto(0)

    def _on_settings_scroll_frame_configure(self, event=None):
        if hasattr(self, "_settings_canvas"):
            self._settings_canvas.configure(scrollregion=self._settings_canvas.bbox("all"))

    def _on_settings_canvas_configure(self, event):
        if hasattr(self, "_settings_canvas_window"):
            self._settings_canvas.itemconfigure(self._settings_canvas_window, width=event.width)

    def _bind_settings_mousewheel(self, event=None):
        self._root.bind_all("<MouseWheel>", self._on_settings_mousewheel)
        self._root.bind_all("<Button-4>", self._on_settings_mousewheel)
        self._root.bind_all("<Button-5>", self._on_settings_mousewheel)

    def _unbind_settings_mousewheel(self, event=None):
        self._root.unbind_all("<MouseWheel>")
        self._root.unbind_all("<Button-4>")
        self._root.unbind_all("<Button-5>")

    def _on_settings_mousewheel(self, event):
        if not hasattr(self, "_settings_canvas"):
            return
        if getattr(event, "num", None) == 4:
            delta = -3
        elif getattr(event, "num", None) == 5:
            delta = 3
        else:
            delta = -1 * int(event.delta / 120)
        self._settings_canvas.yview_scroll(delta, "units")

    def _scroll_to_settings_page(self, key):
        page = self._settings_pages.get(key)
        if not page or not hasattr(self, "_settings_canvas"):
            return
        self._root.update_idletasks()
        bbox = self._settings_canvas.bbox("all")
        if not bbox:
            return
        total_height = max(1, bbox[3] - bbox[1])
        y = page.winfo_y()
        self._settings_canvas.yview_moveto(max(0, min(y / total_height, 1)))

    # ==================== 润色 API ====================

    def _build_llm_profiles(self):
        """读取当前润色 profile，并收敛为一个简化的默认配置。"""
        from src.config import get_llm_profiles

        az = self._config.get("azure", {})
        po = self._config.get("polish", {})
        profiles = get_llm_profiles(self._config)
        if profiles:
            selected = po.get("profile", "default")
            profile = profiles.get(selected) or next(iter(profiles.values()), {})
            return {"default": dict(profile or {})}
        return {"default": _default_llm_profile(_infer_provider_from_endpoint(az.get("endpoint", "")), az)}

    def _build_llm_profile_card(self, card):
        """构建简化后的润色 LLM 设置。"""
        po = self._config.get("polish", {})
        selected = po.get("profile", "default")
        if selected not in self._llm_profiles:
            selected = next(iter(self._llm_profiles), "default")
        self._current_llm_profile = selected

        self._llm_profile_var = tk.StringVar(master=self._root, value=selected)
        self._llm_provider_var = tk.StringVar(master=self._root, value="auto")
        self._llm_base_url_var = tk.StringVar(master=self._root)
        self._llm_key_var = tk.StringVar(master=self._root)
        self._llm_model_var = tk.StringVar(master=self._root)
        self._llm_api_version_var = tk.StringVar(master=self._root, value="")
        self._llm_validate_status_var = tk.StringVar(master=self._root, value="")

        head = tk.Frame(card, bg=_C["surface2"], padx=12, pady=10)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(
            head,
            text="连接状态",
            bg=_C["surface2"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(side="left")
        self._llm_provider_label = tk.Label(
            head,
            text="未验证",
            bg=_C["accent_soft"], fg=_C["accent"],
            font=("Segoe UI Semibold", 8), anchor="center",
            padx=8, pady=3,
        )
        self._llm_provider_label.pack(side="right")

        fields = tk.Frame(card, bg=_C["surface"])
        fields.pack(fill="x")

        def add_field(label, var, kind="entry", hint=None):
            row = tk.Frame(fields, bg=_C["surface"])
            row.pack(fill="x", pady=(0, 10))
            tk.Label(
                row,
                text=label,
                bg=_C["surface"],
                fg=_C["text2"],
                font=("Segoe UI Semibold", 9),
                width=10,
                anchor="w",
            ).pack(side="left")
            if kind == "model":
                widget = ttk.Combobox(row, textvariable=var, values=[], width=42)
                self._llm_model_combo = widget
            else:
                show = "●" if kind == "secret" else ""
                widget = _entry(row, var=var, w=46, show=show)
                if kind == "secret":
                    self._llm_key_entry = widget
                    self._show_llm_key = False
            widget.pack(side="left", fill="x", expand=True, padx=(10, 0))
            if kind == "secret":
                self._llm_key_toggle_btn = _btn(row, "显示", self._toggle_llm_key, w=5)
                self._llm_key_toggle_btn.pack(side="left", padx=(6, 0))
            if hint:
                tk.Label(
                    row,
                    text=hint,
                    bg=_C["surface"],
                    fg=_C["muted"],
                    font=("Segoe UI", 8),
                    anchor="w",
                ).pack(side="left", padx=(8, 0))

        add_field("Endpoint", self._llm_base_url_var)
        add_field("API Key", self._llm_key_var, "secret")
        add_field("模型", self._llm_model_var, "model")

        hint = tk.Label(
            card,
            text="验证会依次尝试 OpenAI-compatible、Azure OpenAI 和 Anthropic，并把可用类型写回配置。",
            bg=_C["surface"],
            fg=_C["text2"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        hint.pack(fill="x", pady=(0, 10))

        action_row = tk.Frame(card, bg=_C["surface"])
        action_row.pack(fill="x")
        self._llm_validate_btn = _btn(action_row, "验证并识别", self._validate_llm_profile_endpoint, w=12)
        self._llm_validate_btn.pack(side="left")
        self._llm_models_btn = _btn(action_row, "获取模型", self._fetch_llm_models, w=9)
        self._llm_models_btn.pack(side="left", padx=(8, 0))
        tk.Label(
            action_row,
            textvariable=self._llm_validate_status_var,
            bg=_C["surface"], fg=_C["text2"],
            font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", padx=(12, 0), fill="x", expand=True)
        self._load_llm_profile(selected)

    def _validate_llm_profile_endpoint(self):
        """后台验证当前润色 profile 是否可调用。"""
        try:
            self._validate_current_llm_profile()
        except Exception as e:
            self._msg("error", "验证失败", str(e))
            return

        endpoint = self._llm_base_url_var.get().strip()
        api_key = self._llm_key_var.get().strip()
        model = self._llm_model_var.get().strip()
        self._set_llm_validate_state(True, "正在自动识别 API 类型...")

        def _worker():
            try:
                from src.llm_clients import detect_llm_profile

                profile, response, _errors = detect_llm_profile(endpoint, api_key, model)
                preview = response.replace("\n", " ")[:80]
                self._root.after(
                    0,
                    lambda: self._on_llm_validate_done(
                        True,
                        f"润色 API 验证成功。类型：{_provider_label(profile.get('provider'))}。返回：{preview}",
                        profile,
                    ),
                )
            except Exception as e:
                self._root.after(
                    0,
                    lambda err=e: self._on_llm_validate_done(False, str(err), None),
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _set_llm_validate_state(self, running, status):
        """更新 LLM 验证按钮和状态文字。"""
        self._llm_validate_status_var.set(status)
        self._llm_validate_btn.config(state=("disabled" if running else "normal"))
        self._llm_models_btn.config(state=("disabled" if running else "normal"))

    def _on_llm_validate_done(self, ok, message, profile=None):
        """显示 LLM profile 验证结果。"""
        self._set_llm_validate_state(False, "验证成功" if ok else "验证失败")
        if ok:
            if profile:
                self._apply_detected_llm_profile(profile)
            self._msg("info", "验证成功", message)
        else:
            self._msg("error", "验证失败", message)

    def _fetch_llm_models(self):
        """后台尝试获取 endpoint 上可用模型列表。"""
        endpoint = self._llm_base_url_var.get().strip()
        api_key = self._llm_key_var.get().strip()
        if not endpoint:
            self._msg("error", "获取失败", "Endpoint 不能为空")
            return
        if not api_key:
            self._msg("error", "获取失败", "API Key 不能为空")
            return

        self._set_llm_validate_state(True, "正在获取模型列表...")

        def _worker():
            try:
                from src.llm_clients import list_llm_models

                models, errors = list_llm_models(endpoint, api_key)
                self._root.after(0, lambda: self._on_llm_models_done(models, errors))
            except Exception as e:
                self._root.after(0, lambda err=e: self._on_llm_models_done([], [str(err)]))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_llm_models_done(self, models, errors):
        self._set_llm_validate_state(False, f"获取到 {len(models)} 个模型" if models else "未获取到模型")
        if models:
            current = self._llm_model_var.get().strip()
            self._llm_model_combo.config(values=models)
            if not current:
                self._llm_model_var.set(models[0])
            self._msg("info", "模型列表", f"已获取 {len(models)} 个模型/部署。")
        else:
            detail = "\n".join(errors[:6]) if errors else "该 endpoint 没有暴露模型列表接口。"
            self._msg("warning", "未获取到模型", detail)

    def _load_llm_profile(self, name):
        """把 profile 字段加载到 UI。"""
        profile = self._llm_profiles.get(name, {})
        provider = profile.get("provider") or _infer_provider_from_endpoint(
            profile.get("endpoint") or profile.get("base_url", "")
        )
        self._llm_provider_var.set(provider)
        self._llm_base_url_var.set(profile.get("base_url") or profile.get("endpoint", ""))
        self._llm_key_var.set(profile.get("api_key", ""))
        self._llm_model_var.set(profile.get("model") or profile.get("deployment", ""))
        self._llm_api_version_var.set(profile.get("api_version", ""))
        self._llm_validate_status_var.set("")
        self._update_llm_provider_label()

    def _save_current_llm_profile(self, name=None):
        """把当前 UI 字段写回内存中的 profile。"""
        name = name or self._llm_profile_var.get()
        if not name:
            return
        endpoint = self._llm_base_url_var.get().strip()
        model = self._llm_model_var.get().strip()
        provider = self._llm_provider_var.get() or _infer_provider_from_endpoint(endpoint)
        if provider == "auto":
            provider = _infer_provider_from_endpoint(endpoint)
        profile = {
            "provider": provider,
            "endpoint": endpoint,
            "api_key": self._llm_key_var.get().strip(),
            "model": model,
        }
        api_version = self._llm_api_version_var.get().strip()
        if api_version:
            profile["api_version"] = api_version
        self._llm_profiles[name] = profile
        self._update_llm_provider_label()

    def _apply_detected_llm_profile(self, profile):
        name = self._llm_profile_var.get()
        profile = dict(profile)
        simplified = {
            "provider": profile.get("provider", "openai_compatible"),
            "endpoint": profile.get("endpoint") or profile.get("base_url", ""),
            "api_key": self._llm_key_var.get().strip(),
            "model": profile.get("model") or profile.get("deployment", ""),
        }
        if profile.get("api_version"):
            simplified["api_version"] = profile["api_version"]
        self._llm_profiles[name] = simplified
        self._llm_provider_var.set(profile.get("provider", "openai_compatible"))
        self._llm_api_version_var.set(profile.get("api_version", ""))
        self._llm_base_url_var.set(simplified["endpoint"])
        self._llm_model_var.set(simplified["model"])
        self._update_llm_provider_label()

    def _update_llm_provider_label(self):
        if hasattr(self, "_llm_provider_label"):
            provider = self._llm_provider_var.get() or "auto"
            if provider == "auto":
                self._llm_provider_label.config(
                    text="未验证",
                    bg=_C["surface"],
                    fg=_C["text2"],
                )
            else:
                self._llm_provider_label.config(
                    text=f"已识别：{_provider_label(provider)}",
                    bg=_C["accent_soft"],
                    fg=_C["accent"],
                )

    def _toggle_llm_key(self):
        self._show_llm_key = not self._show_llm_key
        self._llm_key_entry.config(show="" if self._show_llm_key else "●")
        if hasattr(self, "_llm_key_toggle_btn"):
            self._llm_key_toggle_btn.config(text="隐藏" if self._show_llm_key else "显示")

    # ==================== 历史记录 ====================

    def _build_history_records_tab(self, parent):
        hist = self._config.get("history", {})

        _section_title(parent, "历史记录", "最近的最终输出保存在本机，可快速复制。")
        card = _card(parent)
        card.pack(fill="x", pady=(0, 12))

        policy = tk.Frame(card, bg=_C["surface2"], padx=12, pady=10)
        policy.pack(fill="x", pady=(0, 12))
        self._history_enabled_var = tk.BooleanVar(
            master=self._root,
            value=hist.get("enabled", True),
        )
        tk.Checkbutton(
            policy, text="保存历史记录", variable=self._history_enabled_var,
            bg=_C["surface2"], fg=_C["text"], selectcolor=_C["entry"],
            activebackground=_C["surface2"], activeforeground=_C["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        tk.Label(
            policy, text="最多保留", bg=_C["surface2"], fg=_C["text2"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(18, 6))
        self._history_max_entries_var = tk.StringVar(
            master=self._root,
            value=str(hist.get("max_entries", 100)),
        )
        _entry(policy, var=self._history_max_entries_var, w=6).pack(side="left")
        tk.Label(
            policy, text="条", bg=_C["surface2"], fg=_C["text2"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(6, 0))
        _btn(policy, "清空历史", self._clear_history, w=8).pack(side="right")

        top = tk.Frame(card, bg=_C["surface"])
        top.pack(fill="x", pady=(0, 10))
        self._history_summary_var = tk.StringVar(master=self._root, value="")
        tk.Label(
            top,
            textvariable=self._history_summary_var,
            bg=_C["surface"], fg=_C["text2"],
            font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", fill="x", expand=True)
        _btn(top, "刷新", self._refresh_history_records, w=6).pack(side="right")

        self._history_records_frame = tk.Frame(card, bg=_C["surface"])
        self._history_records_frame.pack(fill="x")
        self._refresh_history_records()

    def _get_history_entries(self):
        if self._on_get_history_entries:
            return self._on_get_history_entries() or []
        return self._status_info.get("history_entries", []) or []

    def _refresh_history_records(self):
        if not hasattr(self, "_history_records_frame"):
            return
        for child in self._history_records_frame.winfo_children():
            child.destroy()

        entries = self._get_history_entries()
        self._history_summary_var.set(f"共 {len(entries)} 条历史记录")
        if not entries:
            empty = tk.Frame(
                self._history_records_frame,
                bg=_C["surface2"],
                padx=14,
                pady=14,
                highlightthickness=1,
                highlightbackground=_C["border"],
            )
            empty.pack(fill="x", pady=(4, 0))
            tk.Label(
                empty,
                text="暂无历史记录",
                bg=_C["surface2"], fg=_C["text"],
                font=("Segoe UI Semibold", 10),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                empty,
                text="完成一次语音输入后，这里会显示最近结果。",
                bg=_C["surface2"], fg=_C["text2"], font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x", pady=(4, 0))
            return

        for index, entry in enumerate(entries[:50], start=1):
            row = tk.Frame(
                self._history_records_frame,
                bg=_C["surface2"],
                padx=12,
                pady=10,
                highlightthickness=1,
                highlightbackground=_C["border"],
            )
            row.pack(fill="x", pady=(0, 8))

            meta = entry.get("metadata", {}) or {}
            profile = meta.get("polish_profile") or "未润色"
            duration = float(entry.get("duration") or 0)
            created_at = _format_history_time(entry.get("created_at", ""))
            header = tk.Frame(row, bg=_C["surface2"])
            header.pack(fill="x")
            tk.Label(
                header,
                text=f"{index:02d}",
                bg=_C["accent_soft"],
                fg=_C["accent"],
                font=("Segoe UI Semibold", 8),
                padx=7,
                pady=2,
            ).pack(side="left", padx=(0, 8))
            tk.Label(
                header,
                text=f"{created_at} · {profile} · {duration:.1f}s",
                bg=_C["surface2"], fg=_C["text2"], font=("Segoe UI", 9),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            _btn(
                header,
                "复制",
                lambda text=entry.get("final_text", ""): self._copy_history_text(text),
                w=5,
            ).pack(side="right")

            tk.Label(
                row,
                text=_short_text(entry.get("final_text", "")),
                bg=_C["surface2"], fg=_C["text"], font=("Segoe UI", 10),
                anchor="w", justify="left", wraplength=620,
            ).pack(fill="x", pady=(6, 0))

            raw_text = entry.get("raw_text", "")
            if raw_text and raw_text.strip() != (entry.get("final_text", "") or "").strip():
                tk.Label(
                    row,
                    text=f"原文：{_short_text(raw_text, 180)}",
                    bg=_C["surface2"], fg=_C["text2"], font=("Segoe UI", 9),
                    anchor="w", justify="left", wraplength=620,
                ).pack(fill="x", pady=(6, 0))

    def _copy_history_text(self, text):
        if not text:
            return
        try:
            import pyperclip

            pyperclip.copy(text)
            self._history_summary_var.set("已复制到剪贴板")
        except Exception as e:
            self._history_summary_var.set(f"复制失败：{e}")

    def _clear_history(self):
        if not self._on_clear_history:
            self._msg("warning", "无法清空", "当前没有可用的历史记录服务。")
            return
        try:
            ok = self._on_clear_history()
        except Exception as e:
            self._msg("error", "清空失败", str(e))
            return
        if ok:
            self._refresh_history_records()
            if hasattr(self, "_history_summary_var"):
                self._history_summary_var.set("历史记录已清空")
        else:
            self._msg("error", "清空失败", "无法删除历史记录文件。")

    def _build_polish_options_card(self, parent):
        """构建默认隐藏的润色高级提示词设置。"""
        po = self._config.get("polish", {})

        # 识别语言不再作为常规设置项展示；留空交给模型自动判断。
        self._language_var = tk.StringVar(master=self._root, value=po.get("language", ""))

        _section_title(parent, "高级提示词", "默认使用内置语音后处理提示词。")
        card = _card(parent)
        card.pack(fill="x", pady=(0, 12))

        from src.polisher import build_prompt

        saved = po.get("system_prompt", "") or ""
        tl_code = po.get("translate_to", "")
        show_orig = po.get("show_original", False)
        self._prompt_base = saved
        self._prompt_text = None
        self._prompt_expanded = False

        top = tk.Frame(card, bg=_C["surface"])
        top.pack(fill="x")
        tk.Label(
            top,
            text="提示词",
            bg=_C["surface"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(side="left")
        state = "已自定义" if saved.strip() else "默认"
        _pill(top, state, fg=_C["accent"] if saved.strip() else _C["text2"],
              bg=_C["accent_soft"] if saved.strip() else _C["surface2"]).pack(side="left", padx=(10, 0))
        self._prompt_toggle_btn = _btn(top, "展开", self._toggle_prompt_editor, w=6)
        self._prompt_toggle_btn.pack(side="right")

        _lbl(
            card,
            "大多数情况下不需要修改；改错会让润色变得啰嗦或偏题。",
            font_size=9,
        ).pack(fill="x", pady=(8, 0))

        self._prompt_advanced_frame = tk.Frame(card, bg=_C["surface"])

        display = build_prompt(saved, tl_code, show_orig)
        self._prompt_text = tk.Text(
            self._prompt_advanced_frame, width=38, height=6, wrap=tk.WORD,
            bg=_C["entry"], fg=_C["text"], insertbackground=_C["accent"],
            selectbackground=_C["accent"], font=("Consolas", 9),
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=_C["border"], highlightcolor=_C["accent"],
        )
        self._prompt_text.pack(fill="x")
        self._prompt_text.insert("1.0", display)
        _lbl(self._prompt_advanced_frame, "留空=使用默认提示词", font_size=9).pack(fill="x", pady=(4, 0))

    def _toggle_prompt_editor(self):
        """展开/收起高级 prompt 编辑区。"""
        if self._prompt_expanded:
            self._prompt_advanced_frame.pack_forget()
            self._prompt_toggle_btn.config(text="展开")
            self._prompt_expanded = False
            return
        self._prompt_advanced_frame.pack(fill="x", pady=(10, 0))
        self._prompt_toggle_btn.config(text="收起")
        self._prompt_expanded = True

    # ==================== 转写引擎 ====================

    def _build_stt_card(self, parent):
        """构建「转写引擎」设置卡片。"""
        from src.model_manager import MODEL_REGISTRY, is_model_ready

        stt = self._config.get("stt", {})
        rc = self._config.get("recording", {})
        cur_model = stt.get("model_type", "sense_voice")
        self._num_threads_value = _coerce_positive_int(stt.get("num_threads"), _default_num_threads())
        self._sample_rate_value = _coerce_positive_int(rc.get("sample_rate"), 16000)
        self._channels_value = _coerce_positive_int(rc.get("channels"), 1)
        self._max_duration_value = _coerce_positive_int(rc.get("max_duration"), 60)

        _section_title(parent, "转写引擎", "固定使用本地模型，云端 API 只用于可选润色。")
        card = _card(parent)
        card.pack(fill="x", pady=(0, 12))

        self._stt_backend_var = tk.StringVar(master=self._root, value="local")

        top_note = tk.Frame(card, bg=_C["surface2"], padx=12, pady=9)
        top_note.pack(fill="x", pady=(0, 12))
        tk.Label(
            top_note,
            text="本地转写",
            bg=_C["surface2"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(side="left")
        _pill(top_note, "无在线转录", fg=_C["green"], bg=_C["accent_soft"]).pack(side="right")

        # 模型选择 + 状态
        self._stt_model_var = tk.StringVar(master=self._root, value=cur_model)
        self._model_status_labels = {}
        self._model_action_btns = {}

        for model_name, model_info in MODEL_REGISTRY.items():
            row = tk.Frame(
                card,
                bg=_C["surface2"],
                padx=12,
                pady=9,
                highlightthickness=1,
                highlightbackground=_C["border"],
            )
            row.pack(fill="x", pady=(0, 8))
            main = tk.Frame(row, bg=_C["surface2"])
            main.pack(fill="x")
            left = tk.Frame(main, bg=_C["surface2"])
            left.pack(side="left", fill="x", expand=True)
            right = tk.Frame(main, bg=_C["surface2"])
            right.pack(side="right")

            tk.Radiobutton(
                left, text=model_info["display_name"],
                variable=self._stt_model_var, value=model_name,
                bg=_C["surface2"], fg=_C["text"], selectcolor=_C["entry"],
                activebackground=_C["surface2"], activeforeground=_C["text"],
                font=("Segoe UI Semibold", 10),
                command=self._on_stt_model_changed,
            ).pack(anchor="w")
            desc = model_info.get("description", "")
            if model_info.get("streaming", False):
                desc += "；选择后自动启用实时转写"
            tk.Label(
                left,
                text=desc,
                bg=_C["surface2"],
                fg=_C["text2"],
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x", padx=(22, 0), pady=(2, 0))

            # 状态标签 + 操作按钮
            ready = is_model_ready(model_name)
            if ready:
                status_lbl = tk.Label(
                    right, text="已就绪", bg=_C["accent_soft"], fg=_C["green"],
                    font=("Segoe UI Semibold", 8), padx=8, pady=3,
                )
                status_lbl.pack(side="right", padx=(8, 0))
                # 删除按钮
                del_btn = _btn(right, "删除", lambda mn=model_name: self._delete_model(mn), w=4)
                del_btn.pack(side="right", padx=(4, 0))
                self._model_action_btns[model_name] = del_btn
            else:
                size_mb = model_info["download_size_mb"]
                status_lbl = tk.Label(
                    right, text=f"{size_mb}MB", bg=_C["surface"], fg=_C["text2"],
                    font=("Segoe UI Semibold", 8), padx=8, pady=3,
                )
                status_lbl.pack(side="right", padx=(8, 0))
                # 下载按钮
                dl_btn = _btn(right, "下载", lambda mn=model_name: self._download_model(mn), w=4)
                dl_btn.pack(side="right", padx=(4, 0))
                self._model_action_btns[model_name] = dl_btn

            self._model_status_labels[model_name] = status_lbl

    def _on_stt_model_changed(self):
        """STT 模型单选按钮切换回调。"""
        return

    def _download_model(self, model_name):
        """启动模型下载流程，显示进度对话框。"""
        from src.model_manager import download_model, get_model_info

        info = get_model_info(model_name)
        if not info:
            self._msg("error", "错误", f"未知模型: {model_name}")
            return

        # 创建进度对话框
        dlg = tk.Toplevel(self._root)
        dlg.title(f"下载 {info['display_name']}")
        dlg.configure(bg=_C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self._root)
        dlg.grab_set()
        self._set_window_icon(dlg)

        f = tk.Frame(dlg, bg=_C["bg"], padx=30, pady=20)
        f.pack()

        tk.Label(f, text="下载模型", bg=_C["bg"], fg=_C["accent"],
                 font=("Segoe UI Semibold", 13)).pack(pady=(0, 8))
        status_label = tk.Label(
            f, text="正在准备下载...", bg=_C["bg"], fg=_C["text"],
            font=("Segoe UI", 10), wraplength=300,
        )
        status_label.pack(pady=(0, 8))

        # 使用 ttk Progressbar
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Download.Horizontal.TProgressbar",
            troughcolor=_C["entry"],
            background=_C["accent"],
            thickness=20,
        )
        progress_bar = ttk.Progressbar(
            f, length=300, mode="determinate",
            style="Download.Horizontal.TProgressbar",
        )
        progress_bar.pack(pady=(0, 12))

        cancel_btn = _btn(f, "取消", lambda: dlg.destroy(), w=10)
        cancel_btn.pack()

        # 居中于父窗口
        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")

        # 进度回调（从下载线程调用，需要用 after 更新 UI）
        def on_progress(percent, status_text):
            try:
                dlg.after(0, lambda: _update_progress(percent, status_text))
            except Exception:
                pass

        def _update_progress(percent, status_text):
            try:
                progress_bar["value"] = percent
                status_label.config(text=status_text)
            except Exception:
                pass

        def on_complete(success):
            try:
                dlg.after(0, lambda: _on_download_done(success))
            except Exception:
                pass

        def _on_download_done(success):
            try:
                dlg.destroy()
            except Exception:
                pass
            if success:
                self._refresh_model_status(model_name)
                self._msg("info", "下载完成", f"{info['display_name']} 已就绪！")
            else:
                self._msg("error", "下载失败", "请检查网络连接后重试。")

        def on_error(error_msg):
            try:
                dlg.after(0, lambda: _on_download_error(error_msg))
            except Exception:
                pass

        def _on_download_error(error_msg):
            try:
                dlg.destroy()
            except Exception:
                pass
            self._msg("error", "下载出错", error_msg)

        # 启动下载
        download_model(
            model_name,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )

    def _delete_model(self, model_name):
        """删除已下载的模型。"""
        from src.model_manager import delete_model, get_model_info

        info = get_model_info(model_name)
        display = info["display_name"] if info else model_name

        # 确认对话框
        dlg = tk.Toplevel(self._root)
        dlg.title("确认删除")
        dlg.configure(bg=_C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self._root)
        dlg.grab_set()
        self._set_window_icon(dlg)

        f = tk.Frame(dlg, bg=_C["bg"], padx=30, pady=20)
        f.pack()

        tk.Label(
            f, text="确认删除模型？", bg=_C["bg"], fg=_C["yellow"],
            font=("Segoe UI Semibold", 13),
        ).pack()
        tk.Label(
            f, text=f"将删除 {display} 的所有文件。\n如需使用本地转写需重新下载。",
            bg=_C["bg"], fg=_C["text"], font=("Segoe UI", 10),
            wraplength=280, justify="center",
        ).pack(pady=(8, 16))

        btn_frame = tk.Frame(f, bg=_C["bg"])
        btn_frame.pack()

        def _do_delete():
            dlg.destroy()
            if delete_model(model_name):
                self._refresh_model_status(model_name)
                self._msg("info", "删除完成", f"{display} 已删除。")
            else:
                self._msg("error", "删除失败", "请关闭可能占用模型文件的程序后重试。")

        _btn(btn_frame, "取消", lambda: dlg.destroy(), w=8).pack(side="left", padx=(0, 8))
        _btn(btn_frame, "删除", _do_delete, accent=True, w=8).pack(side="left")

        # 居中于父窗口
        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")

        dlg.wait_window()

    def _refresh_model_status(self, model_name):
        """刷新指定模型的状态显示（下载完成/删除后调用）。"""
        from src.model_manager import is_model_ready, MODEL_REGISTRY

        ready = is_model_ready(model_name)
        info = MODEL_REGISTRY.get(model_name, {})

        # 更新状态标签
        if model_name in self._model_status_labels:
            lbl = self._model_status_labels[model_name]
            if ready:
                lbl.config(text="已就绪", bg=_C["accent_soft"], fg=_C["green"])
            else:
                size_mb = info.get("download_size_mb", "?")
                lbl.config(text=f"{size_mb}MB", bg=_C["surface"], fg=_C["text2"])

        # 更新操作按钮
        if model_name in self._model_action_btns:
            old_btn = self._model_action_btns[model_name]
            parent = old_btn.master
            old_btn.destroy()

            if ready:
                new_btn = _btn(parent, "删除", lambda mn=model_name: self._delete_model(mn), w=4)
            else:
                new_btn = _btn(parent, "下载", lambda mn=model_name: self._download_model(mn), w=4)
            new_btn.pack(side="right", padx=(4, 0))
            self._model_action_btns[model_name] = new_btn

    # ==================== 翻译联动 ====================

    def _on_translate_changed(self, event=None):
        from src.polisher import build_prompt
        code = ""
        for lb, cd in self._translate_options:
            if lb == self._translate_var.get():
                code = cd
                break
        show_orig = self._show_original_var.get()
        cur = self._prompt_text.get("1.0", "end-1c").strip()
        base = self._strip_translate_suffix(cur)
        self._prompt_text.delete("1.0", "end")
        self._prompt_text.insert("1.0", build_prompt(base, code, show_orig))

    @staticmethod
    def _strip_translate_suffix(p):
        """去掉 prompt 中由 build_prompt() 动态追加的所有指令（翻译指令 + 语言规则）。"""
        import re
        # 新格式：开头的 CRITICAL 语言规则（无翻译模式 build_prompt 在最前面插入的）
        p = re.sub(r"^CRITICAL:.*?Never translate\.\n\n", "", p, flags=re.DOTALL).strip()
        # 新格式：末尾的翻译规则
        p = re.sub(r"\n\n翻译规则：.+", "", p, flags=re.DOTALL).strip()
        # 新格式：末尾的语言规则（无翻译模式的旧版尾部追加格式）
        p = re.sub(r"\n\n语言规则：.+", "", p, flags=re.DOTALL).strip()
        p = re.sub(r"\n\nIMPORTANT: Do NOT translate\..+", "", p, flags=re.DOTALL).strip()
        p = re.sub(r"\n\nCRITICAL RULE: Output language.+", "", p, flags=re.DOTALL).strip()
        # 旧格式兼容
        p = re.sub(r"\n\n=== 翻译指令.+", "", p, flags=re.DOTALL).strip()
        p = re.sub(r"\n\n重要指令：完成润色后.+", "", p, flags=re.DOTALL).strip()
        p = re.sub(r"\n\n最后，将润色后的文字翻译为.+", "", p, flags=re.DOTALL).strip()
        return p

    # ==================== 快捷键录制 ====================

    def _start_hotkey_recording(self):
        self._is_recording_hotkey = True
        self._recording_modifiers = set()
        self._hotkey_var.set("按下快捷键...")
        self._hotkey_display.config(fg=_C["red"])
        self._record_btn.config(text="取消", command=self._cancel_hotkey_recording)
        self._root.bind("<KeyPress>", self._on_kp)
        self._root.bind("<KeyRelease>", self._on_kr)
        self._root.focus_force()

    def _cancel_hotkey_recording(self):
        self._stop_hotkey_recording()
        self._hotkey_var.set(self._config.get("hotkey", {}).get("combination", "ctrl+shift+space"))

    def _stop_hotkey_recording(self):
        self._is_recording_hotkey = False
        self._recording_modifiers = set()
        self._hotkey_display.config(fg=_C["accent"])
        self._root.unbind("<KeyPress>")
        self._root.unbind("<KeyRelease>")
        self._record_btn.config(text="录制", command=self._start_hotkey_recording)

    def _on_kp(self, event):
        if not self._is_recording_hotkey:
            return "break"
        ks = event.keysym
        if ks in _KEYSYM_MOD:
            self._recording_modifiers.add(_KEYSYM_MOD[ks])
            self._hotkey_var.set("+".join(m for m in _MOD_ORDER if m in self._recording_modifiers) + "+...")
            return "break"
        if ks == "Escape" and not self._recording_modifiers:
            self._cancel_hotkey_recording()
            return "break"
        trigger = _KEYSYM_KEY.get(ks, ks.lower() if len(ks) == 1 else None)
        if trigger:
            parts = [m for m in _MOD_ORDER if m in self._recording_modifiers] + [trigger]
            combo = "+".join(parts)
            self._hotkey_var.set(combo)
            self._stop_hotkey_recording()
            if combo.lower() in _RESERVED:
                self._msg("warning", "快捷键冲突", f"「{combo}」是常用系统快捷键，可能冲突。")
        return "break"

    def _on_kr(self, event):
        if not self._is_recording_hotkey:
            return "break"
        ks = event.keysym
        if ks in _KEYSYM_MOD:
            mod = _KEYSYM_MOD[ks]
            if len(self._recording_modifiers) > 1:
                self._recording_modifiers.discard(mod)
                self._hotkey_var.set("+".join(m for m in _MOD_ORDER if m in self._recording_modifiers) + "+...")
        return "break"

    # ==================== 保存 ====================

    def _on_save_click(self):
        try:
            cfg = self._collect_config()
        except ValueError as e:
            self._msg("error", "输入错误", str(e))
            return
        if self._autostart_var is not None:
            try:
                set_autostart(self._autostart_var.get())
            except Exception as e:
                log.warning("设置开机自启失败: %s", e)
        if self._on_save:
            try:
                ok, msg = self._on_save(cfg)
                if ok:
                    self._msg("info", "保存成功", "配置已保存并立即生效。")
                    self._on_close()
                else:
                    self._msg("error", "保存失败", msg or "未知错误")
            except Exception as e:
                self._msg("error", "保存失败", f"出错: {e}")
        else:
            self._on_close()

    def _collect_config(self):
        """收集 UI 中所有设置值，组装为完整配置字典。"""
        import copy

        # 转写固定为本地模型。
        stt_backend = "local"
        polish_enabled = self._polish_var.get()

        self._save_current_llm_profile()

        if polish_enabled:
            self._validate_current_llm_profile()

        try:
            history_max_entries = int(self._history_max_entries_var.get().strip())
            assert history_max_entries > 0
        except Exception:
            raise ValueError("历史记录保留条数必须是正整数")

        c = copy.deepcopy(self._config)
        c.pop("azure", None)

        # STT 配置
        from src.model_manager import MODEL_REGISTRY

        model_type = self._stt_model_var.get()
        model_info = MODEL_REGISTRY.get(model_type, {})
        s = c.setdefault("stt", {})
        s["backend"] = stt_backend
        s["model_type"] = model_type
        s["num_threads"] = self._num_threads_value
        s["streaming"] = bool(model_info.get("streaming", False))
        r = c.setdefault("recording", {})
        r["sample_rate"] = self._sample_rate_value
        r["channels"] = self._channels_value
        r["max_duration"] = self._max_duration_value
        c.setdefault("hotkey", {})["combination"] = self._hotkey_var.get().strip()
        p = c.setdefault("polish", {})
        p["enabled"] = polish_enabled
        p["profile"] = self._llm_profile_var.get()
        p["language"] = self._language_var.get().strip()
        p["system_prompt"] = self._strip_translate_suffix(self._prompt_text.get("1.0", "end-1c").strip())
        # 如果用户没有修改过提示词（内容等于默认值），保存为空字符串
        # 这样下次启动时 build_prompt() 会用代码中最新的默认 prompt
        from src.polisher import POLISH_SYSTEM_PROMPT
        if p["system_prompt"].strip() == POLISH_SYSTEM_PROMPT.strip():
            p["system_prompt"] = ""
        tl = ""
        for lb, cd in self._translate_options:
            if lb == self._translate_var.get():
                tl = cd
                break
        p["translate_to"] = tl
        p["show_original"] = self._show_original_var.get()
        c["llm_profiles"] = self._llm_profiles
        h = c.setdefault("history", {})
        h["enabled"] = self._history_enabled_var.get()
        h["max_entries"] = history_max_entries
        return c

    def _validate_current_llm_profile(self):
        """验证当前润色 API 的必要字段。"""
        if not self._llm_base_url_var.get().strip():
            raise ValueError("润色 API Endpoint 不能为空")
        if not self._llm_key_var.get().strip():
            raise ValueError("润色 API Key 不能为空")
        if not self._llm_model_var.get().strip():
            raise ValueError("润色模型名称不能为空")

    # ==================== 窗口管理 ====================

    @staticmethod
    def _set_window_icon(window):
        """为窗口设置程序图标。"""
        try:
            from src.paths import get_resource_dir, get_project_root
            import os
            # 优先用 ico，回退用 png
            for base in [get_resource_dir(), get_project_root()]:
                ico = base / "assets" / "icon.ico"
                if ico.exists():
                    window.iconbitmap(str(ico))
                    return
                png = base / "assets" / "icon.png"
                if png.exists():
                    from PIL import ImageTk, Image
                    icon_img = ImageTk.PhotoImage(Image.open(str(png)))
                    window.iconphoto(True, icon_img)
                    window._icon_ref = icon_img  # 防 GC
                    return
        except Exception:
            pass

    def _msg(self, msg_type, title, message):
        """
        显示自定义深色弹窗，居中于设置窗口。

        Args:
            msg_type: "info" / "error" / "warning"
            title: 标题
            message: 内容
        """
        icons = {"info": "完成", "error": "错误", "warning": "注意"}
        colors = {"info": _C["accent"], "error": _C["red"], "warning": _C["yellow"]}
        icon = icons.get(msg_type, "提示")
        clr = colors.get(msg_type, _C["accent"])

        dlg = tk.Toplevel(self._root)
        dlg.title(title)
        dlg.configure(bg=_C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self._root)
        dlg.grab_set()
        self._set_window_icon(dlg)

        f = tk.Frame(dlg, bg=_C["bg"], padx=30, pady=20)
        f.pack()

        tk.Label(f, text=icon, bg=_C["bg"], fg=clr,
                 font=("Segoe UI Semibold", 11)).pack(pady=(0, 8))
        tk.Label(f, text=title, bg=_C["bg"], fg=clr, font=("Segoe UI Semibold", 13)).pack()
        tk.Label(f, text=message, bg=_C["bg"], fg=_C["text"], font=("Segoe UI", 10),
                 wraplength=280, justify="center").pack(pady=(8, 16))
        _btn(f, "确定", lambda: dlg.destroy(), accent=True, w=12).pack()

        # 居中于父窗口
        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")

        dlg.wait_window()

    def _toggle_theme(self):
        """切换深色/浅色主题，重建窗口内容。"""
        global _current_theme, _C
        _current_theme = "light" if _current_theme == "dark" else "dark"
        _C.update(_THEMES[_current_theme])

        x, y = self._root.winfo_x(), self._root.winfo_y()
        selected_page = getattr(self, "_current_settings_page", "transcribe")
        selected_tab = getattr(self, "_current_settings_tab", (selected_page, None))[1]

        for widget in self._root.winfo_children():
            widget.destroy()

        self._root.configure(bg=_C["bg"])
        self._configure_fonts()
        self._configure_ttk_style()
        self._initial_page = selected_page
        self._initial_tab = selected_tab
        m = tk.Frame(self._root, bg=_C["bg"], padx=22, pady=18)
        m.pack(fill="both", expand=True)
        self._rebuild_content(m)

        self._select_settings_page(selected_page)

        self._root.update_idletasks()
        sw, sh = self._root.winfo_screenwidth(), self._root.winfo_screenheight()
        w = min(max(self._root.winfo_width(), 960), max(860, sw - 80))
        h = min(max(self._root.winfo_height(), 720), max(620, sh - 100))
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    def _center_window(self):
        """首次打开时居中。"""
        self._root.update_idletasks()
        sw, sh = self._root.winfo_screenwidth(), self._root.winfo_screenheight()
        w = min(max(self._root.winfo_reqwidth(), 960), max(860, sw - 80))
        h = min(max(self._root.winfo_reqheight(), 720), max(620, sh - 100))
        self._root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _on_close(self):
        global _settings_open
        _settings_open = False
        try:
            self._root.destroy()
        except Exception:
            pass

    def run(self):
        try:
            self._root.mainloop()
        except Exception as e:
            log.error("设置窗口异常: %s", e)
        finally:
            global _settings_open
            _settings_open = False


def open_settings(
    current_config,
    status_info=None,
    on_save=None,
    on_clear_history=None,
    on_get_history_entries=None,
    initial_page="transcribe",
    initial_tab=None,
):
    """在新线程中打开设置窗口。"""
    global _settings_open
    if _settings_open:
        return

    def _run():
        try:
            SettingsWindow(
                current_config,
                status_info,
                on_save,
                on_clear_history,
                on_get_history_entries,
                initial_page,
                initial_tab,
            ).run()
        except Exception as e:
            log.error("打开设置窗口失败: %s", e)
            global _settings_open
            _settings_open = False

    threading.Thread(target=_run, daemon=True).start()
