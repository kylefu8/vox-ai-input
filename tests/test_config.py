"""
config 模块的单元测试

测试配置加载、验证、各配置项提取函数。
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from src.config import (
    load_config,
    save_config,
    _validate_config,
    get_history_config,
    get_llm_profile_config,
    get_llm_profiles,
    get_recording_config,
    get_hotkey_config,
    get_polish_config,
    get_ui_config,
    get_floating_control_config,
    get_preview_overlay_config,
)


def _valid_llm_profiles():
    return {
        "azure": {
            "provider": "azure_openai",
            "endpoint": "https://test.openai.azure.com/",
            "api_key": "real-key-abc123",
            "api_version": "2025-01-01-preview",
            "deployment": "gpt-5.4-mini",
        }
    }


class TestValidateConfig:
    """配置验证逻辑的测试。"""

    def test_valid_config_passes(self):
        """完整合法的配置应该通过验证。"""
        config = {
            "stt": {"backend": "local", "model_type": "sense_voice"},
            "polish": {"enabled": True, "profile": "azure"},
            "llm_profiles": _valid_llm_profiles(),
        }
        # 不应抛出异常
        _validate_config(config)

    def test_no_cloud_config_passes_when_polish_disabled(self):
        """只用本地转写且关闭润色时，不需要任何云端配置。"""
        config = {"stt": {"backend": "local"}, "polish": {"enabled": False}}
        _validate_config(config)

    def test_missing_llm_profile_exits_when_polish_enabled(self):
        """启用润色但缺少 profile 时应该退出。"""
        config = {"stt": {"backend": "local"}, "polish": {"enabled": True, "profile": "missing"}}
        with pytest.raises(SystemExit):
            _validate_config(config)


class TestGetRecordingConfig:
    """录音配置提取的测试。"""

    def test_extracts_values(self):
        """应该正确提取录音配置。"""
        config = {
            "recording": {
                "sample_rate": 44100,
                "channels": 2,
                "max_duration": 120,
            }
        }
        result = get_recording_config(config)
        assert result["sample_rate"] == 44100
        assert result["channels"] == 2
        assert result["max_duration"] == 120

    def test_default_values(self):
        """缺少录音配置时应返回默认值。"""
        result = get_recording_config({})
        assert result["sample_rate"] == 16000
        assert result["channels"] == 1
        assert result["max_duration"] == 60


class TestGetHotkeyConfig:
    """热键配置提取的测试。"""

    def test_extracts_combination(self):
        """应该正确提取热键组合。"""
        config = {"hotkey": {"combination": "alt+shift+a"}}
        result = get_hotkey_config(config)
        assert result["combination"] == "alt+shift+a"

    def test_default_combination(self):
        """缺少热键配置时应返回默认组合。"""
        result = get_hotkey_config({})
        assert result["combination"] == "ctrl+shift+space"


class TestGetPolishConfig:
    """润色配置提取的测试。"""

    def test_extracts_values(self):
        """应该正确提取润色配置。"""
        config = {"polish": {"enabled": False, "language": "en"}}
        result = get_polish_config(config)
        assert result["enabled"] is False
        assert result["language"] == "en"

    def test_default_values(self):
        """缺少润色配置时应返回默认值。"""
        result = get_polish_config({})
        assert result["enabled"] is False
        assert result["language"] == ""

    def test_profile_defaults_to_default(self):
        """缺少 profile 时默认使用 default。"""
        result = get_polish_config({})
        assert result["profile"] == "default"


class TestGetHistoryConfig:
    """历史记录配置提取的测试。"""

    def test_defaults(self):
        result = get_history_config({})
        assert result["enabled"] is True
        assert result["max_entries"] == 100
        assert result["path"] == ""

    def test_extracts_values(self):
        result = get_history_config({
            "history": {
                "enabled": False,
                "max_entries": 25,
                "path": "custom-history.jsonl",
            }
        })
        assert result["enabled"] is False
        assert result["max_entries"] == 25
        assert result["path"] == "custom-history.jsonl"


class TestGetUIConfig:
    """界面偏好配置提取测试。"""

    def test_defaults(self):
        result = get_ui_config({})
        assert result["language"] == "zh-CN"
        assert result["theme"] == "dark"

    def test_extracts_and_normalizes_values(self):
        result = get_ui_config({"ui": {"language": "en-US", "theme": "LIGHT"}})
        assert result["language"] == "en"
        assert result["theme"] == "light"

    def test_invalid_theme_falls_back_to_dark(self):
        result = get_ui_config({"ui": {"language": "zh", "theme": "purple"}})
        assert result["language"] == "zh-CN"
        assert result["theme"] == "dark"


class TestGetFloatingControlConfig:
    """悬浮录音按钮配置提取测试。"""

    def test_defaults(self):
        result = get_floating_control_config({})
        assert result["enabled"] is True
        assert result["x"] is None
        assert result["y"] is None

    def test_extracts_values(self):
        result = get_floating_control_config({
            "ui": {
                "floating_control": {
                    "enabled": False,
                    "x": "120",
                    "y": 240,
                }
            }
        })
        assert result["enabled"] is False
        assert result["x"] == 120
        assert result["y"] == 240


class TestGetPreviewOverlayConfig:
    """结果预览胶囊配置提取测试。"""

    def test_defaults_to_enabled(self):
        result = get_preview_overlay_config({})
        assert result["enabled"] is True

    def test_extracts_enabled(self):
        result = get_preview_overlay_config({
            "ui": {
                "preview_overlay": {
                    "enabled": False,
                }
            }
        })
        assert result["enabled"] is False


class TestGetLLMProfileConfig:
    """LLM profile 配置提取的测试。"""

    def test_missing_profile_raises(self):
        """polish.profile 不存在时应该明确报错。"""
        config = {"polish": {"profile": "missing"}, "llm_profiles": _valid_llm_profiles()}
        with pytest.raises(ValueError, match="找不到 LLM profile"):
            get_llm_profile_config(config)

    def test_named_azure_profile(self):
        """应该按名称提取 Azure profile。"""
        config = {"polish": {"profile": "azure"}, "llm_profiles": _valid_llm_profiles()}
        result = get_llm_profile_config(config)
        assert result["provider"] == "azure_openai"
        assert result["deployment"] == "gpt-5.4-mini"

    def test_named_anthropic_profile(self):
        """应该按名称提取 Anthropic profile。"""
        config = {
            "polish": {"profile": "claude"},
            "llm_profiles": {
                "claude": {
                    "provider": "anthropic",
                    "api_key_env": "ANTHROPIC_API_KEY",
                    "model": "claude-3-5-haiku-20241022",
                }
            },
        }
        result = get_llm_profile_config(config)
        assert result["name"] == "claude"
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-3-5-haiku-20241022"

    def test_get_llm_profiles_returns_explicit_profiles_only(self):
        """只返回配置中显式声明的 profiles。"""
        profiles = get_llm_profiles({"llm_profiles": _valid_llm_profiles()})
        assert list(profiles.keys()) == ["azure"]
        assert get_llm_profiles({"azure": {"endpoint": "x"}}) == {}


class TestLoadConfig:
    """配置文件加载的测试。"""

    def test_missing_file_exits(self):
        """配置文件不存在时应该退出。"""
        with patch("src.config.CONFIG_PATH", Path("/nonexistent/config.yaml")):
            with pytest.raises(SystemExit):
                load_config()

    def test_valid_file_loads(self, tmp_path):
        """合法的配置文件应该正确加载。"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "stt:\n"
            "  backend: local\n"
            "  model_type: sense_voice\n"
            "polish:\n"
            "  profile: azure\n"
            "llm_profiles:\n"
            "  azure:\n"
            "    provider: azure_openai\n"
            "    endpoint: https://test.openai.azure.com/\n"
            "    api_key: real-key-123\n"
            "    deployment: gpt-5.4-mini\n",
            encoding="utf-8",
        )
        with patch("src.config.CONFIG_PATH", config_file):
            config = load_config()
            assert config["stt"]["backend"] == "local"

    def test_invalid_yaml_exits(self, tmp_path):
        """格式错误的 YAML 应该退出。"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content: [[[", encoding="utf-8")
        with patch("src.config.CONFIG_PATH", config_file):
            with pytest.raises(SystemExit):
                load_config()


class TestSaveConfig:
    """配置保存的测试。"""

    VALID_CONFIG = {
        "stt": {
            "backend": "local",
            "model_type": "sense_voice",
            "num_threads": 4,
            "streaming": False,
        },
        "recording": {
            "sample_rate": 16000,
            "channels": 1,
            "max_duration": 60,
        },
        "hotkey": {
            "combination": "ctrl+shift+space",
        },
        "polish": {
            "enabled": True,
            "language": "zh",
            "profile": "azure",
        },
        "llm_profiles": _valid_llm_profiles(),
    }

    def test_saves_valid_config(self, tmp_path):
        """合法配置应该成功保存。"""
        import yaml

        config_file = tmp_path / "config.yaml"
        with patch("src.config.CONFIG_PATH", config_file):
            result = save_config(self.VALID_CONFIG)

        assert result is True
        assert config_file.exists()

        # 验证写入的内容可以被读回
        with open(config_file, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        assert loaded["stt"]["backend"] == "local"
        assert loaded["llm_profiles"]["azure"]["api_key"] == "real-key-abc123"

    def test_missing_endpoint_raises(self):
        """缺少当前 Azure LLM profile endpoint 应抛出 ValueError。"""
        config = {
            "polish": {"enabled": True, "profile": "azure"},
            "llm_profiles": {
                "azure": {
                    "provider": "azure_openai",
                    "endpoint": "",
                    "api_key": "key",
                    "deployment": "gpt-5.4-mini",
                }
            },
        }
        with pytest.raises(ValueError, match="Endpoint"):
            save_config(config)

    def test_missing_api_key_raises(self):
        """缺少当前 LLM profile api_key 应抛出 ValueError。"""
        config = {
            "polish": {"enabled": True, "profile": "azure"},
            "llm_profiles": {
                "azure": {
                    "provider": "azure_openai",
                    "endpoint": "https://test.openai.azure.com/",
                    "api_key": "  ",
                    "deployment": "gpt-5.4-mini",
                }
            },
        }
        with pytest.raises(ValueError, match="API Key"):
            save_config(config)

    def test_missing_llm_deployment_raises(self):
        """缺少当前 LLM profile 部署名应抛出 ValueError。"""
        config = {
            "polish": {"enabled": True, "profile": "azure"},
            "llm_profiles": {
                "azure": {
                    "provider": "azure_openai",
                    "endpoint": "https://test.openai.azure.com/",
                    "api_key": "key",
                    "deployment": "",
                }
            },
        }
        with pytest.raises(ValueError, match="模型名|profile"):
            save_config(config)

    def test_saves_simplified_generic_llm_profile(self, tmp_path):
        """简化后的 endpoint/api_key/model profile 可以直接保存。"""
        config = {
            "polish": {"enabled": True, "profile": "default"},
            "llm_profiles": {
                "default": {
                    "provider": "auto",
                    "endpoint": "https://api.example.com/v1",
                    "api_key": "key",
                    "model": "model-a",
                }
            },
        }
        config_file = tmp_path / "config.yaml"

        with patch("src.config.CONFIG_PATH", config_file):
            result = save_config(config)

        assert result is True

    def test_saves_openai_responses_llm_profile(self, tmp_path):
        """Responses API 类型也应作为合法 profile 保存。"""
        config = {
            "polish": {"enabled": True, "profile": "default"},
            "llm_profiles": {
                "default": {
                    "provider": "openai_responses",
                    "endpoint": "https://api.example.com/v1",
                    "api_key": "key",
                    "model": "gpt-5.4-mini",
                }
            },
        }
        config_file = tmp_path / "config.yaml"

        with patch("src.config.CONFIG_PATH", config_file):
            result = save_config(config)

        assert result is True

    def test_write_error_returns_false(self, tmp_path):
        """写入失败应返回 False。"""
        # 使用不存在的目录路径模拟写入失败
        bad_path = tmp_path / "nonexistent_dir" / "config.yaml"
        with patch("src.config.CONFIG_PATH", bad_path):
            result = save_config(self.VALID_CONFIG)
        assert result is False
