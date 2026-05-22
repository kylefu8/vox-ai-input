"""
配置加载与保存模块

从 config.yaml 读取本地转写、润色 API 和其他配置项。
如果 config.yaml 不存在，会提示用户从 config.example.yaml 复制。
支持通过设置 UI 将修改后的配置写回 config.yaml。
"""

import sys
from pathlib import Path

import yaml

from src.i18n import normalize_ui_language
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
        log.error("请复制 config.example.yaml 为 config.yaml，并按需配置润色 API：")
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
    写入前做基本验证：启用润色时当前 LLM profile 必须完整。

    Args:
        config_dict: 完整的配置字典

    Returns:
        bool: 是否保存成功

    Raises:
        ValueError: 当必填字段为空时
    """
    polish = config_dict.get("polish", {})
    polish_enabled = polish.get("enabled", False)

    if polish_enabled:
        _validate_llm_profile_for_save(config_dict)

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
    "your-openai-api-key-here",
    "your-anthropic-api-key-here",
}


def _validate_config(config):
    """
    验证配置字典中的必要字段是否存在且不为空。

    目前转写固定为本地模型；只有启用润色时才要求所选 LLM profile
    的必要字段完整。

    Args:
        config: 从 YAML 加载的配置字典

    Raises:
        SystemExit: 当必要配置缺失时
    """
    polish_cfg = config.get("polish", {})
    polish_enabled = polish_cfg.get("enabled", False)

    if polish_enabled:
        try:
            _validate_llm_profile_for_save(config)
        except ValueError as e:
            import builtins
            if getattr(builtins, "_VOX_NEED_SETUP", False):
                log.warning("润色配置未填写: %s — 将在启动后打开设置窗口", e)
                return
            log.error("润色配置未填写: %s", e)
            sys.exit(1)


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
        "enabled": polish.get("enabled", False),
        "language": polish.get("language", ""),
        "system_prompt": polish.get("system_prompt", ""),
        "translate_to": polish.get("translate_to", ""),
        "show_original": polish.get("show_original", False),
        "profile": polish.get("profile", "default"),
    }


def get_history_config(config):
    """
    从配置字典中提取历史记录配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 enabled, max_entries, path
    """
    history = config.get("history", {})
    return {
        "enabled": history.get("enabled", True),
        "max_entries": int(history.get("max_entries", 100)),
        "path": history.get("path", ""),
    }


def get_ui_config(config):
    """
    从配置字典中提取界面偏好。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 language, theme
    """
    ui = config.get("ui", {}) or {}
    theme = str(ui.get("theme", "dark")).strip().lower()
    if theme not in ("dark", "light"):
        theme = "dark"
    return {
        "language": normalize_ui_language(ui.get("language", "zh-CN")),
        "theme": theme,
    }


def _optional_int(value):
    """Return int(value) when possible, otherwise None."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_floating_control_config(config):
    """
    从配置字典中提取屏幕悬浮录音按钮配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 enabled, x, y
    """
    ui = config.get("ui", {}) or {}
    floating = ui.get("floating_control", {}) or {}
    return {
        "enabled": bool(floating.get("enabled", True)),
        "x": _optional_int(floating.get("x")),
        "y": _optional_int(floating.get("y")),
    }


def get_preview_overlay_config(config):
    """
    从配置字典中提取结果预览胶囊配置。

    预览胶囊用于展示流式转写中间文本、转写/润色状态和最终结果。
    视觉上与悬浮录音按钮保持一致，默认开启；需要极简模式时可关闭。
    """
    ui = config.get("ui", {}) or {}
    preview = ui.get("preview_overlay", {}) or {}
    return {
        "enabled": bool(preview.get("enabled", True)),
    }


def get_llm_profile_config(config, profile_name=None):
    """
    返回当前润色 LLM profile。

    Args:
        config: 完整配置字典
        profile_name: 指定 profile 名称；None 时使用 polish.profile

    Returns:
        dict: 规范化后的 profile，包含 name/provider/模型字段等
    """
    polish = config.get("polish", {})
    profiles = config.get("llm_profiles", {}) or {}
    name = profile_name or polish.get("profile") or "default"

    if name in profiles:
        profile = dict(profiles[name] or {})
        profile["name"] = name
        return profile

    raise ValueError(f"找不到 LLM profile: {name}")


def get_llm_profiles(config):
    """返回配置中显式声明的 LLM profiles。"""
    return dict(config.get("llm_profiles", {}) or {})


def _validate_llm_profile_for_save(config):
    """Raise ValueError when the selected polish LLM profile is incomplete."""
    profile = get_llm_profile_config(config)
    provider = _infer_llm_profile_provider(profile)
    name = profile.get("name", "default")

    def require(field, label):
        value = str(profile.get(field, "")).strip()
        if not value or value in _PLACEHOLDER_VALUES:
            raise ValueError(f"LLM profile「{name}」的{label}不能为空")
        return value

    def require_any(fields, label):
        for field in fields:
            value = str(profile.get(field, "")).strip()
            if value and value not in _PLACEHOLDER_VALUES:
                return value
        raise ValueError(f"LLM profile「{name}」的{label}不能为空")

    def require_key():
        import os
        env_name = str(profile.get("api_key_env", "")).strip()
        if env_name and os.environ.get(env_name):
            return
        value = str(profile.get("api_key", "")).strip()
        if not value or value in _PLACEHOLDER_VALUES:
            raise ValueError(f"LLM profile「{name}」的 API Key 不能为空")

    if provider == "azure_openai":
        require_any(("endpoint", "base_url"), "Endpoint")
        require_key()
        require_any(("model", "deployment"), "模型名")
    elif provider in ("openai_compatible", "openai_responses"):
        require_any(("endpoint", "base_url"), "Endpoint")
        require_key()
        require("model", "模型名")
    elif provider == "anthropic":
        require_any(("endpoint", "base_url"), "Endpoint")
        require_key()
        require("model", "模型名")
    else:
        raise ValueError(f"不支持的 LLM provider: {provider}")


def _infer_llm_profile_provider(profile):
    provider = str(profile.get("provider") or "").strip()
    if provider and provider != "auto":
        return provider
    endpoint = str(profile.get("endpoint") or profile.get("base_url") or "").lower()
    if "anthropic" in endpoint:
        return "anthropic"
    if "openai.azure" in endpoint or ".azure.com" in endpoint:
        return "azure_openai"
    return "openai_compatible"


def get_stt_config(config):
    """
    从配置字典中提取 STT 后端配置。

    Args:
        config: 完整的配置字典

    Returns:
        dict: 包含 backend, model_type, num_threads, streaming
              - backend: 固定为 "local"（本地离线）
              - model_type: 本地模型类型
              - num_threads: 本地推理线程数（设置窗口默认隐藏）
              - streaming: 是否启用流式（设置窗口按模型自动派生）
    """
    stt = config.get("stt", {})
    return {
        "backend": "local",
        "model_type": stt.get("model_type", "sense_voice"),
        "num_threads": stt.get("num_threads", 4),
        "streaming": stt.get("streaming", False),
    }
