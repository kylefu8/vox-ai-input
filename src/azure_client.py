"""
Azure OpenAI 客户端工厂

提供共享的 AzureOpenAI 客户端实例，供 Azure OpenAI 润色 profile 复用。
"""

import hashlib

import httpx
from openai import AzureOpenAI

from src.logger import setup_logger

log = setup_logger(__name__)

# 模块级客户端缓存
_client_cache = {}


def get_azure_client(endpoint, api_key, api_version, timeout=60.0, max_retries=0, transport=None):
    """
    获取一个 AzureOpenAI 客户端实例（同配置复用）。

    相同 (endpoint, api_key, api_version, timeout, max_retries) 组合
    会复用已有客户端，避免重复创建。

    Args:
        endpoint: Azure OpenAI 服务端点 URL
        api_key: Azure OpenAI API Key
        api_version: API 版本号
        timeout: 请求超时秒数
        max_retries: 失败自动重试次数

    Returns:
        AzureOpenAI 客户端实例
    """
    # 对 api_key 取哈希后作为缓存 key，避免明文常驻内存
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    transport_key = _transport_cache_key(transport)
    cache_key = (endpoint, key_hash, api_version, timeout, max_retries, transport_key)

    if cache_key in _client_cache:
        log.debug("复用已有的 Azure OpenAI 客户端")
        return _client_cache[cache_key]

    kwargs = {
        "azure_endpoint": endpoint,
        "api_key": api_key,
        "api_version": api_version,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    if _needs_custom_http_client(transport):
        headers = {}
        host_header = str(getattr(transport, "host_header", "") or "").strip()
        if host_header:
            headers["Host"] = host_header
        kwargs["http_client"] = httpx.Client(
            verify=_httpx_verify_value(transport),
            headers=headers or None,
            timeout=timeout,
        )

    client = AzureOpenAI(**kwargs)

    _client_cache[cache_key] = client
    log.info("创建新的 Azure OpenAI 客户端（端点: %s）", endpoint)
    return client


def _transport_cache_key(transport):
    if transport is None:
        return (False, "")
    return (
        bool(getattr(transport, "allow_insecure_tls", False)),
        str(getattr(transport, "host_header", "") or ""),
    )


def _httpx_verify_value(transport):
    if transport is not None and bool(getattr(transport, "allow_insecure_tls", False)):
        return False
    return True


def _needs_custom_http_client(transport) -> bool:
    if transport is None:
        return False
    return (
        bool(getattr(transport, "allow_insecure_tls", False))
        or bool(str(getattr(transport, "host_header", "") or ""))
    )
