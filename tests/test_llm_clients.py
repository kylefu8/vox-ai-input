"""
llm_clients 模块的单元测试

测试 provider 工厂和 Anthropic 响应解析。实际网络请求全部 mock。
"""

from unittest.mock import MagicMock, patch

from src.llm_clients import (
    AnthropicLLMClient,
    AzureOpenAILLMClient,
    OpenAICompatibleLLMClient,
    OpenAIResponsesLLMClient,
    LLMOptions,
    create_llm_client,
    detect_llm_profile,
    list_llm_models,
    list_llm_models_with_base_url,
    validate_llm_profile,
    validate_llm_profile_for_provider,
    _extract_anthropic_text,
    _extract_openai_responses_text,
    _openai_base_url_candidates,
)


def test_factory_creates_azure_client():
    """azure_openai profile 应创建 AzureOpenAILLMClient。"""
    with patch("src.llm_clients.get_azure_client", return_value=MagicMock()):
        client = create_llm_client({
            "provider": "azure_openai",
            "endpoint": "https://test.openai.azure.com/",
            "api_key": "key",
            "api_version": "2025-01-01-preview",
            "deployment": "gpt-5.4-nano",
        })
    assert isinstance(client, AzureOpenAILLMClient)


def test_factory_creates_openai_compatible_client():
    """openai_compatible profile 应创建 OpenAICompatibleLLMClient。"""
    with patch("src.llm_clients.OpenAI"):
        client = create_llm_client({
            "provider": "openai_compatible",
            "endpoint": "https://api.deepseek.com/v1",
            "api_key": "key",
            "model": "deepseek-chat",
        })
    assert isinstance(client, OpenAICompatibleLLMClient)


def test_factory_creates_openai_responses_client():
    """openai_responses profile 应创建 Responses API client。"""
    client = create_llm_client({
        "provider": "openai_responses",
        "endpoint": "https://api.openai.com/v1",
        "api_key": "key",
        "model": "gpt-5.4-mini",
    })
    assert isinstance(client, OpenAIResponsesLLMClient)


def test_factory_accepts_generic_azure_profile():
    """简化 profile 可用 endpoint/model 映射到 Azure deployment。"""
    with patch("src.llm_clients.get_azure_client", return_value=MagicMock()) as factory:
        client = create_llm_client({
            "provider": "azure_openai",
            "endpoint": "https://test.openai.azure.com/",
            "api_key": "key",
            "model": "gpt-5.4-nano",
        })

    assert isinstance(client, AzureOpenAILLMClient)
    assert client.model_name == "gpt-5.4-nano"
    assert factory.call_args.kwargs["api_version"] == "2025-01-01-preview"


def test_openai_compatible_uses_max_tokens():
    """兼容接口应使用更通用的 max_tokens 参数。"""
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    fake_openai = MagicMock()
    fake_openai.chat.completions.create.return_value = fake_response

    with patch("src.llm_clients.OpenAI", return_value=fake_openai):
        client = OpenAICompatibleLLMClient(
            base_url="https://api.deepseek.com/v1",
            api_key="key",
            model="deepseek-chat",
        )
        result = client.complete_text("system", "user", LLMOptions(max_tokens=42))

    assert result == "ok"
    kwargs = fake_openai.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 42
    assert "max_completion_tokens" not in kwargs


def test_openai_responses_posts_responses_payload():
    """Responses adapter 应调用 /responses 并解析 output_text。"""
    fake_response = MagicMock()
    fake_response.read.return_value = b'{"output_text":"ok"}'
    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_response

    with patch("src.llm_clients.urllib.request.urlopen", return_value=fake_context) as mock_urlopen:
        client = OpenAIResponsesLLMClient(
            base_url="https://api.openai.com/v1",
            api_key="key",
            model="gpt-5.4-mini",
        )
        result = client.complete_text("system", "user", LLMOptions(max_tokens=42))

    assert result == "ok"
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://api.openai.com/v1/responses"
    payload = __import__("json").loads(request.data.decode("utf-8"))
    assert payload["model"] == "gpt-5.4-mini"
    assert payload["instructions"] == "system"
    assert payload["input"] == "user"
    assert payload["max_output_tokens"] == 42
    assert "temperature" not in payload


def test_factory_creates_anthropic_client():
    """anthropic profile 应创建 AnthropicLLMClient。"""
    client = create_llm_client({
        "provider": "anthropic",
        "api_key": "key",
        "model": "claude-3-5-haiku-20241022",
    })
    assert isinstance(client, AnthropicLLMClient)


def test_validate_llm_profile_makes_probe_request():
    """profile 验证应发起最小 completion 请求并返回文本。"""
    fake_client = MagicMock()
    fake_client.complete_text.return_value = " OK "

    with patch("src.llm_clients.create_llm_client", return_value=fake_client) as factory:
        result = validate_llm_profile({
            "provider": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "key",
            "model": "test-model",
            "timeout": 90,
            "max_retries": 3,
        })

    assert result == "OK"
    profile = factory.call_args.args[0]
    assert profile["timeout"] == 20.0
    assert profile["max_retries"] == 0
    options = fake_client.complete_text.call_args.args[2]
    assert options.max_tokens == 64
    assert options.temperature == 0


