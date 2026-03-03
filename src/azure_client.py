"""
Azure OpenAI 客户端工厂

提供共享的 AzureOpenAI 客户端实例，避免 Transcriber 和 Polisher 各自重复创建。
"""

from openai import AzureOpenAI

from src.logger import setup_logger

log = setup_logger(__name__)

# 模块级客户端缓存
_client_cache = {}


def get_azure_client(endpoint, api_key, api_version, timeout=60.0, max_retries=2):
    """
    获取一个 AzureOpenAI 客户端实例（同配置复用）。

    相同 endpoint+api_key 的组合会复用已有客户端，避免重复创建。

    Args:
        endpoint: Azure OpenAI 服务端点 URL
        api_key: Azure OpenAI API Key
        api_version: API 版本号
        timeout: 请求超时秒数
        max_retries: 失败自动重试次数

    Returns:
        AzureOpenAI 客户端实例
    """
    cache_key = (endpoint, api_key, api_version)

    if cache_key in _client_cache:
        log.info("复用已有的 Azure OpenAI 客户端")
        return _client_cache[cache_key]

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        timeout=timeout,
        max_retries=max_retries,
    )

    _client_cache[cache_key] = client
    log.info("创建新的 Azure OpenAI 客户端（端点: %s）", endpoint)
    return client
