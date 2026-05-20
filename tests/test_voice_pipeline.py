"""
voice_pipeline 模块的单元测试

核心流水线不依赖 GUI/托盘，外部输出通过注入函数和 callbacks 验证。
"""

from unittest.mock import MagicMock

from src.voice_pipeline import VoicePipeline


def test_process_audio_transcribes_polishes_and_pastes(tmp_path):
    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(b"fake wav data")

    transcriber = MagicMock()
    transcriber.transcribe.return_value = "你好世界"
    polisher = MagicMock()
    polisher.polish.return_value = "你好，世界。"
    paste = MagicMock()
    raw_cb = MagicMock()
    final_cb = MagicMock()

    pipeline = VoicePipeline(
        transcriber=transcriber,
        polisher=polisher,
        polish_enabled=True,
        language="zh",
        stt_counts_as_api=True,
        paste_func=paste,
    )

    result = pipeline.process_audio(wav_file, on_raw_text=raw_cb, on_final_text=final_cb)

    transcriber.transcribe.assert_called_once_with(wav_file, language="zh")
    polisher.polish.assert_called_once_with("你好世界")
    raw_cb.assert_called_once_with("你好世界")
    final_cb.assert_called_once_with("你好，世界。")
    paste.assert_called_once_with("你好，世界。")
    assert result.raw_text == "你好世界"
    assert result.final_text == "你好，世界。"
    assert result.api_calls == 2
    assert result.duration >= 0


def test_process_audio_returns_none_for_empty_transcription(tmp_path):
    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(b"fake wav data")

    transcriber = MagicMock()
    transcriber.transcribe.return_value = None
    paste = MagicMock()

    pipeline = VoicePipeline(transcriber=transcriber, paste_func=paste)

    assert pipeline.process_audio(wav_file) is None
    paste.assert_not_called()


def test_process_text_falls_back_to_raw_when_polish_empty():
    polisher = MagicMock()
    polisher.polish.return_value = ""
    paste = MagicMock()

    pipeline = VoicePipeline(
        transcriber=None,
        polisher=polisher,
        polish_enabled=True,
        paste_func=paste,
    )

    result = pipeline.process_text("原始文字")

    polisher.polish.assert_called_once_with("原始文字")
    paste.assert_called_once_with("原始文字")
    assert result.final_text == "原始文字"
    assert result.api_calls == 1


def test_process_text_skips_polish_when_disabled():
    polisher = MagicMock()
    paste = MagicMock()

    pipeline = VoicePipeline(
        transcriber=None,
        polisher=polisher,
        polish_enabled=False,
        paste_func=paste,
    )

    result = pipeline.process_text("原始文字")

    polisher.polish.assert_not_called()
    paste.assert_called_once_with("原始文字")
    assert result.final_text == "原始文字"
    assert result.api_calls == 0


def test_process_audio_saves_history(tmp_path):
    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(b"fake wav data")

    transcriber = MagicMock()
    transcriber.transcribe.return_value = "你好世界"
    paste = MagicMock()
    history_store = MagicMock()
    history_store.append.return_value = type("Entry", (), {"id": "hist-1"})()

    pipeline = VoicePipeline(
        transcriber=transcriber,
        polish_enabled=False,
        paste_func=paste,
        history_store=history_store,
        history_metadata={"polish_profile": "azure"},
    )

    result = pipeline.process_audio(wav_file)

    history_store.append.assert_called_once()
    kwargs = history_store.append.call_args.kwargs
    assert kwargs["raw_text"] == "你好世界"
    assert kwargs["final_text"] == "你好世界"
    assert kwargs["source"] == "audio"
    assert kwargs["metadata"]["polish_profile"] == "azure"
    assert result.history_id == "hist-1"
