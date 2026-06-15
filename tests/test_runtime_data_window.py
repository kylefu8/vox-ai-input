from src.runtime_data_window import RuntimeDataWindow, _format_history_time, _short_text


def test_short_text_flattens_and_truncates():
    text = "第一行\n第二行很长"

    assert _short_text(text, limit=8) == "第一行 第..."


def test_format_history_time_handles_iso_value():
    formatted = _format_history_time("2026-06-15T10:20:30+00:00")

    assert formatted.startswith("2026-06-15")
    assert "10:20" in formatted or ":" in formatted


def test_window_translation_accepts_text_placeholder():
    window = RuntimeDataWindow.__new__(RuntimeDataWindow)
    window._language = "en"

    assert window._t("最近结果：{text}", text="hello") == "Latest result: hello"
