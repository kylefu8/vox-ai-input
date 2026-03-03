"""
语音唤醒模块

使用 openwakeword 进行本地唤醒词检测，纯离线、免费。
检测到唤醒词后触发录音 → 转写 → 润色 → 粘贴流程。

录音自动停止策略：检测到连续静音（默认 1.5 秒）后自动结束录音。
"""

import platform
import threading
import time

import numpy as np
import sounddevice as sd

from src.logger import setup_logger

log = setup_logger(__name__)

# 支持的预训练唤醒词（openwakeword 内置）
BUILTIN_MODELS = [
    "hey_jarvis",
    "alexa",
    "ok_google",
    "hey_mycroft",
    "hey_rhasspy",
]


class WakeWordListener:
    """
    语音唤醒监听器。

    持续监听麦克风，检测到唤醒词后调用回调函数。
    使用 openwakeword 的 ONNX 模型，纯本地推理，CPU 占用 ~2%。

    Args:
        model_name: 唤醒词模型名称（如 'hey_jarvis'）或自定义 .onnx 路径
        threshold: 检测灵敏度阈值 (0.0~1.0)，越高越严格
        on_wake: 唤醒回调函数
        sample_rate: 采样率（必须 16000）
        device: 录音设备名称（None=系统默认）
        audio_backend: Windows 音频后端
    """

    def __init__(
        self,
        model_name="hey_jarvis",
        threshold=0.5,
        on_wake=None,
        sample_rate=16000,
        device=None,
        audio_backend=None,
    ):
        self._model_name = model_name
        self._threshold = threshold
        self._on_wake = on_wake
        self._sample_rate = sample_rate
        self._device = device
        self._audio_backend = audio_backend
        self._running = False
        self._stream = None
        self._oww_model = None
        self._cooldown = False  # 防止连续触发

    def start(self):
        """启动唤醒词监听（阻塞当前线程）。"""
        try:
            from openwakeword.model import Model as OWWModel
        except ImportError:
            log.error("openwakeword 未安装！请运行: pip install openwakeword")
            raise

        # 加载模型
        log.info("正在加载唤醒词模型: %s (阈值: %.2f)", self._model_name, self._threshold)
        self._oww_model = OWWModel(
            wakeword_models=[self._model_name],
            inference_framework="onnx",
        )
        log.info("唤醒词模型加载完成")

        self._running = True

        # 配置音频流参数
        stream_kwargs = {
            "samplerate": self._sample_rate,
            "channels": 1,
            "dtype": "int16",
            "blocksize": 1280,  # 80ms @ 16kHz — openwakeword 推荐
            "callback": self._audio_callback,
        }
        if self._device:
            stream_kwargs["device"] = self._device

        # Windows 音频后端
        if self._audio_backend and platform.system() == "Windows":
            extra = sd.WasapiSettings() if self._audio_backend == "wasapi" else None
            if extra:
                stream_kwargs["extra_settings"] = extra

        log.info("🎤 语音唤醒已启动，说 \"%s\" 开始录音...", self._model_name.replace("_", " "))

        self._stream = sd.InputStream(**stream_kwargs)
        self._stream.start()

        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """停止监听。"""
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        log.info("语音唤醒已停止")

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice 音频回调 — 每 80ms 调用一次。"""
        if not self._running or self._cooldown:
            return

        try:
            # openwakeword 需要 int16 numpy array
            audio = np.squeeze(indata)
            prediction = self._oww_model.predict(audio)

            for model_name, score in prediction.items():
                if score >= self._threshold:
                    log.info("🔔 检测到唤醒词 \"%s\" (置信度: %.3f)", model_name, score)
                    self._oww_model.reset()

                    # 冷却期防止连续触发
                    self._cooldown = True
                    threading.Timer(3.0, self._reset_cooldown).start()

                    # 触发回调
                    if self._on_wake:
                        threading.Thread(target=self._on_wake, daemon=True).start()
                    break

        except Exception as e:
            log.warning("唤醒词检测出错: %s", e)

    def _reset_cooldown(self):
        """重置冷却期。"""
        self._cooldown = False


class VoiceActivatedRecorder:
    """
    语音激活录音器 — 唤醒后自动录音，静音自动停止。

    工作流程：
    1. 唤醒词触发
    2. 播放提示音
    3. 开始录音
    4. 检测到连续静音（默认 1.5 秒）后自动停止
    5. 返回录音文件路径

    Args:
        recorder: Recorder 实例
        silence_duration: 连续静音多久后停止录音（秒）
        silence_threshold: 静音 RMS 阈值
        max_duration: 最大录音时长（秒）
    """

    def __init__(self, recorder, silence_duration=1.5, silence_threshold=0.02, max_duration=60):
        self._recorder = recorder
        self._silence_duration = silence_duration
        self._silence_threshold = silence_threshold
        self._max_duration = max_duration

    def record_until_silence(self):
        """
        开始录音，检测到静音后自动停止。

        Returns:
            WAV 文件路径，如果录音无效返回 None
        """
        from src.notifier import play_start_sound, play_stop_sound

        play_start_sound()
        self._recorder.start()

        start_time = time.time()
        last_sound_time = time.time()

        # 等待一小段时间让用户开始说话
        time.sleep(0.3)

        while self._recorder.is_recording:
            elapsed = time.time() - start_time

            # 超过最大时长
            if elapsed >= self._max_duration:
                log.info("达到最大录音时长 (%ds)，自动停止", self._max_duration)
                break

            # 检查当前音量
            current_rms = self._recorder.get_current_rms()
            if current_rms is not None:
                if current_rms >= self._silence_threshold:
                    last_sound_time = time.time()
                elif time.time() - last_sound_time >= self._silence_duration:
                    # 连续静音超过阈值
                    if elapsed > 1.0:  # 至少录了 1 秒
                        log.info("检测到连续静音 (%.1fs)，自动停止录音", self._silence_duration)
                        break

            time.sleep(0.1)

        play_stop_sound()
        wav_path = self._recorder.stop()

        if not wav_path:
            log.warning("没有有效的录音数据")
            return None

        if self._recorder.is_silent(wav_path):
            log.info("未检测到语音输入，跳过")
            self._recorder.cleanup_temp_files()
            return None

        return wav_path
