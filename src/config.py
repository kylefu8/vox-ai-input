"""
配置加载与保存模块

从 config.yaml 读取 Azure API 和其他配置项。
如果 config.yaml 不存在，会提示用户从 config.example.yaml 复制。
支持通过设置 UI 将修改后的配置写回 config.yaml。
"""

import sys
from pathlib import Path

import yaml

from src.logger import setup_logger
from src.paths import get_project_root

log = setup_logger(__name__)

# 项目根目录（打包模式下为 exe 所在目录，脚本模式下为代码根目录）
PROJECT_ROOT = get_project_root()
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def load_config():
    """
    加载并返回配置字典。

    从项目根目录的 config.yaml 读取配置。
    如果文件不存在，打印提示信息并退出程序。

    Returns:
        dict: 包含所有配置项的字典

    Raises:
        SystemExit: 当 config.yaml 不存在或格式错误时
    """
    if not CONFIG_PATH.exists():
        log.error("找不到配置文件: %s", CONFIG_PATH)
        log.error("请复制 config.example.yaml 为 config.yaml，并填入你的 Azure API 信息：")
        log.error("  macOS/Linux: cp config.example.yaml config.yaml")
        log.error("  Windows:     copy config.example.yaml config.yaml")
        sys.exit(1)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        log.error("配置文件格式错误: %s", e)
        sys.exit(1)
    except OSError as e:
        log.error("无法读取配置文件: %s", e)
        sys.exit(1)

    # 验证必要的配置项是否存在
    _validate_config(config)

    log.info("配置加载成功")
    return config


def save_config(config_dict):
    """
    将配置字典写回 config.yaml。

    会覆盖整个文件（PyYAML 无法保留注释）。
    写入前做基本验证：azure 必填字段不能为空。

    Args:
        config_dict: 完整的配置字典

    Returns:
        bool: 是否保存成功

    Raises:
        ValueError: 当必填字段为空时
    """
    # 基本验证
    azure = config_dict.get("azure", {})
    if not azure.get("endpoint", "").strip():
        raise ValueError("Azure 端点 URL 不能为空")
    if not azure.get("api_key", "").strip():
        raise ValueError("Azure API Key 不能为空")
    if not azure.get("whisper_deployment", "").strip():
        raise ValueError("转写模型部署名不能为空")
    if not azure.get("gpt_deployment", "").strip():
        raise ValueError("润色模型部署名不能为空")

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(
                config_dict,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        log.info("配置已保存到 %s", CONFIG_PATH)
        return True
    except OSError as e:
        log.error("保存配置文件失败: %s", e)
        return False


# config.example.yaml 中已知的占位符值，精确匹配避免误判
_PLACEHOLDER_VALUES = {
    "https://your-resource.openai.azure.com/",
    "your-api-key-here",
}


def _validate_config(config):
    """
    验证配置字典中的必要字段是否存在且不为空。

    Args:
        config: 从 YAML 加载的配置字典

    Raises:
        SystemExit: 当必要配置缺失时
    """
    required_fields = [
        ("azure.endpoint", ["azure", "endpoint"]),
        ("azure.api_key", ["azure", "api_key"]),
        ("azure.whisper_deployment", ["azure", "whisper_deployment"]),
        ("azure.gpt_deployment", ["azure", "gpt_deployment"]),
    ]

    for field_name, keys in required_fields:
        value = config
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                log.error("配置缺失: %s — 请检查 config.yaml", field_name)
                sys.exit(1)
            value = value[key]

        str_value = str(value).strip()
        if not value or str_value == "" or str_value in _PLACEHOLDER_VALUES:
            log.error("配置未填写: %s — 请在 config.yaml 中填入实际值", field_name)
            sys.exit(1)


def get_azure_config(config):
    """
    从配置字典中提取 Azure 相关配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 endpoint, api_key, api_version, whisper_deployment, gpt_deployment
    """
    azure = config.get("azure", {})
    return {
        "endpoint": azure.get("endpoint", ""),
        "api_key": azure.get("api_key", ""),
        "api_version": azure.get("api_version", "2024-06-01"),
        "whisper_deployment": azure.get("whisper_deployment", "whisper"),
        "gpt_deployment": azure.get("gpt_deployment", "gpt-4o-mini"),
    }


def get_recording_config(config):
    """
    从配置字典中提取录音相关配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 sample_rate, channels, max_duration
    """
    recording = config.get("recording", {})
    return {
        "sample_rate": recording.get("sample_rate", 16000),
        "channels": recording.get("channels", 1),
        "max_duration": recording.get("max_duration", 60),
    }


def get_hotkey_config(config):
    """
    从配置字典中提取热键相关配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 combination
    """
    hotkey = config.get("hotkey", {})
    return {
        "combination": hotkey.get("combination", "ctrl+shift+space"),
    }


def get_polish_config(config):
    """
    从配置字典中提取润色相关配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 enabled, language
    """
    polish = config.get("polish", {})
    return {
        "enabled": polish.get("enabled", True),
        "language": polish.get("language", "zh"),
    }
