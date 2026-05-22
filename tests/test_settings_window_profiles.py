"""
设置窗口 LLM profile 管理辅助函数测试。
"""

import pytest

import src.settings_window as settings_window
from src.settings_window import (
    SettingsWindow,
    _button_width,
    _default_llm_profile,
    _icon_text,
    _hotkey_warning_text,
    _normalize_llm_profile_name,
    _normalize_hotkey_combo,
    _unique_llm_profile_name,
)


def test_normalize_llm_profile_name():
    assert _normalize_llm_profile_name(" My Claude Profile ") == "my-claude-profile"
    assert _normalize_llm_profile_name("deepseek.v3_main") == "deepseek.v3_main"


def test_normalize_llm_profile_name_rejects_empty():
    with pytest.raises(ValueError, match="不能为空"):
        _normalize_llm_profile_name(" ! ")


def test_unique_llm_profile_name_adds_suffix():
    assert _unique_llm_profile_name("openai-copy", {"openai-copy"}) == "openai-copy-2"
    assert _unique_llm_profile_name("openai-copy", {"openai-copy", "openai-copy-2"}) == "openai-copy-3"


def test_default_azure_profile_uses_azure_config():
    profile = _default_llm_profile(
        "azure_openai",
        {
            "endpoint": "https://test.openai.azure.com/",
            "api_key": "key",
        },
    )

    assert profile["provider"] == "azure_openai"
    assert profile["endpoint"] == "https://test.openai.azure.com/"
    assert profile["api_key"] == "key"
    assert profile["model"]


def test_default_anthropic_profile():
    profile = _default_llm_profile("anthropic")

    assert profile["provider"] == "anthropic"
    assert profile["endpoint"] == "https://api.anthropic.com"
    assert profile["model"].startswith("claude-")


def test_default_openai_responses_profile():
    profile = _default_llm_profile("openai_responses")

    assert profile["provider"] == "openai_responses"
    assert profile["endpoint"] == "https://api.openai.com/v1"
    assert profile["model"]


def test_button_width_expands_for_english_labels():
    assert _button_width("Download", 4) >= 9
    assert _button_width("下载", 4) >= 5
    assert _button_width("🗑️", 3) == 3


def test_icon_text_keeps_command_label_for_image_icon_buttons():
    assert _icon_text("save", "Save") == "Save"


def test_hotkey_warning_flags_alt_z():
    assert _normalize_hotkey_combo(" Alt + Z ") == "alt+z"
    assert "Alt+Z" in _hotkey_warning_text("alt+z")


def test_hotkey_warning_allows_recommended_default():
    assert _hotkey_warning_text("ctrl+shift+space") == ""


def test_unsaved_theme_preview_reverts_on_close():
    calls = []
    window = SettingsWindow.__new__(SettingsWindow)
    window._on_theme_change = calls.append
    window._initial_theme = "dark"
    window._theme_saved = False
    window._root = type("Root", (), {"destroy": lambda self: None})()

    previous = settings_window._current_theme
    try:
        settings_window._set_current_theme("light")
        window._on_close()
    finally:
        settings_window._set_current_theme(previous)

    assert calls == ["dark"]


def test_saved_theme_preview_does_not_revert_on_close():
    calls = []
    window = SettingsWindow.__new__(SettingsWindow)
    window._on_theme_change = calls.append
    window._initial_theme = "dark"
    window._theme_saved = True
    window._root = type("Root", (), {"destroy": lambda self: None})()

    previous = settings_window._current_theme
    try:
        settings_window._set_current_theme("light")
        window._on_close()
    finally:
        settings_window._set_current_theme(previous)

    assert calls == []
