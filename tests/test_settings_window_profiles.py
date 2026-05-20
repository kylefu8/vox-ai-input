"""
设置窗口 LLM profile 管理辅助函数测试。
"""

import pytest

from src.settings_window import (
    _default_llm_profile,
    _normalize_llm_profile_name,
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
