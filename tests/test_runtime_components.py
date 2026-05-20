"""
runtime_components 模块的单元测试

验证 GUI 和测试模式共用的组件工厂，不触发真实 API 或模型加载。
"""

from unittest.mock import MagicMock, patch

from src.runtime_components import (
    create_polisher,
    create_recorder,
    create_runtime_components,
    create_transcriber_runtime,
)


def test_create_recorder_uses_recording_config():
    recorder = create_recorder({
        "sample_rate": 44100,
        "channels": 2,
        "max_duration": 30,
    })

    assert recorder.sample_rate == 44100
    assert recorder.channels == 2
    assert recorder.max_duration == 30


def test_create_transcriber_runtime_local():
    with patch("src.model_manager.is_model_ready", return_value=True), \
         patch("src.model_manager.get_model_dir", return_value="models/sense_voice"), \
         patch("src.local_transcriber.LocalTranscriber") as transcriber_cls:
        fake_transcriber = MagicMock()
        transcriber_cls.return_value = fake_transcriber

        runtime = create_transcriber_runtime(
            stt_cfg={"backend": "local", "model_type": "sense_voice", "num_threads": 4},
            language="zh",
        )

    transcriber_cls.assert_called_once_with(
        model_dir="models/sense_voice",
        model_type="sense_voice",
        num_threads=4,
        language="zh",
    )
    assert runtime.transcriber is fake_transcriber
    assert runtime.is_streaming_mode is False
    assert runtime.streaming_transcriber is None


def test_create_polisher_uses_selected_profile():
    config = {
        "polish": {"profile": "claude"},
        "llm_profiles": {
            "claude": {
                "provider": "anthropic",
                "api_key": "key",
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 512,
                "temperature": 0.2,
            }
        },
    }
    polish_cfg = {
        "profile": "claude",
        "system_prompt": "",
        "translate_to": "",
        "show_original": False,
    }

    with patch("src.runtime_components.create_llm_client", return_value=MagicMock()) as factory:
        polisher = create_polisher(config, polish_cfg)

    factory.assert_called_once()
    assert polisher.max_tokens == 512
    assert polisher.temperature == 0.2


def test_create_runtime_components_skips_polisher_when_disabled():
    config = {
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
        "polish": {
            "enabled": False,
            "language": "zh",
        },
    }

    with patch("src.model_manager.is_model_ready", return_value=True), \
         patch("src.model_manager.get_model_dir", return_value="models/sense_voice"), \
         patch("src.local_transcriber.LocalTranscriber", return_value=MagicMock()):
        components = create_runtime_components(config)

    assert components.polisher is None
    assert components.polish_cfg["enabled"] is False
    assert components.transcriber_runtime.transcriber is components.transcriber
