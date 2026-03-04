"""
设置窗口模块（现代深色主题）

基于 tkinter 的设置 UI，从系统托盘菜单打开。
深色主题 + 卡片式布局 + 彩色强调色，比传统 ttk 更现代。

功能：
- API 配置（endpoint、key、模型名等）
- 快捷键（按键捕捉 + 冲突检测）、润色开关、翻译等常用设置
- 高级设置（采样率、声道、时长、提示词，默认折叠）

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

_settings_open = False

# ==================== Catppuccin Latte-Dark 色系 ====================
_C = {
    "bg": "#282A36",
    "surface": "#343746",
    "border": "#4A4D5E",
    "text": "#E2E4F0",
    "text2": "#9499B0",
    "accent": "#8BE9FD",
    "green": "#50FA7B",
    "red": "#FF5555",
    "yellow": "#F1FA8C",
    "orange": "#FFB86C",
    "btn": "#4E5166",
    "btn_h": "#626580",
    "entry": "#3C3F52",
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
}


# ==================== UI 工具函数 ====================

def _entry(parent, var=None, w=30, show="", **kw):
    """深色输入框。"""
    return tk.Entry(
        parent, textvariable=var, width=w, show=show,
        bg=_C["entry"], fg=_C["text"], insertbackground=_C["accent"],
        selectbackground=_C["accent"], selectforeground="#1E1E2E",
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=_C["border"], highlightcolor=_C["accent"],
        font=("Segoe UI", 10), **kw,
    )


def _btn(parent, text, cmd=None, accent=False, w=8, **kw):
    """风格化按钮。"""
    bg = _C["accent"] if accent else _C["btn"]
    fg = "#1E1E2E" if accent else _C["text"]
    hbg = "#A4C8FF" if accent else _C["btn_h"]
    b = tk.Button(
        parent, text=text, command=cmd, bg=bg, fg=fg,
        activebackground=hbg, activeforeground=fg,
        relief="flat", bd=0, padx=12, pady=4,
        font=("Segoe UI", 10), cursor="hand2", width=w, **kw,
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
    return tk.Frame(parent, bg=_C["surface"], padx=16, pady=12)


def _sep(parent):
    """间距。"""
    tk.Frame(parent, bg=_C["bg"], height=8).pack(fill="x")


class SettingsWindow:
    """现代深色主题设置窗口。"""

    def __init__(self, current_config, status_info=None, on_save=None):
        global _settings_open
        _settings_open = True
        self._config = current_config
        self._status_info = status_info or {}
        self._on_save = on_save
        self._advanced_visible = False
        self._translate_options = [
            ("不翻译", ""), ("简体中文", "zh"), ("英语", "en"),
            ("日语", "ja"), ("韩语", "ko"), ("法语", "fr"),
            ("德语", "de"), ("西班牙语", "es"), ("俄语", "ru"),
            ("繁体中文", "zh-TW"),
        ]
        self._build_ui()

    # ==================== 构建 UI ====================

    def _build_ui(self):
        """构建窗口。"""
        self._root = tk.Tk()
        self._root.title("Vox AI Input")
        self._root.configure(bg=_C["bg"])
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.withdraw()

        m = tk.Frame(self._root, bg=_C["bg"], padx=24, pady=20)
        m.pack(fill="both", expand=True)

        # ---- 标题 ----
        hdr = tk.Frame(m, bg=_C["bg"])
        hdr.pack(fill="x", pady=(0, 16))

        from run import __version__
        tk.Label(hdr, text="Vox AI Input", bg=_C["bg"], fg=_C["text"],
                 font=("Segoe UI Black", 18)).pack(side="left")
        tk.Label(hdr, text=f"v{__version__}", bg=_C["bg"], fg=_C["text2"],
                 font=("Segoe UI", 11)).pack(side="left", padx=(10, 0), pady=(6, 0))

        # 右侧：项目介绍 + 链接
        right_info = tk.Frame(hdr, bg=_C["bg"])
        right_info.pack(side="right")
        tk.Label(right_info, text="AI 语音输入法 · 说话即打字",
                 bg=_C["bg"], fg=_C["text2"], font=("Segoe UI", 9)).pack(anchor="e")
        link = tk.Label(right_info, text="github.com/kylefu8/vox-ai-input",
                        bg=_C["bg"], fg=_C["accent"], font=("Segoe UI", 9),
                        cursor="hand2")
        link.pack(anchor="e")
        link.bind("<Button-1>", lambda e: __import__("webbrowser").open(
            "https://github.com/kylefu8/vox-ai-input"))

        # ---- 上次结果摘要 ----
        last_text = self._status_info.get("last_text", "")
        last_duration = self._status_info.get("last_duration", 0)
        api_calls = self._status_info.get("session_api_calls", 0)
        if last_text:
            info_frame = tk.Frame(m, bg=_C["surface"], padx=12, pady=8)
            info_frame.pack(fill="x", pady=(0, 12))
            display_text = last_text if len(last_text) <= 50 else last_text[:47] + "..."
            duration_str = f"  ({last_duration:.1f}s)" if last_duration else ""
            tk.Label(
                info_frame,
                text=f"上次输出: \u201c{display_text}\u201d{duration_str}",
                bg=_C["surface"], fg=_C["text2"],
                font=("Segoe UI", 9), anchor="w", wraplength=460, justify="left",
            ).pack(fill="x")
            if api_calls > 0:
                tk.Label(
                    info_frame,
                    text=f"本次会话已调用 API {api_calls} 次",
                    bg=_C["surface"], fg=_C["text2"],
                    font=("Segoe UI", 9), anchor="w",
                ).pack(fill="x")

        # ---- API 配置 ----
        _lbl(m, "🔑  API 配置", fg=_C["accent"], font_size=11, bold=True, bg=_C["bg"]).pack(fill="x", pady=(0, 6))
        c1 = _card(m)
        c1.pack(fill="x", pady=(0, 12))
        az = self._config.get("azure", {})

        for i, (label, key, show) in enumerate([
            ("端点 URL", "endpoint", ""),
            ("API Key", "api_key", "●"),
            ("转写模型", "whisper_deployment", ""),
            ("润色模型", "gpt_deployment", ""),
        ]):
            _lbl(c1, label).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar(master=self._root, value=az.get(key, ""))
            setattr(self, f"_{key.replace('_', '')}_var" if 'deploy' not in key else f"_{'whisper' if 'whisper' in key else 'gpt'}_var", var)
            e = _entry(c1, var=var, w=40, show=show)
            e.grid(row=i, column=1, sticky="ew", pady=3, padx=(10, 0))
            if key == "api_key":
                self._endpoint_var = getattr(self, "_endpointvar", None)  # fix below
                self._apikey_var = var
                self._apikey_entry = e
                self._show_key = False
                eye = _btn(c1, "👁", self._toggle_api_key, w=3)
                eye.grid(row=i, column=2, padx=(4, 0))

        # Fix variable references for the loop above
        self._endpoint_var = tk.StringVar(master=self._root, value=az.get("endpoint", ""))
        self._apikey_var = tk.StringVar(master=self._root, value=az.get("api_key", ""))
        self._whisper_var = tk.StringVar(master=self._root, value=az.get("whisper_deployment", ""))
        self._gpt_var = tk.StringVar(master=self._root, value=az.get("gpt_deployment", ""))

        # Rebuild API card properly (the loop approach was flawed)
        c1.destroy()
        c1 = _card(m)
        c1.pack(fill="x", pady=(0, 12), after=m.winfo_children()[1])

        rows = [
            ("端点 URL", self._endpoint_var, ""),
            ("API Key", self._apikey_var, "●"),
            ("转写模型", self._whisper_var, ""),
            ("润色模型", self._gpt_var, ""),
        ]
        for i, (label, var, show) in enumerate(rows):
            _lbl(c1, label).grid(row=i, column=0, sticky="w", pady=3)
            e = _entry(c1, var=var, w=40, show=show)
            e.grid(row=i, column=1, sticky="ew", pady=3, padx=(10, 0))
            if label == "API Key":
                self._apikey_entry = e
                self._show_key = False
                _btn(c1, "👁", self._toggle_api_key, w=3).grid(row=i, column=2, padx=(4, 0))
        c1.columnconfigure(1, weight=1)

        # ---- 常用设置 ----
        _lbl(m, "⚙  常用设置", fg=_C["accent"], font_size=11, bold=True, bg=_C["bg"]).pack(fill="x", pady=(0, 6))
        c2 = _card(m)
        c2.pack(fill="x", pady=(0, 12))

        hk = self._config.get("hotkey", {})
        po = self._config.get("polish", {})

        # 快捷键
        r0 = tk.Frame(c2, bg=_C["surface"])
        r0.pack(fill="x", pady=4)
        _lbl(r0, "快捷键").pack(side="left")
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

        # 润色
        r1 = tk.Frame(c2, bg=_C["surface"])
        r1.pack(fill="x", pady=4)
        self._polish_var = tk.BooleanVar(master=self._root, value=po.get("enabled", True))
        tk.Checkbutton(
            r1, text="启用 AI 润色", variable=self._polish_var,
            bg=_C["surface"], fg=_C["text"], selectcolor=_C["entry"],
            activebackground=_C["surface"], activeforeground=_C["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")

        # 翻译
        r2 = tk.Frame(c2, bg=_C["surface"])
        r2.pack(fill="x", pady=4)
        _lbl(r2, "翻译").pack(side="left")
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

        # 开机自启
        if get_autostart_supported():
            r3 = tk.Frame(c2, bg=_C["surface"])
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

        # ---- 高级设置 ----
        self._toggle_btn = tk.Button(
            m, text="▶  高级设置", command=self._toggle_advanced,
            bg=_C["bg"], fg=_C["text2"], activebackground=_C["bg"],
            activeforeground=_C["accent"], font=("Segoe UI", 10),
            relief="flat", bd=0, cursor="hand2", anchor="w",
        )
        self._toggle_btn.pack(fill="x", pady=(0, 4))
        self._adv_card = _card(m)
        self._build_advanced()

        # ---- 按钮 ----
        bb = tk.Frame(m, bg=_C["bg"])
        bb.pack(fill="x", pady=(16, 0))
        _btn(bb, "取消", self._on_close, w=10).pack(side="right", padx=(8, 0))
        _btn(bb, "保存", self._on_save_click, accent=True, w=10).pack(side="right")

        self._root.update_idletasks()
        self._center_window()
        self._root.deiconify()

    # ==================== 高级设置 ====================

    def _build_advanced(self):
        f = self._adv_card
        az = self._config.get("azure", {})
        rc = self._config.get("recording", {})
        po = self._config.get("polish", {})

        _lbl(f, "⚠ 修改以下设置可能影响程序运行", fg=_C["orange"], font_size=9).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        fields = [
            ("API 版本", "api_version", az.get("api_version", "2024-06-01")),
            ("采样率 (Hz)", "sample_rate", str(rc.get("sample_rate", 16000))),
            ("声道数", "channels", str(rc.get("channels", 1))),
            ("最大时长 (秒)", "max_duration", str(rc.get("max_duration", 60))),
        ]
        for i, (label, attr, val) in enumerate(fields, start=1):
            _lbl(f, label).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(master=self._root, value=val)
            setattr(self, f"_{attr}_var", var)
            _entry(f, var=var, w=28).grid(row=i, column=1, sticky="ew", pady=2, padx=(10, 0))

        # 识别语言
        _lbl(f, "识别语言").grid(row=5, column=0, sticky="w", pady=2)
        self._language_var = tk.StringVar(master=self._root, value=po.get("language", ""))
        lf = tk.Frame(f, bg=_C["surface"])
        lf.grid(row=5, column=1, sticky="ew", pady=2, padx=(10, 0))
        _entry(lf, var=self._language_var, w=8).pack(side="left")
        _lbl(lf, "留空=自动  zh=中文  en=英文", font_size=9).pack(side="left", padx=(8, 0))

        # Prompt
        _lbl(f, "润色提示词").grid(row=6, column=0, sticky="nw", pady=2)
        from src.polisher import POLISH_SYSTEM_PROMPT, build_prompt
        saved = po.get("system_prompt", "") or ""
        tl_code = po.get("translate_to", "")
        display = build_prompt(saved, tl_code)
        self._prompt_text = tk.Text(
            f, width=38, height=8, wrap=tk.WORD,
            bg=_C["entry"], fg=_C["text"], insertbackground=_C["accent"],
            selectbackground=_C["accent"], font=("Consolas", 9),
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=_C["border"], highlightcolor=_C["accent"],
        )
        self._prompt_text.grid(row=6, column=1, sticky="ew", pady=2, padx=(10, 0))
        self._prompt_text.insert("1.0", display)
        _lbl(f, "留空=使用默认提示词", font_size=9).grid(row=7, column=1, sticky="w", padx=(10, 0))

        f.columnconfigure(1, weight=1)

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._toggle_btn.config(text="▼  高级设置")
            self._adv_card.pack(fill="x", pady=(0, 8), after=self._toggle_btn)
        else:
            self._toggle_btn.config(text="▶  高级设置")
            self._adv_card.pack_forget()
        # 只调整窗口高度，不移动位置
        self._root.update_idletasks()
        self._resize_height()

    # ==================== 翻译联动 ====================

    def _on_translate_changed(self, event=None):
        from src.polisher import build_prompt
        code = ""
        for lb, cd in self._translate_options:
            if lb == self._translate_var.get():
                code = cd
                break
        cur = self._prompt_text.get("1.0", "end-1c").strip()
        base = self._strip_translate_suffix(cur)
        self._prompt_text.delete("1.0", "end")
        self._prompt_text.insert("1.0", build_prompt(base, code))

    @staticmethod
    def _strip_translate_suffix(p):
        import re
        return re.sub(r"\n\n最后，将润色后的文字翻译为.+。只输出翻译结果，不要输出原文。$", "", p).strip()

    # ==================== API Key ====================

    def _toggle_api_key(self):
        self._show_key = not self._show_key
        self._apikey_entry.config(show="" if self._show_key else "●")

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
                messagebox.showwarning("快捷键冲突", f"「{combo}」是常用系统快捷键，可能冲突。", parent=self._root)
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
            messagebox.showerror("输入错误", str(e), parent=self._root)
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
                    messagebox.showinfo("保存成功", "配置已保存并立即生效。", parent=self._root)
                    self._on_close()
                else:
                    messagebox.showerror("保存失败", msg or "未知错误", parent=self._root)
            except Exception as e:
                messagebox.showerror("保存失败", f"出错: {e}", parent=self._root)
        else:
            self._on_close()

    def _collect_config(self):
        import copy
        ep = self._endpoint_var.get().strip()
        ak = self._apikey_var.get().strip()
        wh = self._whisper_var.get().strip()
        gp = self._gpt_var.get().strip()
        if not ep: raise ValueError("端点 URL 不能为空")
        if not ak: raise ValueError("API Key 不能为空")
        if not wh: raise ValueError("转写模型不能为空")
        if not gp: raise ValueError("润色模型不能为空")
        try:
            sr = int(self._sample_rate_var.get().strip())
            assert sr > 0
        except Exception:
            raise ValueError("采样率必须是正整数")
        try:
            ch = int(self._channels_var.get().strip())
            assert ch > 0
        except Exception:
            raise ValueError("声道数必须是正整数")
        try:
            md = int(self._max_duration_var.get().strip())
            assert md > 0
        except Exception:
            raise ValueError("最大录音时长必须是正整数")

        c = copy.deepcopy(self._config)
        a = c.setdefault("azure", {})
        a["endpoint"] = ep
        a["api_key"] = ak
        a["api_version"] = self._api_version_var.get().strip()
        a["whisper_deployment"] = wh
        a["gpt_deployment"] = gp
        r = c.setdefault("recording", {})
        r["sample_rate"] = sr
        r["channels"] = ch
        r["max_duration"] = md
        c.setdefault("hotkey", {})["combination"] = self._hotkey_var.get().strip()
        p = c.setdefault("polish", {})
        p["enabled"] = self._polish_var.get()
        p["language"] = self._language_var.get().strip()
        p["system_prompt"] = self._strip_translate_suffix(self._prompt_text.get("1.0", "end-1c").strip())
        tl = ""
        for lb, cd in self._translate_options:
            if lb == self._translate_var.get():
                tl = cd
                break
        p["translate_to"] = tl
        return c

    # ==================== 窗口管理 ====================

    def _center_window(self):
        """首次打开时居中。"""
        self._root.update_idletasks()
        w, h = self._root.winfo_reqwidth(), self._root.winfo_reqheight()
        sw, sh = self._root.winfo_screenwidth(), self._root.winfo_screenheight()
        self._root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _resize_height(self):
        """展开/折叠时只调整高度，保持窗口位置不动。"""
        self._root.update_idletasks()
        w = self._root.winfo_reqwidth()
        h = self._root.winfo_reqheight()
        x = self._root.winfo_x()
        y = self._root.winfo_y()
        self._root.geometry(f"{w}x{h}+{x}+{y}")

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


def open_settings(current_config, status_info=None, on_save=None):
    """在新线程中打开设置窗口。"""
    global _settings_open
    if _settings_open:
        return

    def _run():
        try:
            SettingsWindow(current_config, status_info, on_save).run()
        except Exception as e:
            log.error("打开设置窗口失败: %s", e)
            global _settings_open
            _settings_open = False

    threading.Thread(target=_run, daemon=True).start()
