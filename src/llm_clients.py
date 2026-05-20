"""
LLM provider adapters for text polishing.

The polishing workflow talks to this module instead of a concrete vendor API.
Azure OpenAI keeps the existing behavior, OpenAI-compatible endpoints cover
OpenAI/DeepSeek/OpenRouter/Ollama/LM Studio style APIs, and Anthropic uses the
Messages API directly without adding a new dependency.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI

from src.azure_client import get_azure_client
from src.logger import setup_logger

log = setup_logger(__name__)


DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_AZURE_API_VERSION = "2025-01-01-preview"


@dataclass
class LLMOptions:
    """Runtime options for a single LLM request."""

    max_tokens: int = 1024
    temperature: float = 0.0


class LLMClientProtocol(Protocol):
    """Minimal chat-completion interface used by Polisher."""

    provider: str
    model_name: str

    def complete_text(self, system_prompt: str, user_prompt: str, options: LLMOptions) -> str:
        """Return generated text for a system/user prompt pair."""
        ...


class AzureOpenAILLMClient:
    """Azure OpenAI chat-completions adapter."""

    provider = "azure_openai"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        api_version: str,
        deployment: str,
        timeout: float = 60.0,
        max_retries: int = 0,
    ):
        self.model_name = deployment
        self.client = get_azure_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=timeout,
            max_retries=max_retries,
        )

    def complete_text(self, system_prompt: str, user_prompt: str, options: LLMOptions) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=options.temperature,
            max_completion_tokens=options.max_tokens,
        )
        return response.choices[0].message.content or ""


class OpenAICompatibleLLMClient:
    """OpenAI-compatible /v1/chat/completions adapter."""

    provider = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 0,
    ):
        self.model_name = model
        self.client = OpenAI(
            base_url=base_url.rstrip("/") if base_url else DEFAULT_OPENAI_BASE_URL,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
        )

    def complete_text(self, system_prompt: str, user_prompt: str, options: LLMOptions) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=options.temperature,
            max_tokens=options.max_tokens,
        )
        return response.choices[0].message.content or ""


class AnthropicLLMClient:
    """Anthropic Messages API adapter."""

    provider = "anthropic"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        api_version: str = DEFAULT_ANTHROPIC_VERSION,
        timeout: float = 60.0,
        max_retries: int = 0,
    ):
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.api_key = api_key
        self.api_version = api_version or DEFAULT_ANTHROPIC_VERSION
        self.model_name = model
        self.timeout = timeout
        self.max_retries = max_retries

    def complete_text(self, system_prompt: str, user_prompt: str, options: LLMOptions) -> str:
        payload = {
            "model": self.model_name,
            "max_tokens": options.max_tokens,
            "temperature": options.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
            },
        )

        attempts = max(1, self.max_retries + 1)
        last_error = None
        for _ in range(attempts):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return _extract_anthropic_text(data)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"Anthropic API HTTP {e.code}: {detail}")
                break
            except Exception as e:
                last_error = e

        raise last_error or RuntimeError("Anthropic API request failed")


def create_llm_client(profile: dict) -> LLMClientProtocol:
    """Build an LLM client from a normalized profile dict."""
    provider = _infer_profile_provider(profile)
    timeout = float(profile.get("timeout", 60.0))
    max_retries = int(profile.get("max_retries", 0))
    endpoint = _profile_endpoint(profile)
    model = _profile_model(profile)

    if provider == "azure_openai":
        return AzureOpenAILLMClient(
            endpoint=endpoint,
            api_key=_resolve_api_key(profile),
            api_version=profile.get("api_version", DEFAULT_AZURE_API_VERSION),
            deployment=model,
            timeout=timeout,
            max_retries=max_retries,
        )

    if provider == "openai_compatible":
        return OpenAICompatibleLLMClient(
            base_url=endpoint or DEFAULT_OPENAI_BASE_URL,
            api_key=_resolve_api_key(profile),
            model=model,
            timeout=timeout,
            max_retries=max_retries,
        )

    if provider == "anthropic":
        return AnthropicLLMClient(
            base_url=endpoint or "https://api.anthropic.com",
            api_key=_resolve_api_key(profile),
            model=model,
            api_version=profile.get("api_version", DEFAULT_ANTHROPIC_VERSION),
            timeout=timeout,
            max_retries=max_retries,
        )

    raise ValueError(f"不支持的 LLM provider: {provider}")


def validate_llm_profile(profile: dict) -> str:
    """
    Make a minimal completion request to verify a profile.

    Returns:
        Short response text from the provider.

    Raises:
        Any provider/API error from the underlying client.
    """
    profile = dict(profile)
    profile["timeout"] = min(float(profile.get("timeout", 20.0)), 20.0)
    profile["max_retries"] = 0
    client = create_llm_client(profile)
    result = client.complete_text(
        "You are a connectivity check. Reply with OK only.",
        "Reply OK.",
        LLMOptions(max_tokens=16, temperature=0),
    ).strip()
    if not result:
        raise RuntimeError("LLM provider returned an empty response")
    return result


def detect_llm_profile(endpoint: str, api_key: str, model: str) -> tuple[dict, str, list[str]]:
    """
    Try common provider protocols and return the first working profile.

    Args:
        endpoint: User-entered endpoint/base URL.
        api_key: API key.
        model: Model name or Azure deployment name.

    Returns:
        (profile, probe_response, errors)

    Raises:
        RuntimeError: when no candidate works. The error message includes
        per-provider details so the UI can show an actionable failure.
    """
    candidates = _build_detection_candidates(endpoint, api_key, model)
    errors: list[str] = []

    for label, profile in candidates:
        try:
            response = validate_llm_profile(profile)
            return profile, response, errors
        except Exception as e:
            errors.append(f"{label}: {e}")

    detail = "\n".join(errors) if errors else "没有可测试的候选 API 类型"
    raise RuntimeError(f"没有找到可用的润色 API。\n\n{detail}")


def list_llm_models(endpoint: str, api_key: str) -> tuple[list[str], list[str]]:
    """
    Try to fetch model/deployment names from a user-entered endpoint.

    OpenAI-compatible endpoints usually expose GET /models. Azure OpenAI
    exposes deployments through /openai/deployments. Anthropic exposes
    /v1/models for accounts that have access to the models API.
    """
    endpoint = (endpoint or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    models: list[str] = []
    errors: list[str] = []

    if not endpoint:
        return [], ["Endpoint 为空"]

    for base_url in _openai_base_url_candidates(endpoint):
        try:
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            values = [item.get("id", "") for item in data.get("data", []) if item.get("id")]
            if values:
                models.extend(values)
                break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:200]
            errors.append(f"OpenAI-compatible {base_url}: HTTP {e.code} {detail}")
        except Exception as e:
            errors.append(f"OpenAI-compatible {base_url}: {e}")

    try:
        azure_url = f"{endpoint}/openai/deployments?api-version=2022-12-01"
        req = urllib.request.Request(azure_url, headers={"api-key": api_key})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        values = [item.get("id", "") for item in data.get("data", []) if item.get("id")]
        models.extend(values)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        errors.append(f"Azure OpenAI deployments: HTTP {e.code} {detail}")
    except Exception as e:
        errors.append(f"Azure OpenAI deployments: {e}")

    try:
        req = urllib.request.Request(
            f"{endpoint}/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": DEFAULT_ANTHROPIC_VERSION,
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        values = [item.get("id", "") for item in data.get("data", []) if item.get("id")]
        models.extend(values)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        errors.append(f"Anthropic models: HTTP {e.code} {detail}")
    except Exception as e:
        errors.append(f"Anthropic models: {e}")

    deduped = list(dict.fromkeys(models))
    return deduped, errors


def _infer_profile_provider(profile: dict) -> str:
    provider = str(profile.get("provider") or "").strip()
    if provider and provider != "auto":
        return provider
    endpoint = _profile_endpoint(profile).lower()
    if "anthropic" in endpoint:
        return "anthropic"
    if "openai.azure" in endpoint or ".azure.com" in endpoint:
        return "azure_openai"
    return "openai_compatible"


def _profile_endpoint(profile: dict) -> str:
    return str(profile.get("endpoint") or profile.get("base_url") or "").strip()


def _profile_model(profile: dict) -> str:
    return str(profile.get("model") or profile.get("deployment") or "").strip()


def _resolve_api_key(profile: dict) -> str:
    """Resolve API key with env-var priority."""
    env_name = profile.get("api_key_env", "")
    if env_name:
        value = os.environ.get(env_name)
        if value:
            log.info("使用环境变量 %s 作为 %s API Key", env_name, profile.get("provider", "LLM"))
            return value
    return profile.get("api_key", "")


def _build_detection_candidates(endpoint: str, api_key: str, model: str) -> list[tuple[str, dict]]:
    endpoint = (endpoint or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    endpoint_l = endpoint.lower()

    candidates: list[tuple[str, dict]] = []

    def add_openai():
        for base_url in _openai_base_url_candidates(endpoint):
            candidates.append((
                f"OpenAI-compatible ({base_url})",
                {
                    "provider": "openai_compatible",
                    "endpoint": base_url,
                    "base_url": base_url,
                    "api_key": api_key,
                    "model": model,
                    "timeout": 20,
                    "max_retries": 0,
                },
            ))

    def add_anthropic():
        candidates.append((
            "Anthropic Messages API",
            {
                "provider": "anthropic",
                "endpoint": endpoint or "https://api.anthropic.com",
                "base_url": endpoint or "https://api.anthropic.com",
                "api_key": api_key,
                "api_version": DEFAULT_ANTHROPIC_VERSION,
                "model": model,
                "timeout": 20,
                "max_retries": 0,
            },
        ))

    def add_azure():
        candidates.append((
            "Azure OpenAI",
            {
                "provider": "azure_openai",
                "endpoint": endpoint,
                "api_key": api_key,
                "api_version": DEFAULT_AZURE_API_VERSION,
                "model": model,
                "deployment": model,
                "timeout": 20,
                "max_retries": 0,
            },
        ))

    if "anthropic" in endpoint_l:
        add_anthropic()
        add_openai()
        add_azure()
    elif "openai.azure" in endpoint_l or ".azure.com" in endpoint_l:
        add_azure()
        add_openai()
        add_anthropic()
    else:
        add_openai()
        add_anthropic()
        add_azure()

    seen = set()
    unique = []
    for label, profile in candidates:
        key = (
            profile.get("provider"),
            profile.get("base_url") or profile.get("endpoint"),
            profile.get("model") or profile.get("deployment"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, profile))
    return unique


def _openai_base_url_candidates(endpoint: str) -> list[str]:
    endpoint = (endpoint or DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")
    candidates = [endpoint]
    if not endpoint.endswith("/v1"):
        candidates.append(f"{endpoint}/v1")
    return candidates


def _extract_anthropic_text(data: dict) -> str:
    """Extract concatenated text blocks from an Anthropic Messages response."""
    parts = []
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)
