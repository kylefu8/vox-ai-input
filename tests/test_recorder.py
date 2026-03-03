"""
recorder 模块的单元测试

测试录音器的状态管理、数据保存逻辑。
音频硬件操作用 mock 替代。
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.recorder import Recorder


class TestRecorderInit:
    """录音器初始化的测试。"""

    def test_default_values(self):
        """默认参数应该正确设置。"""
        r = Recorder()
        assert r.sample_rate == 16000
        assert r.channels == 1
        assert r.max_duration == 60
        assert r.is_recording is False

    def test_custom_values(self):
        """自定义参数应该正确设置。"""
        r = Recorder(sample_rate=44100, channels=2, max_duration=120)
        assert r.sample_rate == 44100
        assert r.channels == 2
        assert r.max_duration == 120


class TestRecorderStop:
    """录音停止逻辑的测试。"""

    def test_stop_when_not_recording_returns_none(self):
        """未在录音时调用 stop 应返回 None。"""
        r = Recorder()
        assert r.stop() is None

    def test_stop_with_empty_chunks_returns_none(self):
        """录音数据为空时应返回 None。"""
        r = Recorder()
        r._is_recording = True
        r._stream = MagicMock()
        r._audio_chunks = []

        result = r.stop()
        assert result is None

    def test_stop_with_short_audio_returns_none(self):
        """录音太短（<0.3秒）应返回 None。"""
        r = Recorder(sample_rate=16000)
        r._is_recording = True
        r._stream = MagicMock()
        # 0.1 秒的数据 = 1600 个采样点（小于 0.3 秒 = 4800 采样点）
        short_audio = np.zeros((1600, 1), dtype=np.float32)
        r._audio_chunks = [short_audio]

        result = r.stop()
        assert result is None

    def test_stop_with_valid_audio_returns_path(self):
        """有效录音应返回 WAV 文件路径。"""
        r = Recorder(sample_rate=16000)
        r._is_recording = True
        r._stream = MagicMock()
        # 1 秒的数据 = 16000 个采样点
        audio_data = np.random.randn(16000, 1).astype(np.float32)
        r._audio_chunks = [audio_data]

        result = r.stop()
        assert result is not None
        assert isinstance(result, Path)
        assert result.suffix == ".wav"
        assert result.exists()

        # 清理
        result.unlink()

    def test_stop_cancels_auto_stop_timer(self):
        """stop 应该取消自动停止定时器。"""
        r = Recorder()
        r._is_recording = True
        r._stream = MagicMock()
        mock_timer = MagicMock()
        r._auto_stop_timer = mock_timer
        r._audio_chunks = []

        r.stop()
        mock_timer.cancel.assert_called_once()
        # stop 之后定时器应被清除
        assert r._auto_stop_timer is None


class TestRecorderStart:
    """录音启动逻辑的测试。"""

    def test_start_when_already_recording_returns_false(self):
        """已在录音时重复调用 start 应返回 False。"""
        r = Recorder()
        r._is_recording = True

        result = r.start()
        assert result is False

    @patch("src.recorder.sd.InputStream")
    def test_start_success_returns_true(self, mock_stream_class):
        """正常启动应返回 True。"""
        mock_stream = MagicMock()
        mock_stream_class.return_value = mock_stream

        r = Recorder()
        result = r.start()

        assert result is True
        assert r.is_recording is True
        mock_stream.start.assert_called_once()


class TestRecorderAudioCallback:
    """音频回调的测试。"""

    def test_callback_stores_data(self):
        """回调应该将数据副本存入缓冲区。"""
        r = Recorder()
        fake_data = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)

        r._audio_callback(fake_data, 3, None, None)

        assert len(r._audio_chunks) == 1
        # 确认是副本不是引用
        assert r._audio_chunks[0] is not fake_data
        np.testing.assert_array_equal(r._audio_chunks[0], fake_data)

    def test_callback_multiple_calls_accumulate(self):
        """多次回调应该累积数据。"""
        r = Recorder()
        for i in range(5):
            fake_data = np.array([[float(i)]], dtype=np.float32)
            r._audio_callback(fake_data, 1, None, None)

        assert len(r._audio_chunks) == 5
