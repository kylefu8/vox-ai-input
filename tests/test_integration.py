"""
集成测试

测试模块间的联动流程，验证 app.py 的完整工作流：
热键按下 → 录音 → 转写 → 润色 → 粘贴。

所有外部依赖（API、硬件）均使用 mock 替代。
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, mock_open

import pytest

import src.azure_client


@pytest.fixture(autouse=True)
def clear_client_cache():
    """每个测试前清除客户端缓存，避免测试间干扰。"""
    src.azure_client._client_cache.clear()
    yield
    src.azure_client._client_cache.clear()


# ---------- 测试配置 ----------

MOCK_CONFIG = {
    "azure": {
        "endpoint": "https://test.openai.azure.com/",
        "api_key": "test-key-12345",
        "api_version": "2024-06-01",
        "whisper_deployment": "whisper",
        "gpt_deployment": "gpt-4o-mini",
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
    },
}


def _make_app():
    """
    创建一个完全 mock 化的 AIInputApp 实例。

    mock 掉所有外部依赖：配置加载、Azure 客户端、提示音、托盘图标。
    """
    with patch("src.app.load_config", return_value=MOCK_CONFIG), \
         patch("src.azure_client.AzureOpenAI"), \
         patch("src.app.create_default_sounds"), \
         patch("src.app.TrayIcon") as mock_tray_cls:

        # TrayIcon mock
        mock_tray = MagicMock()
        mock_tray_cls.return_value = mock_tray

        from src.app import AIInputApp
        app = AIInputApp()

    return app


# =============================================================
# 完整流程测试：热键按下 → 录音 → 转写 → 润色 → 粘贴
# =============================================================

class TestFullPipeline:
    """测试完整的语音输入流水线。"""

    def test_hotkey_press_starts_recording(self):
        """按下热键应该开始录音。"""
        app = _make_app()

        with patch.object(app._recorder, "start", return_value=True) as mock_start, \
             patch("src.app.play_start_sound"):
            app._on_hotkey_press()
            mock_start.assert_called_once()

    def test_hotkey_press_sets_tray_recording(self):
        """按下热键应该将托盘图标设为录音状态。"""
        app = _make_app()

        with patch.object(app._recorder, "start", return_value=True), \
             patch("src.app.play_start_sound"):
            app._on_hotkey_press()
            app._tray.set_state.assert_called_with("recording")

    def test_hotkey_press_skipped_when_processing(self):
        """如果正在处理上一条语音，按下热键应该被忽略。"""
        app = _make_app()
        app._is_processing = True

        with patch.object(app._recorder, "start") as mock_start:
            app._on_hotkey_press()
            mock_start.assert_not_called()

    def test_hotkey_press_recovers_on_start_failure(self):
        """录音启动失败时，托盘应恢复为空闲状态。"""
        app = _make_app()

        with patch.object(app._recorder, "start", return_value=False), \
             patch("src.app.play_start_sound"):
            app._on_hotkey_press()
            app._tray.set_state.assert_called_with("idle")

    def test_hotkey_release_triggers_processing(self):
        """松开热键应该停止录音并启动后台处理。"""
        app = _make_app()

        # 模拟录音器处于录音状态
        with patch.object(type(app._recorder), "is_recording",
                          new_callable=PropertyMock, return_value=True), \
             patch.object(app._recorder, "stop",
                          return_value=Path("/tmp/test.wav")), \
             patch("src.app.play_stop_sound"), \
             patch("threading.Thread") as mock_thread_cls:

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            app._on_hotkey_release()

            app._recorder.stop.assert_called_once()
            mock_thread.start.assert_called_once()

    def test_hotkey_release_no_wav_resets_tray(self):
        """录音数据无效时，托盘应恢复为空闲状态。"""
        app = _make_app()

        with patch.object(type(app._recorder), "is_recording",
                          new_callable=PropertyMock, return_value=True), \
             patch.object(app._recorder, "stop", return_value=None), \
             patch("src.app.play_stop_sound"):

            app._on_hotkey_release()
            app._tray.set_state.assert_called_with("idle")

    def test_process_audio_full_pipeline(self, tmp_path):
        """完整流程：转写 → 润色 → 粘贴。"""
        app = _make_app()
        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake wav data")

        app._transcriber.transcribe = MagicMock(return_value="你好世界")
        app._polisher.polish = MagicMock(return_value="你好，世界。")

        with patch("src.app.paste_text") as mock_paste, \
             patch("src.app.cleanup_audio"):

            app._process_audio(wav_file)

            # 验证转写被调用
            app._transcriber.transcribe.assert_called_once_with(
                wav_file, language="zh"
            )
            # 验证润色被调用
            app._polisher.polish.assert_called_once_with("你好世界")
            # 验证粘贴被调用
            mock_paste.assert_called_once_with("你好，世界。")

    def test_process_audio_sets_tray_processing_then_idle(self, tmp_path):
        """处理过程中托盘应先设为处理中，完成后恢复空闲。"""
        app = _make_app()
        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake wav data")

        app._transcriber.transcribe = MagicMock(return_value="test")
        app._polisher.polish = MagicMock(return_value="test.")

        with patch("src.app.paste_text"), \
             patch("src.app.cleanup_audio"):
            app._process_audio(wav_file)

        # 检查 set_state 的调用顺序
        calls = [c[0][0] for c in app._tray.set_state.call_args_list]
        assert "processing" in calls
        assert calls[-1] == "idle"  # 最后一次应该是恢复空闲

    def test_process_audio_skips_polish_when_disabled(self, tmp_path):
        """润色关闭时应直接使用原始文字。"""
        app = _make_app()
        app._polish_enabled = False
        app._polisher = None

        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake wav data")

        app._transcriber.transcribe = MagicMock(return_value="你好世界")

        with patch("src.app.paste_text") as mock_paste, \
             patch("src.app.cleanup_audio"):
            app._process_audio(wav_file)
            mock_paste.assert_called_once_with("你好世界")

    def test_process_audio_empty_transcription_skips(self, tmp_path):
        """转写结果为空时应跳过后续步骤。"""
        app = _make_app()
        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake wav data")

        app._transcriber.transcribe = MagicMock(return_value=None)

        with patch("src.app.paste_text") as mock_paste, \
             patch("src.app.cleanup_audio"):
            app._process_audio(wav_file)
            mock_paste.assert_not_called()

    def test_process_audio_cleans_up_wav(self, tmp_path):
        """处理后应清理临时音频文件。"""
        app = _make_app()
        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake wav data")

        app._transcriber.transcribe = MagicMock(return_value="test")
        app._polisher.polish = MagicMock(return_value="test.")

        with patch("src.app.paste_text"), \
             patch("src.app.cleanup_audio") as mock_cleanup:
            app._process_audio(wav_file)
            mock_cleanup.assert_called_once_with(wav_file)

    def test_process_audio_resets_processing_flag_on_error(self, tmp_path):
        """处理出错时也应重置 _is_processing 标志。"""
        app = _make_app()
        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake wav data")

        app._transcriber.transcribe = MagicMock(
            side_effect=RuntimeError("boom")
        )

        with patch("src.app.cleanup_audio"):
            app._process_audio(wav_file)

        assert app._is_processing is False
        app._tray.set_state.assert_called_with("idle")


# =============================================================
# 取消录音测试
# =============================================================

class TestCancelFlow:
    """测试 Esc 取消录音的流程。"""

    def test_cancel_stops_recording_and_cleans_up(self, tmp_path):
        """取消录音应该停止录音、清理文件、恢复空闲。"""
        app = _make_app()
        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake wav data")

        with patch.object(type(app._recorder), "is_recording",
                          new_callable=PropertyMock, return_value=True), \
             patch.object(app._recorder, "stop",
                          return_value=wav_file), \
             patch("src.app.cleanup_audio") as mock_cleanup:

            app._on_cancel()

            app._recorder.stop.assert_called_once()
            mock_cleanup.assert_called_once_with(wav_file)
            app._tray.set_state.assert_called_with("idle")

    def test_cancel_when_not_recording_is_noop(self):
        """未在录音时按取消应该无动作。"""
        app = _make_app()

        with patch.object(type(app._recorder), "is_recording",
                          new_callable=PropertyMock, return_value=False), \
             patch.object(app._recorder, "stop") as mock_stop:

            app._on_cancel()
            mock_stop.assert_not_called()


# =============================================================
# cleanup_audio 模块级函数测试
# =============================================================

class TestCleanupAudio:
    """测试模块级 cleanup_audio 工具函数。"""

    def test_cleanup_deletes_file(self, tmp_path):
        """应该删除指定的文件。"""
        from src.transcriber import cleanup_audio

        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake")

        cleanup_audio(wav_file)
        assert not wav_file.exists()

    def test_cleanup_nonexistent_file_no_error(self, tmp_path):
        """删除不存在的文件应该不报错。"""
        from src.transcriber import cleanup_audio

        wav_file = tmp_path / "nonexistent.wav"
        cleanup_audio(wav_file)  # 不应该抛异常

    def test_transcriber_cleanup_delegates(self, tmp_path):
        """Transcriber.cleanup_audio() 应该委托给模块级函数。"""
        wav_file = tmp_path / "test.wav"
        wav_file.write_bytes(b"fake")

        with patch("src.azure_client.AzureOpenAI"):
            from src.transcriber import Transcriber
            t = Transcriber(
                endpoint="https://test.openai.azure.com/",
                api_key="test-key",
                api_version="2024-06-01",
                deployment="whisper",
            )

        t.cleanup_audio(wav_file)
        assert not wav_file.exists()


# =============================================================
# run.py _create_components() 测试
# =============================================================

class TestCreateComponents:
    """测试 run.py 的共享组件初始化函数。"""

    def test_creates_all_components(self):
        """应该返回 recorder, transcriber, polisher, polish_cfg 四元组。"""
        with patch("src.config.CONFIG_PATH") as mock_path, \
             patch("builtins.open", mock_open(read_data="")), \
             patch("src.config.yaml.safe_load", return_value=MOCK_CONFIG), \
             patch("src.config._validate_config"), \
             patch("src.azure_client.AzureOpenAI"):

            mock_path.exists.return_value = True

            from run import _create_components
            recorder, transcriber, polisher, polish_cfg = _create_components()

            from src.recorder import Recorder
            from src.transcriber import Transcriber
            from src.polisher import Polisher

            assert isinstance(recorder, Recorder)
            assert isinstance(transcriber, Transcriber)
            assert isinstance(polisher, Polisher)
            assert polish_cfg["language"] == "zh"
            assert polish_cfg["enabled"] is True

    def test_creates_without_polisher_when_disabled(self):
        """润色关闭时 polisher 应该为 None。"""
        config_no_polish = {
            **MOCK_CONFIG,
            "polish": {"enabled": False, "language": "zh"},
        }

        with patch("src.config.CONFIG_PATH") as mock_path, \
             patch("builtins.open", mock_open(read_data="")), \
             patch("src.config.yaml.safe_load",
                   return_value=config_no_polish), \
             patch("src.config._validate_config"), \
             patch("src.azure_client.AzureOpenAI"):

            mock_path.exists.return_value = True

            from run import _create_components
            recorder, transcriber, polisher, polish_cfg = _create_components()

            assert polisher is None


# =============================================================
# Protocol 接口合规性测试
# =============================================================

class TestProtocolCompliance:
    """验证具体实现满足 Protocol 接口。"""

    def test_transcriber_satisfies_protocol(self):
        """Transcriber 应该满足 TranscriberProtocol。"""
        from src.interfaces import TranscriberProtocol
        from src.transcriber import Transcriber

        with patch("src.azure_client.AzureOpenAI"):
            t = Transcriber(
                endpoint="https://test.openai.azure.com/",
                api_key="test-key",
                api_version="2024-06-01",
                deployment="whisper",
            )

        assert isinstance(t, TranscriberProtocol)

    def test_polisher_satisfies_protocol(self):
        """Polisher 应该满足 PolisherProtocol。"""
        from src.interfaces import PolisherProtocol
        from src.polisher import Polisher

        with patch("src.azure_client.AzureOpenAI"):
            p = Polisher(
                endpoint="https://test.openai.azure.com/",
                api_key="test-key",
                api_version="2024-06-01",
                deployment="gpt-4o-mini",
            )

        assert isinstance(p, PolisherProtocol)


# =============================================================
# 剪贴板保护测试
# =============================================================

class TestClipboardProtection:
    """测试剪贴板备份/恢复机制。"""

    def test_empty_clipboard_skips_restore(self):
        """原剪贴板为空字符串时（可能是图片），应跳过恢复。"""
        from src.output import _restore_clipboard

        with patch("src.output.pyperclip.copy") as mock_copy:
            _restore_clipboard("")
            # 空字符串不应调用 pyperclip.copy，以保护非文字内容
            mock_copy.assert_not_called()

    def test_none_clipboard_skips_restore(self):
        """备份失败（None）时应跳过恢复。"""
        from src.output import _restore_clipboard

        with patch("src.output.pyperclip.copy") as mock_copy:
            _restore_clipboard(None)
            mock_copy.assert_not_called()

    def test_text_clipboard_restores(self):
        """有文字内容时应正常恢复。"""
        from src.output import _restore_clipboard

        with patch("src.output.pyperclip.copy") as mock_copy:
            _restore_clipboard("原来的文字")
            mock_copy.assert_called_once_with("原来的文字")

    def test_async_restore_does_not_block(self):
        """异步恢复不应阻塞调用方。"""
        from src.output import _async_restore_clipboard

        with patch("src.output._restore_clipboard") as mock_restore, \
             patch("src.output.time.sleep"):
            _async_restore_clipboard("测试内容")
            # 异步调用应立即返回（不阻塞）
            # 等后台线程执行完
            import time
            time.sleep(0.1)
            mock_restore.assert_called_once_with("测试内容")
