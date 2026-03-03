"""
config 模块的单元测试

测试配置加载、验证、各配置项提取函数。
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.config import (
    load_config,
    _validate_config,
    get_azure_config,
    get_recording_config,
    get_hotkey_config,
    get_polish_config,
)


class TestValidateConfig:
    """配置验证逻辑的测试。"""

    def test_valid_config_passes(self):
        """完整合法的配置应该通过验证。"""
        config = {
            "azure": {
                "endpoint": "https://test.openai.azure.com/",
                "api_key": "real-key-abc123",
                "whisper_deployment": "whisper",
                "gpt_deployment": "gpt-4o-mini",
            }
        }
        # 不应抛出异常
        _validate_config(config)

    def test_missing_azure_section_exits(self):
        """缺少 azure 整个配置段应该退出。"""
        config = {"recording": {"sample_rate": 16000}}
        with pytest.raises(SystemExit):
            _validate_config(config)

    def test_missing_api_key_exits(self):
        """缺少 api_key 应该退出。"""
        config = {
            "azure": {
                "endpoint": "https://test.openai.azure.com/",
                "whisper_deployment": "whisper",
                "gpt_deployment": "gpt-4o-mini",
            }
        }
        with pytest.raises(SystemExit):
            _validate_config(config)

    def test_placeholder_value_exits(self):
        """占位符值应该被检测出来并退出。"""
        config = {
            "azure": {
                "endpoint": "https://your-resource.openai.azure.com/",
                "api_key": "your-api-key-here",
                "whisper_deployment": "whisper",
                "gpt_deployment": "gpt-4o-mini",
            }
        }
        with pytest.raises(SystemExit):
            _validate_config(config)

    def test_empty_value_exits(self):
        """空字符串值应该退出。"""
        config = {
            "azure": {
                "endpoint": "",
                "api_key": "real-key",
                "whisper_deployment": "whisper",
                "gpt_deployment": "gpt-4o-mini",
            }
        }
        with pytest.raises(SystemExit):
            _validate_config(config)


class TestGetAzureConfig:
    """Azure 配置提取的测试。"""

    def test_extracts_all_fields(self):
        """应该正确提取所有 Azure 字段。"""
        config = {
            "azure": {
                "endpoint": "https://test.openai.azure.com/",
                "api_key": "test-key",
                "api_version": "2024-06-01",
                "whisper_deployment": "whisper",
                "gpt_deployment": "gpt-4o-mini",
            }
        }
        result = get_azure_config(config)
        assert result["endpoint"] == "https://test.openai.azure.com/"
        assert result["api_key"] == "test-key"
        assert result["api_version"] == "2024-06-01"
        assert result["whisper_deployment"] == "whisper"
        assert result["gpt_deployment"] == "gpt-4o-mini"

    def test_default_values(self):
        """缺少的可选字段应该使用默认值。"""
        config = {"azure": {}}
        result = get_azure_config(config)
        assert result["api_version"] == "2024-06-01"
        assert result["whisper_deployment"] == "whisper"
        assert result["gpt_deployment"] == "gpt-4o-mini"

    def test_empty_config(self):
        """完全空的配置应该返回全默认值，不崩溃。"""
        result = get_azure_config({})
        assert result["endpoint"] == ""
        assert result["api_key"] == ""


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
        assert result["enabled"] is True
        assert result["language"] == "zh"


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
            "azure:\n"
            "  endpoint: https://test.openai.azure.com/\n"
            "  api_key: real-key-123\n"
            "  whisper_deployment: whisper\n"
            "  gpt_deployment: gpt-4o-mini\n",
            encoding="utf-8",
        )
        with patch("src.config.CONFIG_PATH", config_file):
            config = load_config()
            assert config["azure"]["endpoint"] == "https://test.openai.azure.com/"

    def test_invalid_yaml_exits(self, tmp_path):
        """格式错误的 YAML 应该退出。"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content: [[[", encoding="utf-8")
        with patch("src.config.CONFIG_PATH", config_file):
            with pytest.raises(SystemExit):
                load_config()
