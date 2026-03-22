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
    支持通过环境变量覆盖 Azure API 配置，避免在文件中存当敏感信息。

    环境变量优先级高于 config.yaml：
    - AZURE_OPENAI_ENDPOINT  → azure.endpoint
    - AZURE_OPENAI_API_KEY   → azure.api_key

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

    # 环境变量覆盖：优先级高于配置文件，适合 CI/CD 和安全敏感场景
    import os
    azure = config.setdefault("azure", {})
    env_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    env_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    if env_endpoint:
        azure["endpoint"] = env_endpoint
        log.info("使用环境变量 AZURE_OPENAI_ENDPOINT 覆盖配置")
    if env_api_key:
        azure["api_key"] = env_api_key
        log.info("使用环境变量 AZURE_OPENAI_API_KEY 覆盖配置")

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
    # 基本验证：根据 STT 后端和润色开关决定哪些 Azure 字段必填
    stt_cfg = get_stt_config(config_dict)
    azure = config_dict.get("azure", {})
    polish = config_dict.get("polish", {})
    is_local = stt_cfg["backend"] == "local"
    polish_enabled = polish.get("enabled", True)

    if is_local and not polish_enabled:
        # 完全离线模式：不需要任何 Azure 配置
        pass
    elif is_local and polish_enabled:
        # 本地转写 + 云端润色：需要 endpoint、api_key、gpt_deployment
        if not azure.get("endpoint", "").strip():
            raise ValueError("Azure 端点 URL 不能为空（润色功能需要）")
        if not azure.get("api_key", "").strip():
            raise ValueError("Azure API Key 不能为空（润色功能需要）")
        if not azure.get("gpt_deployment", "").strip():
            raise ValueError("润色模型部署名不能为空")
    else:
        # Azure 云端模式：所有字段必填
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

    根据 STT 后端和润色开关决定哪些 Azure 字段必填：
    - azure 模式：所有 Azure 字段必填（与之前一致）
    - local + 润色开：需要 endpoint、api_key、gpt_deployment
    - local + 润色关：不需要任何 Azure 配置（完全离线）

    Args:
        config: 从 YAML 加载的配置字典

    Raises:
        SystemExit: 当必要配置缺失时
    """
    stt_cfg = get_stt_config(config)
    polish_cfg = config.get("polish", {})
    is_local = stt_cfg["backend"] == "local"
    polish_enabled = polish_cfg.get("enabled", True)

    # 确定需要验证的 Azure 字段
    if is_local and not polish_enabled:
        # 完全离线模式：不需要任何 Azure 配置
        required_fields = []
    elif is_local and polish_enabled:
        # 本地转写 + 云端润色
        required_fields = [
            ("azure.endpoint", ["azure", "endpoint"]),
            ("azure.api_key", ["azure", "api_key"]),
            ("azure.gpt_deployment", ["azure", "gpt_deployment"]),
        ]
    else:
        # Azure 云端模式：所有字段必填
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
            # 首次启动时跳过验证（由 run.py 标记），让程序启动后打开设置窗口
            import builtins
            if getattr(builtins, "_VOX_NEED_SETUP", False):
                log.warning("配置未填写: %s — 将在启动后打开设置窗口", field_name)
                return  # 不退出，让程序继续启动
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
        dict: 包含 enabled, language, system_prompt, translate_to
    """
    polish = config.get("polish", {})
    return {
        "enabled": polish.get("enabled", True),
        "language": polish.get("language", "zh"),
        "system_prompt": polish.get("system_prompt", ""),
        "translate_to": polish.get("translate_to", ""),
        "show_original": polish.get("show_original", False),
    }


def get_stt_config(config):
    """
    从配置字典中提取 STT 后端配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 backend, model_type, num_threads
              - backend: "azure"（云端）或 "local"（本地离线）
              - model_type: 本地模型类型（sense_voice 或 whisper_small）
              - num_threads: 本地推理线程数
    """
    stt = config.get("stt", {})
    return {
        "backend": stt.get("backend", "azure"),
        "model_type": stt.get("model_type", "sense_voice"),
        "num_threads": stt.get("num_threads", 4),
    }
