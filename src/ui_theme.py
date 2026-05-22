"""Shared UI theme palettes."""

from __future__ import annotations


UI_THEMES = {
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


def normalize_ui_theme(theme):
    """Return a supported UI theme name."""
    theme = str(theme or "dark").strip().lower()
    return theme if theme in UI_THEMES else "dark"


def get_ui_palette(theme):
    """Return the semantic settings-window palette for a theme."""
    return UI_THEMES[normalize_ui_theme(theme)].copy()


def get_floating_palette(theme):
    """Return a floating-capsule palette derived from the main UI palette."""
    theme = normalize_ui_theme(theme)
    c = UI_THEMES[theme]
    if theme == "light":
        return {
            "bg": c["surface2"],
            "bg_hover": c["rail"],
            "bg_press": c["entry"],
            "idle_bg": c["rail"],
            "border": c["btn_h"],
            "text": c["text"],
            "muted": c["text2"],
            "idle": c["accent"],
            "recording": c["red"],
            "recording_soft": "#FCA5A5",
            "processing": c["yellow"],
            "success": c["green"],
            "warning": c["orange"],
            "bars": c["red"],
            "icon": "#0F172A",
            "icon_bg": c["accent_soft"],
            "shadow": "#0F172A",
        }
    return {
        "bg": c["surface"],
        "bg_hover": c["surface2"],
        "bg_press": c["entry"],
        "idle_bg": c["surface"],
        "border": c["border"],
        "text": c["text"],
        "muted": c["text2"],
        "idle": c["accent"],
        "recording": "#FF4D5E",
        "recording_soft": c["red"],
        "processing": c["yellow"],
        "success": c["green"],
        "warning": c["orange"],
        "bars": "#FFE5EE",
        "icon": "#EAFBFF",
        "icon_bg": c["accent_soft"],
        "shadow": "#000000",
    }


FLOATING_THEMES = {
    "dark": get_floating_palette("dark"),
    "light": get_floating_palette("light"),
}
