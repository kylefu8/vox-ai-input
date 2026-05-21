from src.i18n import language_label, language_options, normalize_ui_language, t


def test_normalize_ui_language_aliases():
    assert normalize_ui_language("zh") == "zh-CN"
    assert normalize_ui_language("en-US") == "en"
    assert normalize_ui_language("unknown") == "zh-CN"


def test_translation_falls_back_to_source_text():
    assert t("设置", "en") == "Settings"
    assert t("不存在的文案", "en") == "不存在的文案"
    assert t("设置", "zh-CN") == "设置"


def test_translation_formats_placeholders():
    assert t("共 {count} 条历史记录", "en", count=3) == "3 history items"


def test_polish_tips_are_translated():
    assert t("语音小技巧", "en") == "Voice Tips"
    assert "action items" in t("说“整理成待办……”会提取行动项。", "en")


def test_floating_control_text_is_translated():
    assert t("显示悬浮录音按钮", "en") == "Show floating mic button"
    assert "Alt+Z" in t("Alt+Z 常被显卡覆盖层或录屏工具占用，建议更换。", "en")


def test_language_labels_are_localized():
    assert language_label("zh-CN", "en") == "Chinese"
    assert language_label("zh-CN", "zh-CN") == "简体中文"
    assert ("English", "en") in language_options("zh-CN")
