"""
transcriber 和 polisher 模块的单元测试

外部 API 调用全部用 mock 替代，测试输入输出逻辑和异常处理。
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

from openai import APITimeoutError, APIConnectionError

import src.azure_client


@pytest.fixture(autouse=True)
def clear_client_cache():
    """每个测试前清除客户端缓存，避免测试间干扰。"""
    src.azure_client._client_cache.clear()
    yield
    src.azure_client._client_cache.clear()


class TestTranscriber:
    """语音转写器的测试。"""

    def _make_transcriber(self):
        """创建一个带 mock 客户端的 Transcriber 实例。"""
        with patch("src.azure_client.AzureOpenAI"):
            from src.transcriber import Transcriber
            t = Transcriber(
                endpoint="https://test.openai.azure.com/",
                api_key="test-key",
                api_version="2024-06-01",
                deployment="whisper",
            )
        return t

    def test_transcribe_returns_text(self, tmp_path):
        """正常转写应该返回文字。"""
        t = self._make_transcriber()
        t.client.audio.transcriptions.create = MagicMock(return_value="你好世界")

        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav data")

        result = t.transcribe(audio_file, language="zh")
        assert result == "你好世界"

    def test_transcribe_empty_result_returns_none(self, tmp_path):
        """空转写结果应该返回 None。"""
        t = self._make_transcriber()
        t.client.audio.transcriptions.create = MagicMock(return_value="   ")

        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav data")

        result = t.transcribe(audio_file)
        assert result is None

    def test_transcribe_file_not_found_returns_none(self):
        """音频文件不存在应该返回 None。"""
        t = self._make_transcriber()

        result = t.transcribe(Path("/nonexistent/file.wav"))
        assert result is None

    def test_transcribe_timeout_returns_none(self, tmp_path):
        """API 超时应该返回 None。"""
        t = self._make_transcriber()
        t.client.audio.transcriptions.create = MagicMock(
            side_effect=APITimeoutError(request=MagicMock())
        )

        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav data")

        result = t.transcribe(audio_file)
        assert result is None

    def test_transcribe_connection_error_returns_none(self, tmp_path):
        """连接错误应该返回 None。"""
        t = self._make_transcriber()
        t.client.audio.transcriptions.create = MagicMock(
            side_effect=APIConnectionError(request=MagicMock())
        )

        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav data")

        result = t.transcribe(audio_file)
        assert result is None

    def test_transcribe_without_language(self, tmp_path):
        """不指定语言时应该也能正常工作（自动检测）。"""
        t = self._make_transcriber()
        t.client.audio.transcriptions.create = MagicMock(return_value="hello world")

        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav data")

        result = t.transcribe(audio_file, language="")
        assert result == "hello world"

        # 验证调用参数中不含 language
        call_kwargs = t.client.audio.transcriptions.create.call_args
        params = call_kwargs[1] if call_kwargs[1] else call_kwargs[0][0]
        assert "language" not in params or params.get("language") == ""

    def test_cleanup_audio_deletes_file(self, tmp_path):
        """cleanup_audio 应该删除临时文件。"""
        t = self._make_transcriber()

        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav data")
        assert audio_file.exists()

        t.cleanup_audio(audio_file)
        assert not audio_file.exists()

    def test_cleanup_nonexistent_file_no_error(self):
        """清理不存在的文件不应该报错。"""
        t = self._make_transcriber()
        # 不应抛出异常
        t.cleanup_audio(Path("/nonexistent/file.wav"))


class TestPolisher:
    """文字润色器的测试。"""

    def _make_polisher(self):
        """创建一个带 mock 客户端的 Polisher 实例。"""
        with patch("src.azure_client.AzureOpenAI"):
            from src.polisher import Polisher
            p = Polisher(
                endpoint="https://test.openai.azure.com/",
                api_key="test-key",
                api_version="2024-06-01",
                deployment="gpt-4o-mini",
            )
        return p

    def _mock_chat_response(self, polisher, text):
        """设置 mock 的 GPT 返回值。"""
        mock_message = MagicMock()
        mock_message.content = text
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        polisher.client.chat.completions.create = MagicMock(return_value=mock_response)

    def test_polish_returns_text(self):
        """正常润色应该返回润色后的文字。"""
        p = self._make_polisher()
        self._mock_chat_response(p, "你好，世界。")

        result = p.polish("你好 世界")
        assert result == "你好，世界。"

    def test_polish_empty_input_returns_none(self):
        """空输入应该返回 None。"""
        p = self._make_polisher()

        assert p.polish("") is None
        assert p.polish("   ") is None
        assert p.polish(None) is None

    def test_polish_empty_response_returns_original(self):
        """GPT 返回空内容应该降级返回原文。"""
        p = self._make_polisher()
        self._mock_chat_response(p, "")

        result = p.polish("原始文字")
        assert result == "原始文字"

    def test_polish_api_error_returns_original(self):
        """API 调用失败应该降级返回原文。"""
        p = self._make_polisher()
        p.client.chat.completions.create = MagicMock(
            side_effect=Exception("API error")
        )

        result = p.polish("原始文字")
        assert result == "原始文字"

    def test_polish_timeout_returns_original(self):
        """API 超时应该降级返回原文。"""
        p = self._make_polisher()
        p.client.chat.completions.create = MagicMock(
            side_effect=APITimeoutError(request=MagicMock())
        )

        result = p.polish("原始文字")
        assert result == "原始文字"

    def test_polish_connection_error_returns_original(self):
        """连接错误应该降级返回原文。"""
        p = self._make_polisher()
        p.client.chat.completions.create = MagicMock(
            side_effect=APIConnectionError(request=MagicMock())
        )

        result = p.polish("原始文字")
        assert result == "原始文字"

    def test_polish_same_text_returns_same(self):
        """原文不需要修改时应返回相同文字。"""
        p = self._make_polisher()
        self._mock_chat_response(p, "已经很好的文字")

        result = p.polish("已经很好的文字")
        assert result == "已经很好的文字"
