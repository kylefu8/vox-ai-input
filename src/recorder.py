"""
麦克风录音模块

使用 sounddevice 的回调模式进行实时录音，不阻塞主线程。
录音数据暂存在内存中，停止后保存为临时 WAV 文件供后续 API 调用使用。
"""

import tempfile
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from src.logger import setup_logger

log = setup_logger(__name__)


class Recorder:
    """
    麦克风录音器。

    使用 sounddevice 的回调（callback）模式录音：
    - start() 开始录音，音频数据通过回调函数持续写入内存缓冲区
    - stop() 停止录音，将缓冲区数据保存为 WAV 文件并返回文件路径

    这种回调模式不会阻塞调用线程，适合在主线程监听热键的同时录音。
    """

    def __init__(self, sample_rate=16000, channels=1, max_duration=60):
        """
        初始化录音器。

        Args:
            sample_rate: 采样率，默认 16000 Hz（Whisper 推荐值）
            channels: 声道数，默认 1（单声道）
            max_duration: 最大录音时长（秒），超过自动停止
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_duration = max_duration

        # 录音状态
        self._is_recording = False
        self._stream = None
        self._audio_chunks = []  # 存放录音数据片段
        self._lock = threading.Lock()

        # 自动停止定时器
        self._auto_stop_timer = None
        # 当录音自动停止时的回调函数
        self._on_auto_stop = None

    @property
    def is_recording(self):
        """当前是否正在录音。"""
        return self._is_recording

    def start(self, on_auto_stop=None):
        """
        开始录音。

        Args:
            on_auto_stop: 可选回调函数，当录音达到最大时长自动停止时调用

        Returns:
            bool: 是否成功开始录音
        """
        if self._is_recording:
            log.warning("已经在录音中，忽略重复的 start 调用")
            return False

        try:
            # 清空之前的录音数据
            self._audio_chunks = []
            self._on_auto_stop = on_auto_stop

            # 创建音频输入流（回调模式）
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True

            # 设置最大录音时长的自动停止定时器
            self._auto_stop_timer = threading.Timer(
                self.max_duration, self._auto_stop
            )
            self._auto_stop_timer.daemon = True
            self._auto_stop_timer.start()

            log.info("🎤 开始录音（采样率: %d Hz，最长: %d 秒）",
                      self.sample_rate, self.max_duration)
            return True

        except sd.PortAudioError as e:
            log.error("无法访问麦克风: %s", e)
            log.error("请检查系统是否已授权麦克风访问权限")
            self._is_recording = False
            return False
        except Exception as e:
            log.error("录音启动失败: %s", e)
            self._is_recording = False
            return False

    def stop(self):
        """
        停止录音并保存为 WAV 文件。

        Returns:
            Path | None: 录音文件路径，如果录音失败或无数据则返回 None
        """
        if not self._is_recording:
            log.warning("当前未在录音，忽略 stop 调用")
            return None

        # 取消自动停止定时器
        if self._auto_stop_timer:
            self._auto_stop_timer.cancel()
            self._auto_stop_timer = None

        # 停止并关闭音频流
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception as e:
            log.warning("关闭音频流时出错: %s", e)
        finally:
            self._stream = None
            self._is_recording = False

        log.info("⏹️  停止录音")

        # 把所有录音片段拼接成一个完整的 numpy 数组
        with self._lock:
            if not self._audio_chunks:
                log.warning("录音数据为空，可能麦克风未正常工作")
                return None
            audio_data = np.concatenate(self._audio_chunks, axis=0)

        duration = len(audio_data) / self.sample_rate
        log.info("录音时长: %.1f 秒（%d 个采样点）", duration, len(audio_data))

        # 如果录音太短（不到 0.3 秒），可能是误触
        if duration < 0.3:
            log.warning("录音时长不足 0.3 秒，跳过处理")
            return None

        # 保存为临时 WAV 文件
        try:
            wav_path = self._save_to_wav(audio_data)
            log.info("录音已保存: %s", wav_path)
            return wav_path
        except Exception as e:
            log.error("保存录音文件失败: %s", e)
            return None

    def _audio_callback(self, indata, frames, time_info, status):
        """
        sounddevice 的回调函数，每收到一段音频数据就调用一次。

        这个函数在音频线程中执行，不能做耗时操作。

        Args:
            indata: 输入音频数据（numpy 数组）
            frames: 帧数
            time_info: 时间信息
            status: 状态标志（溢出等）
        """
        if status:
            log.warning("音频流状态异常: %s", status)

        # 复制一份数据存入缓冲区（indata 的内存会被复用）
        with self._lock:
            self._audio_chunks.append(indata.copy())

    def _save_to_wav(self, audio_data):
        """
        将 numpy 音频数据保存为临时 WAV 文件。

        Args:
            audio_data: numpy 数组，形状为 (samples,) 或 (samples, channels)

        Returns:
            Path: 保存的 WAV 文件路径
        """
        # 在系统临时目录创建 WAV 文件
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".wav", prefix="ai_input_", delete=False
        )
        wav_path = Path(temp_file.name)
        temp_file.close()

        sf.write(str(wav_path), audio_data, self.sample_rate)
        return wav_path

    def _auto_stop(self):
        """
        当录音达到最大时长时自动停止。
        在 Timer 线程中执行。
        """
        log.warning("录音已达最大时长 %d 秒，自动停止", self.max_duration)
        wav_path = self.stop()
        if self._on_auto_stop and wav_path:
            self._on_auto_stop(wav_path)
