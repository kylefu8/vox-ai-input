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
from src.i18n import (
    language_label,
    language_options,
    normalize_ui_language,
    t,
)
from src.logger import setup_logger

log = setup_logger(__name__)

_settings_open = False

# ==================== 主题定义 ====================
_THEMES = {
    "dark": {
        "bg": "#1B1E24",
        "rail": "#20252D",
        "surface": "#262B34",
        "surface2": "#303743",
        "border": "#4A5564",
        "text": "#F6F8FA",
        "text2": "#CBD5E1",
        "muted": "#A8B3C2",
        "accent": "#7DD3F0",
        "accent_soft": "#263F4A",
        "green": "#8BE0A8",
        "red": "#FF8EA0",
        "yellow": "#F7D47A",
        "orange": "#F2AE6D",
        "btn": "#343C49",
        "btn_h": "#3F4A59",
        "entry": "#222832",
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


def _normalize_theme(theme):
    theme = str(theme or "dark").strip().lower()
    return theme if theme in _THEMES else "dark"


def _set_current_theme(theme):
    global _current_theme, _C
    _current_theme = _normalize_theme(theme)
    _C.clear()
    _C.update(_THEMES[_current_theme])


_BASE_TRANSLATE_OPTIONS = [
    ("不翻译", ""), ("简体中文", "zh"), ("英语", "en"),
    ("日语", "ja"), ("韩语", "ko"), ("法语", "fr"),
    ("德语", "de"), ("西班牙语", "es"), ("俄语", "ru"),
    ("繁体中文", "zh-TW"),
]

_ICONS = {
    "check": "check",
    "cancel": "cancel",
    "clear": "clear",
    "copy": "copy",
    "delete": "delete",
    "download": "download",
    "expand": "expand",
    "collapse": "collapse",
    "fetch": "fetch",
    "info": "info",
    "record": "record",
    "refresh": "refresh",
    "save": "save",
    "theme_dark": "theme_dark",
    "theme_light": "theme_light",
}

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
    "alt+z", "win+space", "windows+space", "ctrl+space",
}
_HOTKEY_WARNINGS = {
    "alt+z": "Alt+Z 常被显卡覆盖层或录屏工具占用，建议更换。",
    "win+space": "Win+Space 通常用于切换输入法，建议更换。",
    "windows+space": "Win+Space 通常用于切换输入法，建议更换。",
    "ctrl+space": "Ctrl+Space 常被输入法或编辑器占用，建议更换。",
}

_PROFILE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _normalize_llm_profile_name(name):
    """Return a safe profile id for config.yaml."""
    normalized = _PROFILE_NAME_RE.sub("-", (name or "").strip()).strip("-_.").lower()
    if not normalized:
        raise ValueError("Profile 名称不能为空")
    return normalized


def _normalize_hotkey_combo(combo):
    """Normalize a hotkey string for conflict checks."""
    return "+".join(part.strip().lower() for part in str(combo or "").split("+") if part.strip())


def _hotkey_warning_text(combo):
    """Return a user-facing warning for risky hotkeys, or an empty string."""
    normalized = _normalize_hotkey_combo(combo)
    if normalized in _HOTKEY_WARNINGS:
        return _HOTKEY_WARNINGS[normalized]
    if normalized in _RESERVED:
        return "「{combo}」是常用系统快捷键，可能冲突。".format(combo=combo)
    return ""


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
    if provider == "openai_responses":
        return {
            "provider": "openai_responses",
            "endpoint": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-5.4-mini",
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
        "openai_compatible": "OpenAI Chat Completions",
        "openai_responses": "OpenAI Responses",
        "anthropic": "Anthropic Messages",
    }.get(provider or "auto", provider or "未验证")


_LLM_PROVIDER_OPTIONS = [
    ("自动识别", "auto"),
    ("OpenAI Chat Completions", "openai_compatible"),
    ("OpenAI Responses", "openai_responses"),
    ("Anthropic Messages", "anthropic"),
]


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


def _text_units(text):
    """Approximate Tk character width for mixed Chinese/English button text."""
    units = 0
    for ch in str(text or ""):
        if ch in ("\ufe0e", "\ufe0f", "\u200d"):
            continue
        units += 2 if ord(ch) > 127 else 1
    return units


def _button_width(text, minimum=8):
    """Return a button width that does not clip longer English labels."""
    return max(int(minimum or 0), _text_units(text) + 1)


def _icon_text(icon_key, label):
    """Return an icon + label string for command buttons."""
    return label


def _draw_button_icon(icon_key, size=18):
    """Draw a small colorful bitmap icon so Tk does not depend on emoji fonts."""
    from PIL import Image, ImageDraw

    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def xy(values):
        return tuple(int(v * scale) for v in values)

    def line(points, fill, width=2):
        d.line([xy(p) for p in points], fill=fill, width=width * scale, joint="curve")

    def ellipse(box, fill, outline=None, width=1):
        d.ellipse(xy(box), fill=fill, outline=outline, width=width * scale)

    def rect(box, fill, outline=None, width=1):
        d.rounded_rectangle(xy(box), radius=3 * scale, fill=fill, outline=outline, width=width * scale)

    def poly(points, fill):
        d.polygon([xy(p) for p in points], fill=fill)

    blue = "#38BDF8"
    blue2 = "#0EA5E9"
    green = "#34D399"
    red = "#FB7185"
    yellow = "#FBBF24"
    purple = "#A78BFA"
    white = "#FFFFFF"
    ink = "#0F172A"
    slate = "#94A3B8"

    if icon_key == "check":
        ellipse((1.5, 1.5, 16.5, 16.5), green)
        line(((5, 9), (8, 12), (13.5, 6)), white, 2)
    elif icon_key == "cancel":
        ellipse((1.5, 1.5, 16.5, 16.5), red)
        line(((6, 6), (12, 12)), white, 2)
        line(((12, 6), (6, 12)), white, 2)
    elif icon_key == "save":
        rect((3, 2.5, 15, 15.5), blue2)
        rect((5, 4, 12, 7), white)
        rect((5, 10, 13, 15), "#DBEAFE")
        rect((11, 4, 13, 7), "#075985")
    elif icon_key == "record":
        rect((6, 2.5, 12, 11), red)
        line(((4.5, 8), (4.5, 10), (6.5, 12), (11.5, 12), (13.5, 10), (13.5, 8)), red, 2)
        line(((9, 12), (9, 15)), red, 2)
        line(((6.5, 15), (11.5, 15)), red, 2)
    elif icon_key in ("download", "fetch"):
        ellipse((1.5, 1.5, 16.5, 16.5), blue)
        line(((9, 4), (9, 11)), white, 2)
        poly(((5.5, 9), (9, 13), (12.5, 9)), white)
        line(((5, 14), (13, 14)), white, 2)
    elif icon_key == "delete":
        rect((5, 6, 13, 15.5), red)
        rect((4, 4, 14, 6), "#FDA4AF")
        line(((7, 8), (7, 13.5)), white, 1)
        line(((11, 8), (11, 13.5)), white, 1)
        line(((7, 3), (11, 3)), red, 2)
    elif icon_key == "copy":
        rect((6, 3, 14.5, 12.5), "#BFDBFE", outline=blue2)
        rect((3.5, 5.5, 12, 15), white, outline=blue2)
        line(((6, 9), (10, 9)), blue2, 1)
        line(((6, 12), (10, 12)), blue2, 1)
    elif icon_key == "refresh":
        ellipse((2.5, 2.5, 15.5, 15.5), None, outline=blue, width=2)
        poly(((12, 2.5), (15.5, 2.5), (15.5, 6)), blue)
        poly(((6, 15.5), (2.5, 15.5), (2.5, 12)), blue)
    elif icon_key == "clear":
        rect((3, 10, 15, 15), yellow)
        line(((5, 10), (13, 10)), "#92400E", 1)
        line(((10, 3), (6, 10)), "#92400E", 2)
        line(((10, 3), (14, 8)), "#92400E", 2)
    elif icon_key == "expand":
        poly(((4, 6), (14, 6), (9, 12.5)), blue)
    elif icon_key == "collapse":
        poly(((4, 12), (14, 12), (9, 5.5)), blue)
    elif icon_key == "info":
        ellipse((2, 2, 16, 16), blue2)
        ellipse((8, 4, 10, 6), white)
        rect((7.8, 7.2, 10.2, 13.5), white)
    elif icon_key == "theme_light":
        ellipse((5, 5, 13, 13), yellow)
        for p1, p2 in (((9, 1), (9, 3.5)), ((9, 14.5), (9, 17)),
                       ((1, 9), (3.5, 9)), ((14.5, 9), (17, 9)),
                       ((3, 3), (4.8, 4.8)), ((13.2, 13.2), (15, 15)),
                       ((15, 3), (13.2, 4.8)), ((4.8, 13.2), (3, 15))):
            line((p1, p2), yellow, 1)
    elif icon_key == "theme_dark":
        ellipse((3, 2, 16, 16), purple)
        ellipse((8, 1.5, 18, 13), _C["btn"])
    else:
        ellipse((2, 2, 16, 16), slate)
        line(((6, 9), (12, 9)), white, 2)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def _button_icon_image(widget, icon_key, size=18):
    """Return a cached PhotoImage for a button icon."""
    try:
        from PIL import ImageTk
    except Exception:
        return None
    root = widget.winfo_toplevel()
    cache = getattr(root, "_button_icon_cache", None)
    if cache is None:
        cache = {}
        root._button_icon_cache = cache
    key = (_current_theme, icon_key, size)
    if key not in cache:
        cache[key] = ImageTk.PhotoImage(_draw_button_icon(icon_key, size), master=root)
    return cache[key]


def _prewarm_button_icons(root, size=18):
    """Generate common button icons before the window is shown."""
    try:
        from PIL import ImageTk
    except Exception:
        return
    cache = getattr(root, "_button_icon_cache", None)
    if cache is None:
        cache = {}
        root._button_icon_cache = cache
    for icon_key in _ICONS:
        key = (_current_theme, icon_key, size)
        if key not in cache:
            cache[key] = ImageTk.PhotoImage(_draw_button_icon(icon_key, size), master=root)


def _set_button_icon(button, icon_key, text=None, icon_only=False):
    """Apply a colored image icon to an existing button."""
    img = _button_icon_image(button, icon_key)
    if not img:
        if text is not None:
            button.config(text=text)
        return
    if icon_only:
        button.config(text="", image=img, width=30, height=28, compound="center")
    else:
        # With image+text, Tk may treat width as pixels on some Windows/Tk
        # builds. Let the button size itself naturally to avoid clipping.
        button.config(text=text or "", image=img, compound="left", width=0)
    button._icon_key = icon_key
    button._icon_only = icon_only
    button._icon_ref = img


def _theme_color_map(old_palette):
    """Map colors from the previous palette to the current palette."""
    color_map = {}
    for key, old_value in old_palette.items():
        new_value = _C.get(key)
        if isinstance(old_value, str) and isinstance(new_value, str):
            color_map[old_value.lower()] = new_value
    return color_map


def _map_theme_color(value, color_map):
    if isinstance(value, str):
        return color_map.get(value.lower(), value)
    return value


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


def _tooltip(widget, text, delay=450):
    """Attach a small theme-aware tooltip to a widget."""
    state = {"after_id": None, "tip": None}

    def _get_text():
        return text() if callable(text) else str(text or "")

    def _hide():
        if state["after_id"]:
            try:
                widget.after_cancel(state["after_id"])
            except Exception:
                pass
            state["after_id"] = None
        if state["tip"]:
            try:
                state["tip"].destroy()
            except Exception:
                pass
            state["tip"] = None

    def _show():
        _hide()
        tip_text = _get_text()
        if not tip_text:
            return
        try:
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() + 8
            tip = tk.Toplevel(widget)
            tip.withdraw()
            tip.overrideredirect(True)
            tip.configure(bg=_C["surface2"])
            tk.Label(
                tip,
                text=tip_text,
                bg=_C["surface2"],
                fg=_C["text"],
                font=("Segoe UI", 9),
                padx=8,
                pady=4,
            ).pack()
            tip.update_idletasks()
            tip.geometry(f"+{max(0, x - tip.winfo_reqwidth() // 2)}+{y}")
            tip.deiconify()
            state["tip"] = tip
        except Exception:
            _hide()

    def _schedule(_event=None):
        _hide()
        state["after_id"] = widget.after(delay, _show)

    widget.bind("<Enter>", _schedule, add="+")
    widget.bind("<Leave>", lambda _event=None: _hide(), add="+")
    widget.bind("<ButtonPress>", lambda _event=None: _hide(), add="+")
    widget.bind("<Destroy>", lambda _event=None: _hide(), add="+")
    return widget


def _btn(parent, text, cmd=None, accent=False, w=8, tooltip=None, icon_key=None, **kw):
    """风格化按钮。"""
    bg = _C["accent"] if accent else _C["btn"]
    fg = "#0F1217" if accent else _C["text"]
    hbg = "#B7E6FF" if accent else _C["btn_h"]
    padx = kw.pop("padx", 12)
    pady = kw.pop("pady", 6)
    font = kw.pop("font", ("Segoe UI Semibold", 9))
    b = tk.Button(
        parent, text=text, command=cmd, bg=bg, fg=fg,
        activebackground=hbg, activeforeground=fg,
        relief="flat", bd=0, padx=padx, pady=pady,
        font=font, cursor="hand2",
        width=_button_width(text, w),
        **kw,
    )
    b.bind("<Enter>", lambda e: b.config(bg=hbg))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    if icon_key:
        _set_button_icon(b, icon_key, text=text)
    if tooltip:
        _tooltip(b, tooltip)
    return b


def _icon_btn(parent, icon_key, cmd=None, tooltip=None, accent=False, w=3, **kw):
    """Compact icon button with tooltip."""
    b = _btn(
        parent,
        "",
        cmd,
        accent=accent,
        w=w,
        tooltip=tooltip,
        padx=8,
        pady=5,
        font=kw.pop("font", ("Segoe UI Semibold", 10)),
        **kw,
    )
    _set_button_icon(b, icon_key, icon_only=True)
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
        ui = current_config.get("ui", {}) or {}
        self._ui_language = normalize_ui_language(ui.get("language", "zh-CN"))
        _set_current_theme(ui.get("theme", _current_theme))
        self._translate_options = self._make_translate_options()
        self._llm_profiles = self._build_llm_profiles()
        self._build_ui()

    def _t(self, text, **kwargs):
        return t(text, self._ui_language, **kwargs)

    def _make_translate_options(self):
        return [(self._t(label), code) for label, code in _BASE_TRANSLATE_OPTIONS]

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
        _prewarm_button_icons(self._root)

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

        # 右侧：界面语言、主题、信息入口
        right = tk.Frame(hdr, bg=_C["bg"])
        right.pack(side="right")

        controls = tk.Frame(right, bg=_C["bg"])
        controls.pack(anchor="e", pady=(0, 6))
        tk.Label(
            controls,
            text=self._t("界面"),
            bg=_C["bg"],
            fg=_C["text2"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 6))
        self._ui_language_options = language_options(self._ui_language)
        self._ui_language_var = tk.StringVar(
            master=self._root,
            value=language_label(self._ui_language, self._ui_language),
        )
        lang_combo = ttk.Combobox(
            controls,
            textvariable=self._ui_language_var,
            values=[label for label, _code in self._ui_language_options],
            state="readonly",
            width=14,
        )
        lang_combo.pack(side="left", padx=(0, 8))
        lang_combo.bind("<<ComboboxSelected>>", self._on_ui_language_changed)
        self._theme_btn = _icon_btn(
            controls,
            self._theme_icon_key(),
            self._toggle_theme,
            tooltip=self._theme_tooltip_text,
            w=3,
        )
        self._theme_btn.pack(side="left", padx=(0, 8))
        _icon_btn(
            controls,
            "info",
            self._show_about,
            tooltip=self._t("关于"),
            w=3,
        ).pack(side="left")

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
        self._history_records_loaded = False

        def add_page(key, title, subtitle):
            page = tk.Frame(self._settings_scroll_frame, bg=_C["bg"])
            header = tk.Frame(page, bg=_C["bg"])
            header.pack(fill="x", pady=(0, 12))
            tk.Label(
                header, text=title, bg=_C["bg"], fg=_C["text"],
                font=("Segoe UI Semibold", 15), anchor="w",
            ).pack(anchor="w")
            if subtitle:
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
            ("transcribe", self._t("转写"), self._t("本地模型"), self._t("本地离线转写模型设置")),
            ("polish", self._t("润色"), self._t("AI API"), self._t("润色、翻译和 LLM 配置")),
            ("operation", self._t("操作"), self._t("快捷键"), self._t("触发按键和启动行为")),
            ("data", self._t("数据"), self._t("历史记录"), self._t("历史浏览与复制")),
        ]

        tk.Label(
            sidebar,
            text=self._t("设置").upper(),
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

        transcribe_page, transcribe_tabs, transcribe_body = add_page(
            "transcribe", self._t("转写"), "")
        polish_page, polish_tabs, polish_body = add_page(
            "polish", self._t("润色"), "")
        operation_page, operation_tabs, operation_body = add_page(
            "operation", self._t("操作"), "")
        data_page, data_tabs, data_body = add_page(
            "data", self._t("数据"), "")

        transcribe_model_tab = add_tab("transcribe", transcribe_tabs, transcribe_body, "model", self._t("本地模型"))
        polish_api_tab = add_tab("polish", polish_tabs, polish_body, "api", self._t("连接"))
        operation_shortcut_tab = add_tab("operation", operation_tabs, operation_body, "shortcut", self._t("快捷键"))
        history_records_tab = add_tab("data", data_tabs, data_body, "records", self._t("历史"))

        # 每个主类目只保留一个页面时，隐藏横向 tab，避免重复导航。
        for tabbar in (transcribe_tabs, polish_tabs, operation_tabs, data_tabs):
            tabbar.pack_forget()

        # ---- 转写 ----
        self._build_stt_card(transcribe_model_tab)

        # ---- 润色 ----
        _section_title(polish_api_tab, self._t("润色 API"))
        c_llm = _card(polish_api_tab)
        c_llm.pack(fill="x", pady=(0, 12))
        self._build_llm_profile_card(c_llm)

        hk = self._config.get("hotkey", {})
        ui = self._config.get("ui", {}) or {}
        po = self._config.get("polish", {})

        _section_title(polish_api_tab, self._t("润色流程"))
        c_polish = _card(polish_api_tab)
        c_polish.pack(fill="x", pady=(0, 12))
        r1 = tk.Frame(c_polish, bg=_C["surface2"], padx=12, pady=8)
        r1.pack(fill="x", pady=4)
        self._polish_var = tk.BooleanVar(master=self._root, value=po.get("enabled", False))
        tk.Checkbutton(
            r1, text=self._t("启用 AI 润色"), variable=self._polish_var,
            bg=_C["surface2"], fg=_C["text"], selectcolor=_C["entry"],
            activebackground=_C["surface2"], activeforeground=_C["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        _pill(r1, self._t("可选"), fg=_C["text2"], bg=_C["surface"]).pack(side="right")

        r2 = tk.Frame(c_polish, bg=_C["surface"])
        r2.pack(fill="x", pady=(10, 4))
        tk.Label(r2, text=self._t("翻译"), bg=_C["surface"], fg=_C["text2"], font=("Segoe UI Semibold", 9),
                 width=10, anchor="w").pack(side="left")
        tl = po.get("translate_to", "")
        cur = self._t("不翻译")
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
        r2b = tk.Frame(c_polish, bg=_C["surface"])
        r2b.pack(fill="x", pady=2)
        self._show_original_var = tk.BooleanVar(
            master=self._root, value=po.get("show_original", False))
        self._show_original_cb = tk.Checkbutton(
            r2b, text=self._t("翻译时同时输出原文"), variable=self._show_original_var,
            bg=_C["surface"], fg=_C["text"], selectcolor=_C["entry"],
            activebackground=_C["surface"], activeforeground=_C["text"],
            font=("Segoe UI", 10), command=self._on_translate_changed,
        )
        self._show_original_cb.pack(side="left", padx=(20, 0))

        self._build_polish_tips(c_polish)
        self._build_polish_options_card(polish_api_tab)

        # ---- 快捷键 ----
        _section_title(operation_shortcut_tab, self._t("快捷键与启动"))
        c_shortcut = _card(operation_shortcut_tab)
        c_shortcut.pack(fill="x", pady=(0, 12))

        r0 = tk.Frame(c_shortcut, bg=_C["surface2"], padx=12, pady=10)
        r0.pack(fill="x", pady=(0, 10))
        tk.Label(
            r0,
            text=self._t("快捷键"),
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
        self._record_btn = _btn(
            r0,
            _icon_text("record", self._t("录制")),
            self._start_hotkey_recording,
            icon_key="record",
            w=5,
        )
        self._record_btn.pack(side="left", padx=(8, 0))
        self._is_recording_hotkey = False
        self._recording_modifiers = set()

        self._hotkey_hint_var = tk.StringVar(
            master=self._root,
            value=self._hotkey_hint_text(self._hotkey_var.get()),
        )
        self._hotkey_hint_label = tk.Label(
            c_shortcut,
            textvariable=self._hotkey_hint_var,
            bg=_C["surface"],
            fg=_C["yellow"] if _hotkey_warning_text(self._hotkey_var.get()) else _C["muted"],
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self._hotkey_hint_label.pack(fill="x", pady=(0, 12), padx=2)

        r_float = tk.Frame(c_shortcut, bg=_C["surface"])
        r_float.pack(fill="x", pady=(2, 4))
        floating_cfg = (ui.get("floating_control", {}) or {})
        self._floating_enabled_var = tk.BooleanVar(
            master=self._root,
            value=bool(floating_cfg.get("enabled", True)),
        )
        tk.Checkbutton(
            r_float,
            text=self._t("显示悬浮录音按钮"),
            variable=self._floating_enabled_var,
            bg=_C["surface"],
            fg=_C["text"],
            selectcolor=_C["entry"],
            activebackground=_C["surface"],
            activeforeground=_C["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        _pill(r_float, self._t("可拖动"), fg=_C["text2"], bg=_C["surface2"]).pack(side="right")
        tk.Label(
            c_shortcut,
            text=self._t("左键开始/停止，拖动可移动；右键录音中取消，否则打开设置。"),
            bg=_C["surface"],
            fg=_C["muted"],
            font=("Segoe UI", 9),
            anchor="w",
            wraplength=560,
        ).pack(fill="x", padx=2, pady=(0, 8))

        if get_autostart_supported():
            r3 = tk.Frame(c_shortcut, bg=_C["surface"])
            r3.pack(fill="x", pady=4)
            self._autostart_var = tk.BooleanVar(master=self._root, value=check_autostart())
            tk.Checkbutton(
                r3, text=self._t("开机自启动"), variable=self._autostart_var,
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
            text=self._t("保存后立即生效"),
            bg=_C["surface"],
            fg=_C["text2"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="left")
        _btn(bb, _icon_text("cancel", self._t("取消")), self._on_close, icon_key="cancel", w=10).pack(side="right", padx=(8, 0))
        _btn(bb, _icon_text("save", self._t("保存")), self._on_save_click, accent=True, icon_key="save", w=10).pack(side="right")
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
        if key == "data" and tab_key == "records":
            self._ensure_history_records_loaded()
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
        self._llm_provider_choice_var = tk.StringVar(master=self._root)
        self._llm_base_url_var = tk.StringVar(master=self._root)
        self._llm_key_var = tk.StringVar(master=self._root)
        self._llm_model_var = tk.StringVar(master=self._root)
        self._llm_api_version_var = tk.StringVar(master=self._root, value="")
        self._llm_validate_status_var = tk.StringVar(master=self._root, value="")
        self._llm_resolved_base_url = ""
        self._llm_resolved_endpoint_input = ""

        head = tk.Frame(card, bg=_C["surface2"], padx=12, pady=10)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(
            head,
            text=self._t("连接状态"),
            bg=_C["surface2"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(side="left")
        self._llm_provider_label = tk.Label(
            head,
            text=self._t("未验证"),
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
            if kind == "provider":
                self._llm_provider_options = [
                    (self._t(label), code) for label, code in _LLM_PROVIDER_OPTIONS
                ]
                widget = ttk.Combobox(
                    row,
                    textvariable=self._llm_provider_choice_var,
                    values=[label for label, _code in self._llm_provider_options],
                    state="readonly",
                    width=24,
                )
                widget.bind("<<ComboboxSelected>>", self._on_llm_provider_selected)
            elif kind == "model":
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
                self._llm_key_toggle_btn = _btn(
                    row,
                    self._t("显示"),
                    self._toggle_llm_key,
                    w=5,
                    tooltip=lambda: self._t("隐藏 API Key") if self._show_llm_key else self._t("显示 API Key"),
                )
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

        add_field(self._t("API 类型"), self._llm_provider_choice_var, "provider")
        add_field(self._t("Endpoint"), self._llm_base_url_var)
        add_field(self._t("API Key"), self._llm_key_var, "secret")
        add_field(self._t("模型"), self._llm_model_var, "model")

        action_row = tk.Frame(card, bg=_C["surface"])
        action_row.pack(fill="x")
        self._llm_models_btn = _btn(
            action_row,
            _icon_text("fetch", self._t("获取模型")),
            self._fetch_llm_models,
            icon_key="fetch",
            w=9,
        )
        self._llm_models_btn.pack(side="left")
        self._llm_validate_btn = _btn(
            action_row,
            _icon_text("check", self._t("验证并识别")),
            self._validate_llm_profile_endpoint,
            icon_key="check",
            w=12,
        )
        self._llm_validate_btn.pack(side="left", padx=(8, 0))
        tk.Label(
            action_row,
            textvariable=self._llm_validate_status_var,
            bg=_C["surface"], fg=_C["text2"],
            font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", padx=(12, 0), fill="x", expand=True)
        self._load_llm_profile(selected)

    def _llm_provider_choice_label(self, provider):
        provider = provider or "auto"
        for label, code in getattr(self, "_llm_provider_options", []):
            if code == provider:
                return label
        return _provider_label(provider)

    def _set_llm_provider_choice(self, provider):
        provider = provider or "auto"
        self._llm_provider_var.set(provider)
        if hasattr(self, "_llm_provider_choice_var"):
            self._llm_provider_choice_var.set(self._llm_provider_choice_label(provider))
        self._update_llm_provider_label()

    def _on_llm_provider_selected(self, event=None):
        selected = self._llm_provider_choice_var.get()
        for label, code in getattr(self, "_llm_provider_options", []):
            if label == selected:
                self._llm_provider_var.set(code)
                self._update_llm_provider_label()
                return

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
        provider = self._llm_provider_var.get() or "auto"
        self._set_llm_validate_state(
            True,
            self._t("正在自动识别 API 类型...") if provider == "auto" else self._t("正在验证 API 连接..."),
        )

        def _worker():
            try:
                from src.llm_clients import validate_llm_profile_for_provider

                profile, response, _errors = validate_llm_profile_for_provider(
                    provider,
                    endpoint,
                    api_key,
                    model,
                )
                preview = response.replace("\n", " ")[:80]
                self._root.after(
                    0,
                    lambda: self._on_llm_validate_done(
                        True,
                        self._t("润色 API 验证成功。类型：{provider}。返回：{preview}",
                                provider=_provider_label(profile.get("provider")),
                                preview=preview),
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
        self._set_llm_validate_state(False, self._t("验证成功") if ok else self._t("验证失败"))
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

        self._set_llm_validate_state(True, self._t("正在获取模型列表..."))

        def _worker():
            try:
                from src.llm_clients import list_llm_models_with_base_url

                models, errors, base_url = list_llm_models_with_base_url(endpoint, api_key)
                self._root.after(0, lambda: self._on_llm_models_done(models, errors, base_url))
            except Exception as e:
                self._root.after(0, lambda err=e: self._on_llm_models_done([], [str(err)], None))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_llm_models_done(self, models, errors, base_url=None):
        self._set_llm_validate_state(
            False,
            self._t("获取到 {count} 个模型", count=len(models)) if models else self._t("未获取到模型"),
        )
        if models:
            self._remember_resolved_base_url(base_url)
            current = self._llm_model_var.get().strip()
            self._llm_model_combo.config(values=models)
            if not current:
                self._llm_model_var.set(models[0])
            self._msg("info", "模型列表", self._t("已获取 {count} 个模型/部署。", count=len(models)))
        else:
            detail = "\n".join(errors[:6]) if errors else self._t("该 endpoint 没有暴露模型列表接口。")
            self._msg("warning", "未获取到模型", detail)

    def _load_llm_profile(self, name):
        """把 profile 字段加载到 UI。"""
        profile = self._llm_profiles.get(name, {})
        provider = profile.get("provider") or _infer_provider_from_endpoint(
            profile.get("endpoint") or profile.get("base_url", "")
        )
        self._set_llm_provider_choice(provider)
        endpoint = profile.get("endpoint") or profile.get("base_url", "")
        self._llm_base_url_var.set(endpoint)
        self._llm_key_var.set(profile.get("api_key", ""))
        self._llm_model_var.set(profile.get("model") or profile.get("deployment", ""))
        self._llm_api_version_var.set(profile.get("api_version", ""))
        self._remember_resolved_base_url(profile.get("base_url", ""), endpoint=endpoint)
        self._llm_validate_status_var.set("")

    def _save_current_llm_profile(self, name=None):
        """把当前 UI 字段写回内存中的 profile。"""
        name = name or self._llm_profile_var.get()
        if not name:
            return
        endpoint = self._llm_base_url_var.get().strip()
        model = self._llm_model_var.get().strip()
        provider = self._llm_provider_var.get() or "auto"
        profile = {
            "provider": provider,
            "endpoint": endpoint,
            "api_key": self._llm_key_var.get().strip(),
            "model": model,
        }
        base_url = self._matching_resolved_base_url(endpoint)
        if base_url and base_url != endpoint:
            profile["base_url"] = base_url
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
        if profile.get("base_url"):
            simplified["base_url"] = profile["base_url"]
        if profile.get("api_version"):
            simplified["api_version"] = profile["api_version"]
        self._llm_profiles[name] = simplified
        self._set_llm_provider_choice(profile.get("provider", "openai_compatible"))
        self._llm_api_version_var.set(profile.get("api_version", ""))
        self._llm_base_url_var.set(simplified["endpoint"])
        self._llm_model_var.set(simplified["model"])
        self._remember_resolved_base_url(simplified.get("base_url", ""))

    def _remember_resolved_base_url(self, base_url, endpoint=None):
        endpoint = endpoint if endpoint is not None else self._llm_base_url_var.get().strip()
        self._llm_resolved_base_url = (base_url or "").strip().rstrip("/")
        self._llm_resolved_endpoint_input = (endpoint or "").strip().rstrip("/")

    def _matching_resolved_base_url(self, endpoint):
        endpoint = (endpoint or "").strip().rstrip("/")
        if endpoint and endpoint == getattr(self, "_llm_resolved_endpoint_input", ""):
            return getattr(self, "_llm_resolved_base_url", "")
        return ""

    def _update_llm_provider_label(self):
        if hasattr(self, "_llm_provider_label"):
            provider = self._llm_provider_var.get() or "auto"
            if provider == "auto":
                self._llm_provider_label.config(
                    text=self._t("未验证"),
                    bg=_C["surface"],
                    fg=_C["text2"],
                )
            else:
                self._llm_provider_label.config(
                    text=self._t("已识别：{provider}", provider=_provider_label(provider)),
                    bg=_C["accent_soft"],
                    fg=_C["accent"],
                )

    def _toggle_llm_key(self):
        self._show_llm_key = not self._show_llm_key
        self._llm_key_entry.config(show="" if self._show_llm_key else "●")
        if hasattr(self, "_llm_key_toggle_btn"):
            self._llm_key_toggle_btn.config(text=self._t("隐藏") if self._show_llm_key else self._t("显示"))

    # ==================== 历史记录 ====================

    def _build_history_records_tab(self, parent):
        hist = self._config.get("history", {})

        _section_title(parent, self._t("历史记录"))
        card = _card(parent)
        card.pack(fill="x", pady=(0, 12))

        policy = tk.Frame(card, bg=_C["surface2"], padx=12, pady=10)
        policy.pack(fill="x", pady=(0, 12))
        self._history_enabled_var = tk.BooleanVar(
            master=self._root,
            value=hist.get("enabled", True),
        )
        tk.Checkbutton(
            policy, text=self._t("保存历史记录"), variable=self._history_enabled_var,
            bg=_C["surface2"], fg=_C["text"], selectcolor=_C["entry"],
            activebackground=_C["surface2"], activeforeground=_C["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        tk.Label(
            policy, text=self._t("最多保留"), bg=_C["surface2"], fg=_C["text2"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(18, 6))
        self._history_max_entries_var = tk.StringVar(
            master=self._root,
            value=str(hist.get("max_entries", 100)),
        )
        _entry(policy, var=self._history_max_entries_var, w=6).pack(side="left")
        tk.Label(
            policy, text=self._t("条"), bg=_C["surface2"], fg=_C["text2"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(6, 0))
        _icon_btn(
            policy,
            "clear",
            self._clear_history,
            tooltip=self._t("清空历史"),
        ).pack(side="right")

        top = tk.Frame(card, bg=_C["surface"])
        top.pack(fill="x", pady=(0, 10))
        self._history_summary_var = tk.StringVar(master=self._root, value="")
        tk.Label(
            top,
            textvariable=self._history_summary_var,
            bg=_C["surface"], fg=_C["text2"],
            font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", fill="x", expand=True)
        _icon_btn(
            top,
            "refresh",
            self._refresh_history_records,
            tooltip=self._t("刷新"),
        ).pack(side="right")

        self._history_records_frame = tk.Frame(card, bg=_C["surface"])
        self._history_records_frame.pack(fill="x")
        self._history_records_loaded = False

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
        self._history_records_loaded = True
        self._history_summary_var.set(self._t("共 {count} 条历史记录", count=len(entries)))
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
                text=self._t("暂无历史记录"),
                bg=_C["surface2"], fg=_C["text"],
                font=("Segoe UI Semibold", 10),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                empty,
                text=self._t("完成一次语音输入后，这里会显示最近结果。"),
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
            profile = meta.get("polish_profile") or self._t("未润色")
            if meta.get("polish_fallback"):
                profile = f"{profile} · {self._t('润色失败')}"
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
            _icon_btn(
                header,
                "copy",
                lambda text=entry.get("final_text", ""): self._copy_history_text(text),
                tooltip=self._t("复制"),
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
                    text=self._t("原文：{text}", text=_short_text(raw_text, 180)),
                    bg=_C["surface2"], fg=_C["text2"], font=("Segoe UI", 9),
                    anchor="w", justify="left", wraplength=620,
                ).pack(fill="x", pady=(6, 0))

    def _ensure_history_records_loaded(self):
        """Load history rows only when the user opens the history page."""
        if getattr(self, "_history_records_loaded", False):
            return
        if hasattr(self, "_history_records_frame"):
            self._refresh_history_records()

    def _copy_history_text(self, text):
        if not text:
            return
        try:
            import pyperclip

            pyperclip.copy(text)
            self._history_summary_var.set(self._t("已复制到剪贴板"))
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
                self._history_summary_var.set(self._t("历史记录已清空"))
        else:
            self._msg("error", "清空失败", "无法删除历史记录文件。")

    def _build_polish_options_card(self, parent):
        """构建默认隐藏的润色高级提示词设置。"""
        po = self._config.get("polish", {})

        # 识别语言不再作为常规设置项展示；留空交给模型自动判断。
        self._language_var = tk.StringVar(master=self._root, value=po.get("language", ""))

        _section_title(parent, self._t("高级提示词"))
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
            text=self._t("提示词"),
            bg=_C["surface"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(side="left")
        state = self._t("已自定义") if saved.strip() else self._t("默认")
        _pill(top, state, fg=_C["accent"] if saved.strip() else _C["text2"],
              bg=_C["accent_soft"] if saved.strip() else _C["surface2"]).pack(side="left", padx=(10, 0))
        self._prompt_toggle_btn = _icon_btn(
            top,
            "expand",
            self._toggle_prompt_editor,
            tooltip=lambda: self._t("收起") if self._prompt_expanded else self._t("展开"),
        )
        self._prompt_toggle_btn.pack(side="right")

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
        _lbl(self._prompt_advanced_frame, self._t("留空=使用默认提示词"), font_size=9).pack(fill="x", pady=(4, 0))

    def _build_polish_tips(self, parent):
        """Show compact examples for the built-in smart polish behavior."""
        box = tk.Frame(parent, bg=_C["surface2"], padx=12, pady=10)
        box.pack(fill="x", pady=(12, 0))
        tk.Label(
            box,
            text=self._t("语音小技巧"),
            bg=_C["surface2"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(fill="x")
        _lbl(
            box,
            self._t("可以直接说出小指令，默认润色会在不改变原意的前提下处理。"),
            font_size=9,
            bg=_C["surface2"],
        ).pack(fill="x", pady=(3, 8))
        for line in (
            "说“帮我总结成要点……”会输出要点。",
            "说“整理成待办……”会提取行动项。",
            "说“写成一段发给同事的话……”会整理成消息。",
            "包含“第一/第二/最后”等枚举时，会尽量整理成编号列表。",
            "endpoint、base_url、Responses API 等技术词会尽量保留。",
        ):
            tk.Label(
                box,
                text=self._t(line),
                bg=_C["surface2"],
                fg=_C["text2"],
                font=("Segoe UI", 9),
                anchor="w",
                justify="left",
                wraplength=520,
            ).pack(fill="x", pady=(0, 3))

    def _toggle_prompt_editor(self):
        """展开/收起高级 prompt 编辑区。"""
        if self._prompt_expanded:
            self._prompt_advanced_frame.pack_forget()
            _set_button_icon(self._prompt_toggle_btn, "expand", icon_only=True)
            self._prompt_expanded = False
            return
        self._prompt_advanced_frame.pack(fill="x", pady=(10, 0))
        _set_button_icon(self._prompt_toggle_btn, "collapse", icon_only=True)
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

        _section_title(parent, self._t("转写引擎"))
        card = _card(parent)
        card.pack(fill="x", pady=(0, 12))

        self._stt_backend_var = tk.StringVar(master=self._root, value="local")

        top_note = tk.Frame(card, bg=_C["surface2"], padx=12, pady=9)
        top_note.pack(fill="x", pady=(0, 12))
        tk.Label(
            top_note,
            text=self._t("本地转写"),
            bg=_C["surface2"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(side="left")
        _pill(top_note, self._t("无在线转录"), fg=_C["green"], bg=_C["accent_soft"]).pack(side="right")

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
                left, text=self._model_display_name(model_name, model_info),
                variable=self._stt_model_var, value=model_name,
                bg=_C["surface2"], fg=_C["text"], selectcolor=_C["entry"],
                activebackground=_C["surface2"], activeforeground=_C["text"],
                font=("Segoe UI Semibold", 10),
                command=self._on_stt_model_changed,
            ).pack(anchor="w")
            desc = self._model_description(model_name, model_info)
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
                    right, text=self._t("已就绪"), bg=_C["accent_soft"], fg=_C["green"],
                    font=("Segoe UI Semibold", 8), padx=8, pady=3,
                )
                status_lbl.pack(side="right", padx=(8, 0))
                # 删除按钮
                del_btn = _icon_btn(
                    right,
                    "delete",
                    lambda mn=model_name: self._delete_model(mn),
                    tooltip=self._t("删除"),
                )
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
                dl_btn = _icon_btn(
                    right,
                    "download",
                    lambda mn=model_name: self._download_model(mn),
                    tooltip=self._t("下载"),
                )
                dl_btn.pack(side="right", padx=(4, 0))
                self._model_action_btns[model_name] = dl_btn

            self._model_status_labels[model_name] = status_lbl

    def _model_display_name(self, model_name, model_info):
        if self._ui_language == "en":
            return {
                "sense_voice": "SenseVoice",
                "whisper_small": "Whisper Small",
                "paraformer_streaming": "Paraformer Streaming",
            }.get(model_name, model_info.get("display_name", model_name))
        return model_info.get("display_name", model_name)

    def _model_description(self, model_name, model_info):
        if self._ui_language == "en":
            return {
                "sense_voice": "Fast; best for Chinese",
                "whisper_small": "Broad multilingual support",
                "paraformer_streaming": "Real-time Chinese/English",
            }.get(model_name, model_info.get("description", ""))
        if model_name == "sense_voice":
            return "速度快，中文质量最佳"
        if model_name == "whisper_small":
            return "多语言通用，质量稳定"
        if model_name == "paraformer_streaming":
            return "中英实时转写，自动流式"
        return model_info.get("description", "")

    def _on_stt_model_changed(self):
        """STT 模型单选按钮切换回调。"""
        return

    def _download_model(self, model_name):
        """启动模型下载流程，显示进度对话框。"""
        from src.model_manager import download_model, get_model_info

        info = get_model_info(model_name)
        if not info:
            self._msg("error", "错误", self._t("未知模型: {model}", model=model_name))
            return

        # 创建进度对话框
        dlg = tk.Toplevel(self._root)
        dlg.withdraw()
        dlg.title(f"{self._t('下载')} {info['display_name']}")
        dlg.configure(bg=_C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self._root)
        dlg.grab_set()
        self._set_window_icon(dlg)

        f = tk.Frame(dlg, bg=_C["bg"], padx=30, pady=20)
        f.pack()

        tk.Label(f, text=self._t("下载模型"), bg=_C["bg"], fg=_C["accent"],
                 font=("Segoe UI Semibold", 13)).pack(pady=(0, 8))
        status_label = tk.Label(
            f, text=self._t("正在准备下载..."), bg=_C["bg"], fg=_C["text"],
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

        cancel_btn = _btn(f, self._t("取消"), lambda: dlg.destroy(), w=10)
        cancel_btn.pack()

        # 居中于父窗口
        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.deiconify()
        dlg.lift()
        dlg.focus_force()

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
                self._msg("info", "下载完成", self._t("{name} 已就绪！", name=info["display_name"]))
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
        dlg.withdraw()
        dlg.title(self._t("确认删除"))
        dlg.configure(bg=_C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self._root)
        dlg.grab_set()
        self._set_window_icon(dlg)

        f = tk.Frame(dlg, bg=_C["bg"], padx=30, pady=20)
        f.pack()

        tk.Label(
            f, text=self._t("确认删除模型？"), bg=_C["bg"], fg=_C["yellow"],
            font=("Segoe UI Semibold", 13),
        ).pack()
        tk.Label(
            f, text=self._t("将删除 {name} 的所有文件。\n如需使用本地转写需重新下载。", name=display),
            bg=_C["bg"], fg=_C["text"], font=("Segoe UI", 10),
            wraplength=280, justify="center",
        ).pack(pady=(8, 16))

        btn_frame = tk.Frame(f, bg=_C["bg"])
        btn_frame.pack()

        def _do_delete():
            dlg.destroy()
            if delete_model(model_name):
                self._refresh_model_status(model_name)
                self._msg("info", "删除完成", self._t("{name} 已删除。", name=display))
            else:
                self._msg("error", "删除失败", "请关闭可能占用模型文件的程序后重试。")

        _btn(btn_frame, self._t("取消"), lambda: dlg.destroy(), w=8).pack(side="left", padx=(0, 8))
        _btn(btn_frame, self._t("删除"), _do_delete, accent=True, w=8).pack(side="left")

        # 居中于父窗口
        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.deiconify()
        dlg.lift()
        dlg.focus_force()

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
                lbl.config(text=self._t("已就绪"), bg=_C["accent_soft"], fg=_C["green"])
            else:
                size_mb = info.get("download_size_mb", "?")
                lbl.config(text=f"{size_mb}MB", bg=_C["surface"], fg=_C["text2"])

        # 更新操作按钮
        if model_name in self._model_action_btns:
            old_btn = self._model_action_btns[model_name]
            parent = old_btn.master
            old_btn.destroy()

            if ready:
                new_btn = _icon_btn(
                    parent,
                    "delete",
                    lambda mn=model_name: self._delete_model(mn),
                    tooltip=self._t("删除"),
                )
            else:
                new_btn = _icon_btn(
                    parent,
                    "download",
                    lambda mn=model_name: self._download_model(mn),
                    tooltip=self._t("下载"),
                )
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

    def _hotkey_hint_text(self, combo):
        warning = _hotkey_warning_text(combo)
        if warning:
            return self._t(warning)
        return self._t("推荐：Ctrl+Shift+Space 或 Ctrl+Alt+Space。")

    def _refresh_hotkey_hint(self):
        if not hasattr(self, "_hotkey_hint_var"):
            return
        combo = self._hotkey_var.get()
        warning = _hotkey_warning_text(combo)
        self._hotkey_hint_var.set(self._hotkey_hint_text(combo))
        if hasattr(self, "_hotkey_hint_label"):
            self._hotkey_hint_label.config(fg=_C["yellow"] if warning else _C["muted"])

    def _start_hotkey_recording(self):
        self._is_recording_hotkey = True
        self._recording_modifiers = set()
        self._hotkey_var.set(self._t("按下快捷键..."))
        self._hotkey_display.config(fg=_C["red"])
        self._record_btn.config(text=_icon_text("cancel", self._t("取消")), command=self._cancel_hotkey_recording)
        _set_button_icon(self._record_btn, "cancel", text=self._t("取消"))
        self._root.bind("<KeyPress>", self._on_kp)
        self._root.bind("<KeyRelease>", self._on_kr)
        self._root.focus_force()

    def _cancel_hotkey_recording(self):
        self._stop_hotkey_recording()
        self._hotkey_var.set(self._config.get("hotkey", {}).get("combination", "ctrl+shift+space"))
        self._refresh_hotkey_hint()

    def _stop_hotkey_recording(self):
        self._is_recording_hotkey = False
        self._recording_modifiers = set()
        self._hotkey_display.config(fg=_C["accent"])
        self._root.unbind("<KeyPress>")
        self._root.unbind("<KeyRelease>")
        self._record_btn.config(text=_icon_text("record", self._t("录制")), command=self._start_hotkey_recording)
        _set_button_icon(self._record_btn, "record", text=self._t("录制"))

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
            self._refresh_hotkey_hint()
            warning = _hotkey_warning_text(combo)
            if warning:
                self._msg("warning", "快捷键冲突", self._t(warning))
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

    def _collect_config(self, validate_llm=True, validate_history=True):
        """收集 UI 中所有设置值，组装为完整配置字典。"""
        import copy

        # 转写固定为本地模型。
        stt_backend = "local"
        polish_enabled = self._polish_var.get()

        self._save_current_llm_profile()

        if polish_enabled and validate_llm:
            self._validate_current_llm_profile()

        try:
            history_max_entries = int(self._history_max_entries_var.get().strip())
            assert history_max_entries > 0
        except Exception:
            if validate_history:
                raise ValueError(self._t("历史记录保留条数必须是正整数"))
            history_max_entries = _coerce_positive_int(
                self._config.get("history", {}).get("max_entries"),
                100,
            )

        c = copy.deepcopy(self._config)
        c.pop("azure", None)
        ui = c.setdefault("ui", {})
        ui["language"] = self._ui_language
        ui["theme"] = _current_theme
        ui.setdefault("floating_control", {})["enabled"] = self._floating_enabled_var.get()

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
            raise ValueError(self._t("润色 API Endpoint 不能为空"))
        if not self._llm_key_var.get().strip():
            raise ValueError(self._t("润色 API Key 不能为空"))
        if not self._llm_model_var.get().strip():
            raise ValueError(self._t("润色模型名称不能为空"))

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
                    icon_img = ImageTk.PhotoImage(Image.open(str(png)), master=window)
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
        icon = self._t(icons.get(msg_type, "提示"))
        clr = colors.get(msg_type, _C["accent"])
        title = self._t(title)
        message = self._t(message)

        dlg = tk.Toplevel(self._root)
        dlg.withdraw()
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
        _btn(f, self._t("确定"), lambda: dlg.destroy(), accent=True, w=12).pack()

        # 居中于父窗口
        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.deiconify()
        dlg.lift()
        dlg.focus_force()

        dlg.wait_window()

    def _theme_icon_key(self):
        return "theme_light" if _current_theme == "dark" else "theme_dark"

    def _theme_tooltip_text(self):
        return self._t("切换到浅色") if _current_theme == "dark" else self._t("切换到深色")

    def _snapshot_config_for_rebuild(self):
        try:
            self._config = self._collect_config(validate_llm=False, validate_history=False)
        except Exception as e:
            log.debug("主题/语言重建前同步未保存表单失败: %s", e)

    def _iter_theme_widgets(self, widget):
        yield widget
        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            yield from self._iter_theme_widgets(child)

    def _retint_widget(self, widget, color_map):
        """Update theme colors on an existing Tk widget without rebuilding it."""
        option_names = (
            "bg", "background", "fg", "foreground",
            "activebackground", "activeforeground",
            "insertbackground", "selectbackground", "selectforeground",
            "highlightbackground", "highlightcolor", "selectcolor",
            "disabledforeground", "troughcolor",
        )
        updates = {}
        for option in option_names:
            try:
                current = widget.cget(option)
            except Exception:
                continue
            mapped = _map_theme_color(current, color_map)
            if mapped != current:
                updates[option] = mapped
        if updates:
            try:
                widget.configure(**updates)
            except Exception:
                pass

    def _apply_theme_to_existing_widgets(self, old_palette):
        """Apply the new palette in place so theme switching does not reopen the window."""
        color_map = _theme_color_map(old_palette)
        self._root.configure(bg=_C["bg"])
        self._configure_ttk_style()
        _prewarm_button_icons(self._root)

        for widget in self._iter_theme_widgets(self._root):
            self._retint_widget(widget, color_map)

        for widget in self._iter_theme_widgets(self._root):
            icon_key = getattr(widget, "_icon_key", None)
            if not icon_key:
                continue
            text = None if getattr(widget, "_icon_only", False) else widget.cget("text")
            _set_button_icon(widget, icon_key, text=text, icon_only=getattr(widget, "_icon_only", False))

        if hasattr(self, "_theme_btn"):
            _set_button_icon(self._theme_btn, self._theme_icon_key(), icon_only=True)

    def _rebuild_window_content(self, selected_page=None, selected_tab=None):
        selected_page = selected_page or getattr(self, "_current_settings_page", "transcribe")
        selected_tab = selected_tab or getattr(self, "_current_settings_tab", (selected_page, None))[1]
        x, y = self._root.winfo_x(), self._root.winfo_y()
        width, height = self._root.winfo_width(), self._root.winfo_height()
        was_visible = self._root.state() != "withdrawn"

        if was_visible:
            self._root.withdraw()

        for widget in self._root.winfo_children():
            widget.destroy()

        self._translate_options = self._make_translate_options()
        self._root.configure(bg=_C["bg"])
        self._configure_fonts()
        self._configure_ttk_style()
        _prewarm_button_icons(self._root)
        self._initial_page = selected_page
        self._initial_tab = selected_tab
        m = tk.Frame(self._root, bg=_C["bg"], padx=22, pady=18)
        m.pack(fill="both", expand=True)
        self._rebuild_content(m)
        self._root.geometry(f"{max(width, 860)}x{max(height, 620)}+{x}+{y}")
        self._root.update_idletasks()
        if was_visible:
            self._root.deiconify()

    def _on_ui_language_changed(self, event=None):
        selected = self._ui_language_var.get()
        for label, code in self._ui_language_options:
            if label == selected:
                self._snapshot_config_for_rebuild()
                self._ui_language = normalize_ui_language(code)
                self._rebuild_window_content()
                return

    def _show_about(self):
        from run import __version__
        import webbrowser

        dlg = tk.Toplevel(self._root)
        dlg.withdraw()
        dlg.title(self._t("关于 Vox AI Input"))
        dlg.configure(bg=_C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self._root)
        dlg.grab_set()
        self._set_window_icon(dlg)

        f = tk.Frame(dlg, bg=_C["bg"], padx=28, pady=24)
        f.pack(fill="both", expand=True)

        tk.Label(
            f,
            text="Vox AI Input",
            bg=_C["bg"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 18),
        ).pack(anchor="w")
        tk.Label(
            f,
            text=f"v{__version__}",
            bg=_C["bg"],
            fg=_C["accent"],
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", pady=(2, 12))
        tk.Label(
            f,
            text=self._t("本地优先的语音输入工具。"),
            bg=_C["bg"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        for line in (
            "本地模型负责转写，AI API 只在启用润色或翻译时调用。",
            "长按快捷键说话，松开后自动粘贴到当前应用。",
            "支持 OpenAI Chat、OpenAI Responses 和 Anthropic 润色端点。",
        ):
            tk.Label(
                f,
                text=self._t(line),
                bg=_C["bg"],
                fg=_C["text2"],
                font=("Segoe UI", 10),
                anchor="w",
                justify="left",
                wraplength=420,
            ).pack(fill="x", pady=(0, 6))

        tk.Label(
            f,
            text=self._t("语音小技巧"),
            bg=_C["bg"],
            fg=_C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(fill="x", pady=(6, 6))
        for line in (
            "说“帮我总结成要点……”会输出要点。",
            "说“整理成待办……”会提取行动项。",
            "说“写成一段发给同事的话……”会整理成消息。",
            "endpoint、base_url、Responses API 等技术词会尽量保留。",
        ):
            tk.Label(
                f,
                text=self._t(line),
                bg=_C["bg"],
                fg=_C["text2"],
                font=("Segoe UI", 9),
                anchor="w",
                justify="left",
                wraplength=420,
            ).pack(fill="x", pady=(0, 4))

        link_row = tk.Frame(f, bg=_C["bg"])
        link_row.pack(fill="x", pady=(8, 16))
        tk.Label(
            link_row,
            text=self._t("项目主页"),
            bg=_C["bg"],
            fg=_C["muted"],
            font=("Segoe UI", 9),
        ).pack(side="left")
        link = tk.Label(
            link_row,
            text="github.com/kylefu8/vox-ai-input",
            bg=_C["bg"],
            fg=_C["accent"],
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        link.pack(side="left", padx=(10, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open("https://github.com/kylefu8/vox-ai-input"))

        buttons = tk.Frame(f, bg=_C["bg"])
        buttons.pack(fill="x")
        _btn(
            buttons,
            self._t("打开 GitHub"),
            lambda: webbrowser.open("https://github.com/kylefu8/vox-ai-input"),
            w=12,
        ).pack(side="left")
        _btn(buttons, self._t("关闭"), lambda: dlg.destroy(), accent=True, w=10).pack(side="right")

        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px, py = self._root.winfo_x(), self._root.winfo_y()
        pw, ph = self._root.winfo_width(), self._root.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.deiconify()
        dlg.lift()
        dlg.focus_force()
        dlg.wait_window()

    def _toggle_theme(self):
        """切换深色/浅色主题，不重建窗口内容。"""
        self._snapshot_config_for_rebuild()
        old_palette = _C.copy()
        _set_current_theme("light" if _current_theme == "dark" else "dark")
        self._apply_theme_to_existing_widgets(old_palette)

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
