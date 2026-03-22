"""
本地语音转文字模块

使用 sherpa-onnx 离线推理引擎进行语音转写，无需网络连接。
支持 SenseVoice（中文最佳）和 Whisper Small（多语言通用）两种模型。
实现了 TranscriberProtocol 接口（鸭子类型），可无缝替换 Azure Transcriber。

线程安全：推理过程通过 _infer_lock 加锁，避免并发调用冲突。
"""

import gc
import threading
from pathlib import Path

from src.logger import setup_logger

log = setup_logger(__name__)


class LocalTranscriber:
    """
    本地离线语音转文字处理器。

    使用 sherpa-onnx 的 OfflineRecognizer 进行本地推理。
    实现 TranscriberProtocol 接口（鸭子类型，无需继承）。
    """

    def __init__(self, model_dir, model_type="sense_voice", num_threads=4, language="zh"):
        """
        初始化本地转写器。

        延迟导入 sherpa_onnx，避免未安装时导入失败影响其他功能。
        根据 model_type 创建对应的 OfflineRecognizer。

        Args:
            model_dir: 模型文件所在目录（Path 或 str）
            model_type: 模型类型，"sense_voice" 或 "whisper_small"
            num_threads: 推理线程数，建议设为 CPU 核心数的一半
            language: 识别语言代码（如 "zh"），空字符串表示自动检测

        Raises:
            RuntimeError: sherpa-onnx 未安装或模型加载失败时
        """
        self._model_dir = Path(model_dir)
        self._model_type = model_type
        self._infer_lock = threading.Lock()
        self._recognizer = None

        # 延迟导入 sherpa_onnx（未安装时给出清晰提示）
        try:
            import sherpa_onnx
            self._sherpa_onnx = sherpa_onnx
        except ImportError:
            raise RuntimeError(
                "sherpa-onnx 未安装。请运行: pip install sherpa-onnx\n"
                "或在设置中切换回 Azure 云端转写。"
            )

        # 根据模型类型创建 OfflineRecognizer
        try:
            if model_type == "sense_voice":
                self._recognizer = self._create_sense_voice(num_threads, language)
            elif model_type == "whisper_small":
                self._recognizer = self._create_whisper(num_threads, language)
            else:
                raise RuntimeError(f"不支持的模型类型: {model_type}")

            log.info(
                "本地转写器初始化完成（模型: %s，线程数: %d）",
                model_type, num_threads,
            )
        except Exception as e:
            raise RuntimeError(f"本地转写模型加载失败: {e}")

    def _create_sense_voice(self, num_threads, language):
        """
        创建 SenseVoice 离线识别器。

        Args:
            num_threads: 推理线程数
            language: 识别语言

        Returns:
            sherpa_onnx.OfflineRecognizer
        """
        model_path = self._model_dir / "model.int8.onnx"
        tokens_path = self._model_dir / "tokens.txt"

        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        if not tokens_path.exists():
            raise FileNotFoundError(f"词表文件不存在: {tokens_path}")

        recognizer = self._sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_path),
            tokens=str(tokens_path),
            num_threads=num_threads,
            use_itn=True,
            debug=False,
            language=language or "",
        )
        log.info("已加载 SenseVoice 模型: %s", model_path.name)
        return recognizer

    def _create_whisper(self, num_threads, language):
        """
        创建 Whisper 离线识别器。

        Args:
            num_threads: 推理线程数
            language: 识别语言

        Returns:
            sherpa_onnx.OfflineRecognizer
        """
        encoder_path = self._model_dir / "small-encoder.int8.onnx"
        decoder_path = self._model_dir / "small-decoder.int8.onnx"
        tokens_path = self._model_dir / "small-tokens.txt"

        if not encoder_path.exists():
            raise FileNotFoundError(f"编码器文件不存在: {encoder_path}")
        if not decoder_path.exists():
            raise FileNotFoundError(f"解码器文件不存在: {decoder_path}")
        if not tokens_path.exists():
            raise FileNotFoundError(f"词表文件不存在: {tokens_path}")

        recognizer = self._sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=str(encoder_path),
            decoder=str(decoder_path),
            tokens=str(tokens_path),
            num_threads=num_threads,
            language=language or "",
            task="transcribe",
            debug=False,
        )
        log.info("已加载 Whisper Small 模型: encoder=%s, decoder=%s",
                 encoder_path.name, decoder_path.name)
        return recognizer

    def transcribe(self, audio_path, language="zh"):
        """
        将音频文件转为文字（本地推理）。

        读取 WAV 文件 → 送入 OfflineRecognizer → 返回识别结果。
        sherpa-onnx 内部会自动处理采样率转换（重采样到 16kHz）。

        Args:
            audio_path: WAV 音频文件路径（str 或 Path）
            language: 语音语言代码（此参数在本地模式下由模型初始化时决定，
                      这里保留接口一致性但不使用）

        Returns:
            str | None: 转写的文字内容。如果转写失败返回 None。
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            log.error("音频文件不存在: %s", audio_path)
            return None

        if not self._recognizer:
            log.error("本地转写器未初始化")
            return None

        log.info("🖥️  正在进行本地语音转写...")

        try:
            # 读取音频文件
            import soundfile as sf
            audio_data, sample_rate = sf.read(str(audio_path), dtype="float32")

            # 多声道取第一声道
            if len(audio_data.shape) > 1:
                audio_data = audio_data[:, 0]

            log.debug("音频信息: 采样率=%d, 时长=%.1f秒, 样本数=%d",
                       sample_rate, len(audio_data) / sample_rate, len(audio_data))

            # 线程安全推理
            with self._infer_lock:
                stream = self._recognizer.create_stream()
                stream.accept_waveform(sample_rate, audio_data)
                self._recognizer.decode_stream(stream)
                text = stream.result.text.strip()

            if not text:
                log.warning("本地转写结果为空，可能录音中没有语音内容")
                return None

            log.info("✅ 本地转写完成: %s",
                     text[:80] + "..." if len(text) > 80 else text)
            return text

        except Exception as e:
            log.error("本地语音转写失败: %s", e)
            return None

    def unload(self):
        """
        释放模型资源。

        删除 recognizer 引用并强制垃圾回收，释放模型占用的内存。
        切换回 Azure 模式或退出程序时调用。
        """
        log.info("正在释放本地转写模型...")
        self._recognizer = None
        gc.collect()
        log.info("本地转写模型已释放")