def test_validate_llm_profile_rejects_empty_response():
    """验证请求空响应应视为失败。"""
    fake_client = MagicMock()
    fake_client.complete_text.return_value = " "

    with patch("src.llm_clients.create_llm_client", return_value=fake_client):
        try:
            validate_llm_profile({"provider": "anthropic", "api_key": "key", "model": "claude"})
        except RuntimeError as e:
            assert "empty response" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_detect_llm_profile_returns_first_working_candidate():
    """自动识别应返回第一个验证成功的候选 profile。"""
    calls = []

    def fake_validate(profile):
        calls.append(profile)
        if profile["provider"] == "openai_compatible":
            return "OK"
        raise RuntimeError("nope")

    with patch("src.llm_clients.validate_llm_profile", side_effect=fake_validate):
        profile, response, errors = detect_llm_profile(
            "https://api.example.com",
            "key",
            "model-a",
        )

    assert response == "OK"
    assert profile["provider"] == "openai_compatible"
    assert profile["endpoint"] == "https://api.example.com"
    assert profile["base_url"] == "https://api.example.com/v1"
    assert errors == []
    assert calls[0]["provider"] == "openai_compatible"
    assert calls[0]["base_url"] == "https://api.example.com/v1"


def test_detect_llm_profile_reports_all_errors():
    """所有候选失败时应汇总每种 API 类型的错误。"""
    with patch("src.llm_clients.validate_llm_profile", side_effect=RuntimeError("bad key")):
        try:
            detect_llm_profile("https://api.anthropic.com", "bad", "claude")
        except RuntimeError as e:
            message = str(e)
        else:
            raise AssertionError("expected RuntimeError")

    assert "没有找到可用的润色 API" in message
    assert "Anthropic" in message
    assert "OpenAI Chat Completions" in message
    assert "OpenAI Responses" in message


def test_validate_llm_profile_for_provider_keeps_explicit_responses_type():
    """用户选择 Responses 时不回退成 Chat Completions。"""
    calls = []

    def fake_validate(profile):
        calls.append(profile)
        if profile["provider"] == "openai_responses":
            return "OK"
        raise RuntimeError("wrong provider")

    with patch("src.llm_clients.validate_llm_profile", side_effect=fake_validate):
        profile, response, errors = validate_llm_profile_for_provider(
            "openai_responses",
            "https://api.example.com",
            "key",
            "model-a",
        )

    assert response == "OK"
    assert profile["provider"] == "openai_responses"
    assert profile["endpoint"] == "https://api.example.com"
    assert profile["base_url"] == "https://api.example.com/v1"
    assert errors == []
    assert [call["provider"] for call in calls] == ["openai_responses"]


def test_list_llm_models_returns_openai_models_without_unrelated_errors():
    """OpenAI-compatible 成功后不继续混入 Azure/Anthropic 探测错误。"""
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        response = MagicMock()
        response.read.return_value = __import__("json").dumps({
            "data": [{"id": "gpt-a"}, {"id": "shared"}],
        }).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        return context

    with patch("src.llm_clients.urllib.request.urlopen", side_effect=fake_urlopen):
        models, errors = list_llm_models("https://api.example.com", "key")

    assert models == ["gpt-a", "shared"]
    assert errors == []
    assert calls == ["https://api.example.com/v1/models"]


def test_list_llm_models_with_base_url_returns_resolved_v1_without_display_mutation():
    """模型列表解析出 /v1 base_url，供保存使用。"""
    def fake_urlopen(request, timeout):
        response = MagicMock()
        response.read.return_value = __import__("json").dumps({
            "data": [{"id": "gpt-a"}],
        }).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        return context

    with patch("src.llm_clients.urllib.request.urlopen", side_effect=fake_urlopen):
        models, errors, base_url = list_llm_models_with_base_url("https://api.example.com", "key")

    assert models == ["gpt-a"]
    assert errors == []
    assert base_url == "https://api.example.com/v1"


def test_openai_base_url_candidates_prefer_v1_for_root_endpoint():
    assert _openai_base_url_candidates("https://llm.example.com/") == [
        "https://llm.example.com/v1",
        "https://llm.example.com",
    ]
    assert _openai_base_url_candidates("https://llm.example.com/v1") == [
        "https://llm.example.com/v1",
    ]


def test_extract_anthropic_text():
    """Anthropic content text blocks 应被拼接。"""
    data = {
        "content": [
            {"type": "text", "text": "你好"},
            {"type": "tool_use", "name": "ignored"},
            {"type": "text", "text": "，世界。"},
        ]
    }
    assert _extract_anthropic_text(data) == "你好，世界。"


def test_extract_openai_responses_text_from_output_blocks():
    data = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "你"},
                    {"type": "output_text", "text": "好"},
                ]
            }
        ]
    }
    assert _extract_openai_responses_text(data) == "你好"


def test_anthropic_complete_text_posts_messages_payload():
    """Anthropic adapter 应调用 /v1/messages 并解析文本。"""
    fake_response = MagicMock()
    fake_response.read.return_value = b'{"content":[{"type":"text","text":"ok"}]}'
    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_response

    with patch("src.llm_clients.urllib.request.urlopen", return_value=fake_context) as mock_urlopen:
        client = AnthropicLLMClient(
            base_url="https://api.anthropic.com",
            api_key="key",
            model="claude-3-5-haiku-20241022",
        )
        result = client.complete_text("system", "user", LLMOptions(max_tokens=12))

    assert result == "ok"
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert request.headers["X-api-key"] == "key"
    assert request.headers["Anthropic-version"] == "2023-06-01"
