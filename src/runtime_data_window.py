"""Runtime data window for history and lightweight session state.

This window keeps browsing/copying operational data out of the settings UI.
It uses the shared Tk root guard for the same reason as settings_window.py:
Windows Tk/Tcl can crash when independent roots run concurrently.
"""

import threading
import tkinter as tk

from src.display import get_monitor_rect_for_point, tk_scaling_for_current_monitor
from src.i18n import normalize_ui_language, t
from src.logger import setup_logger
from src.tk_runtime import exclusive_tk_root
from src.ui_theme import UI_THEMES, normalize_ui_theme

log = setup_logger(__name__)

_runtime_data_open = False


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


class RuntimeDataWindow:
    """A compact window for runtime history and session state."""

    def __init__(
        self,
        config,
        on_get_history_entries=None,
        on_clear_history=None,
        on_get_status=None,
    ):
        global _runtime_data_open
        _runtime_data_open = True

        ui_cfg = (config or {}).get("ui", {}) or {}
        self._language = normalize_ui_language(ui_cfg.get("language"))
        self._theme = normalize_ui_theme(ui_cfg.get("theme"))
        self._palette = UI_THEMES[self._theme]
        self._on_get_history_entries = on_get_history_entries
        self._on_clear_history = on_clear_history
        self._on_get_status = on_get_status

        self._root = tk.Tk()
        self._root.title(self._t("运行数据"))
        self._root.configure(bg=self._c("bg"))
        self._root.minsize(760, 540)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_tk_scaling()

        self._build()
        self._center_window()
        self._refresh_all()

    def _t(self, source, **kwargs):
        return t(source, self._language, **kwargs)

    def _c(self, key):
        return self._palette[key]

    def _configure_tk_scaling(self):
        try:
            self._root.tk.call("tk", "scaling", tk_scaling_for_current_monitor())
        except Exception:
            pass

    def _build(self):
        root = self._root
        main = tk.Frame(root, bg=self._c("bg"), padx=22, pady=18)
        main.pack(fill="both", expand=True)

        header = tk.Frame(main, bg=self._c("bg"))
        header.pack(fill="x", pady=(0, 14))
        tk.Label(
            header,
            text=self._t("运行数据"),
            bg=self._c("bg"),
            fg=self._c("text"),
            font=("Segoe UI Semibold", 17),
            anchor="w",
        ).pack(side="left")
        self._status_summary_var = tk.StringVar(master=root, value="")
        tk.Label(
            header,
            textvariable=self._status_summary_var,
            bg=self._c("bg"),
            fg=self._c("text2"),
            font=("Segoe UI", 9),
            anchor="e",
        ).pack(side="right")

        self._build_status_card(main)
        self._build_history_card(main)

    def _build_status_card(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        top = tk.Frame(card, bg=self._c("surface"))
        top.pack(fill="x")
        tk.Label(
            top,
            text=self._t("会话状态"),
            bg=self._c("surface"),
            fg=self._c("accent"),
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).pack(side="left")
        self._status_last_result_var = tk.StringVar(master=self._root, value="")
        self._status_calls_var = tk.StringVar(master=self._root, value="")

        body = tk.Frame(card, bg=self._c("surface2"), padx=12, pady=10)
        body.pack(fill="x", pady=(10, 0))
        tk.Label(
            body,
            textvariable=self._status_calls_var,
            bg=self._c("surface2"),
            fg=self._c("text"),
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            textvariable=self._status_last_result_var,
            bg=self._c("surface2"),
            fg=self._c("text2"),
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=660,
        ).pack(fill="x", pady=(5, 0))

    def _build_history_card(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=self._c("surface"))
        top.pack(fill="x", pady=(0, 10))
        tk.Label(
            top,
            text=self._t("最近输出"),
            bg=self._c("surface"),
            fg=self._c("accent"),
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).pack(side="left")
        self._history_summary_var = tk.StringVar(master=self._root, value="")
        tk.Label(
            top,
            textvariable=self._history_summary_var,
            bg=self._c("surface"),
            fg=self._c("text2"),
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(12, 0))
        self._button(top, self._t("刷新"), self._refresh_all).pack(side="right")
        self._button(top, self._t("清空历史"), self._clear_history).pack(side="right", padx=(0, 8))

        scroll_wrap = tk.Frame(card, bg=self._c("surface"))
        scroll_wrap.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(
            scroll_wrap,
            bg=self._c("surface"),
            bd=0,
            highlightthickness=0,
            yscrollincrement=24,
        )
        scrollbar = tk.Scrollbar(scroll_wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._history_frame = tk.Frame(self._canvas, bg=self._c("surface"))
        self._canvas_window = self._canvas.create_window(
            (0, 0),
            window=self._history_frame,
            anchor="nw",
        )
        self._history_frame.bind(
            "<Configure>",
            lambda _event=None: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda event: self._canvas.itemconfigure(self._canvas_window, width=event.width),
        )
        self._canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _card(self, parent):
        return tk.Frame(
            parent,
            bg=self._c("surface"),
            padx=16,
            pady=14,
            highlightthickness=1,
            highlightbackground=self._c("border"),
        )

    def _button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self._c("btn"),
            fg=self._c("text"),
            activebackground=self._c("btn_h"),
            activeforeground=self._c("text"),
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            font=("Segoe UI Semibold", 9),
            cursor="hand2",
        )

    def _get_status(self):
        if self._on_get_status:
            return self._on_get_status() or {}
        return {}

    def _get_history_entries(self):
        if self._on_get_history_entries:
            return self._on_get_history_entries() or []
        return []

    def _refresh_all(self):
        self._refresh_status()
        self._refresh_history()

    def _refresh_status(self):
        status = self._get_status()
        api_calls = int(status.get("session_api_calls") or 0)
        self._status_calls_var.set(
            self._t("本次会话 API 调用：{count}", count=api_calls)
        )
        last_result = status.get("last_result_text") or ""
        duration = float(status.get("last_result_duration") or 0)
        if last_result:
            self._status_last_result_var.set(
                self._t("最近结果：{text}", text=_short_text(last_result, 160))
                + f" · {duration:.1f}s"
            )
        else:
            self._status_last_result_var.set(self._t("暂无最近结果"))

    def _refresh_history(self):
        for child in self._history_frame.winfo_children():
            child.destroy()

        entries = self._get_history_entries()
        self._history_summary_var.set(self._t("共 {count} 条历史记录", count=len(entries)))
        self._status_summary_var.set(self._t("共 {count} 条历史记录", count=len(entries)))

        if not entries:
            empty = tk.Frame(
                self._history_frame,
                bg=self._c("surface2"),
                padx=14,
                pady=14,
                highlightthickness=1,
                highlightbackground=self._c("border"),
            )
            empty.pack(fill="x", pady=(0, 8))
            tk.Label(
                empty,
                text=self._t("暂无历史记录"),
                bg=self._c("surface2"),
                fg=self._c("text"),
                font=("Segoe UI Semibold", 10),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                empty,
                text=self._t("完成一次语音输入后，这里会显示最近结果。"),
                bg=self._c("surface2"),
                fg=self._c("text2"),
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x", pady=(4, 0))
            return

        for index, entry in enumerate(entries[:100], start=1):
            self._add_history_row(index, entry)

    def _add_history_row(self, index, entry):
        row = tk.Frame(
            self._history_frame,
            bg=self._c("surface2"),
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=self._c("border"),
        )
        row.pack(fill="x", pady=(0, 8))

        meta = entry.get("metadata", {}) or {}
        profile = meta.get("polish_profile") or self._t("未润色")
        if meta.get("polish_fallback"):
            profile = f"{profile} · {self._t('润色失败')}"
        duration = float(entry.get("duration") or 0)
        created_at = _format_history_time(entry.get("created_at", ""))

        header = tk.Frame(row, bg=self._c("surface2"))
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"{index:02d}",
            bg=self._c("accent_soft"),
            fg=self._c("accent"),
            font=("Segoe UI Semibold", 8),
            padx=7,
            pady=2,
        ).pack(side="left", padx=(0, 8))
        tk.Label(
            header,
            text=f"{created_at} · {profile} · {duration:.1f}s",
            bg=self._c("surface2"),
            fg=self._c("text2"),
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        self._button(
            header,
            self._t("复制"),
            lambda text=entry.get("final_text", ""): self._copy_history_text(text),
        ).pack(side="right")

        tk.Label(
            row,
            text=_short_text(entry.get("final_text", "")),
            bg=self._c("surface2"),
            fg=self._c("text"),
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=660,
        ).pack(fill="x", pady=(6, 0))

        raw_text = entry.get("raw_text", "")
        if raw_text and raw_text.strip() != (entry.get("final_text", "") or "").strip():
            tk.Label(
                row,
                text=self._t("原文：{text}", text=_short_text(raw_text, 180)),
                bg=self._c("surface2"),
                fg=self._c("text2"),
                font=("Segoe UI", 9),
                anchor="w",
                justify="left",
                wraplength=660,
            ).pack(fill="x", pady=(6, 0))

    def _copy_history_text(self, text):
        if not text:
            return
        try:
            import pyperclip

            pyperclip.copy(text)
            self._history_summary_var.set(self._t("已复制到剪贴板"))
        except Exception as e:
            self._history_summary_var.set(f"{self._t('复制失败')}：{e}")

    def _clear_history(self):
        if not self._on_clear_history:
            self._history_summary_var.set(self._t("当前没有可用的历史记录服务。"))
            return
        try:
            ok = self._on_clear_history()
        except Exception as e:
            self._history_summary_var.set(f"{self._t('清空失败')}：{e}")
            return
        if ok:
            self._refresh_history()
            self._history_summary_var.set(self._t("历史记录已清空"))
        else:
            self._history_summary_var.set(self._t("无法删除历史记录文件。"))

    def _center_window(self):
        self._root.update_idletasks()
        rect = get_monitor_rect_for_point()
        if rect:
            left, top, right, bottom = rect
            sw, sh = right - left, bottom - top
            w = min(max(self._root.winfo_reqwidth(), 820), max(760, sw - 80))
            h = min(max(self._root.winfo_reqheight(), 620), max(540, sh - 100))
            self._root.geometry(f"{w}x{h}+{left + (sw - w) // 2}+{top + (sh - h) // 2}")
            return
        sw, sh = self._root.winfo_screenwidth(), self._root.winfo_screenheight()
        w = min(max(self._root.winfo_reqwidth(), 820), max(760, sw - 80))
        h = min(max(self._root.winfo_reqheight(), 620), max(540, sh - 100))
        self._root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _on_close(self):
        global _runtime_data_open
        _runtime_data_open = False
        try:
            self._root.destroy()
        except Exception:
            pass

    def run(self):
        try:
            self._root.mainloop()
        except Exception as e:
            log.error("运行数据窗口异常: %s", e)
        finally:
            global _runtime_data_open
            _runtime_data_open = False


def open_runtime_data_window(
    current_config,
    on_get_history_entries=None,
    on_clear_history=None,
    on_get_status=None,
):
    """Open the runtime data window in a guarded Tk thread."""
    global _runtime_data_open
    if _runtime_data_open:
        return
    _runtime_data_open = True

    def _run():
        try:
            with exclusive_tk_root("runtime_data"):
                RuntimeDataWindow(
                    current_config,
                    on_get_history_entries=on_get_history_entries,
                    on_clear_history=on_clear_history,
                    on_get_status=on_get_status,
                ).run()
        except Exception as e:
            log.error("打开运行数据窗口失败: %s", e)
            global _runtime_data_open
            _runtime_data_open = False

    threading.Thread(target=_run, daemon=True).start()
