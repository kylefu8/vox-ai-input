"""
polisher 模块的单元测试

外部 API 调用全部用 mock 替代，测试输入输出逻辑和异常处理。
"""

import pytest
from unittest.mock import MagicMock

from openai import APITimeoutError, APIConnectionError

import src.azure_client


@pytest.fixture(autouse=True)
def clear_client_cache():
    """每个测试前清除客户端缓存，避免测试间干扰。"""
    src.azure_client._client_cache.clear()
    yield
    src.azure_client._client_cache.clear()


class TestPolisher:
    """文字润色器的测试。"""

    def _make_polisher(self):
        """创建一个带 mock LLM client 的 Polisher 实例。"""
        from src.polisher import Polisher

        llm_client = MagicMock()
        llm_client.provider = "mock"
        llm_client.model_name = "mock-model"
        return Polisher(llm_client=llm_client)

    def _mock_chat_response(self, polisher, text):
        """设置 mock LLM 返回值。"""
        polisher.llm_client.complete_text = MagicMock(return_value=text)

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
        p.llm_client.complete_text = MagicMock(
            side_effect=Exception("API error")
        )

        result = p.polish("原始文字")
        assert result == "原始文字"

    def test_polish_timeout_returns_original(self):
        """API 超时应该降级返回原文。"""
        p = self._make_polisher()
        p.llm_client.complete_text = MagicMock(
            side_effect=APITimeoutError(request=MagicMock())
        )

        result = p.polish("原始文字")
        assert result == "原始文字"

    def test_polish_connection_error_returns_original(self):
        """连接错误应该降级返回原文。"""
        p = self._make_polisher()
        p.llm_client.complete_text = MagicMock(
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
