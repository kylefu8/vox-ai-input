"""
流式语音转文字模块

使用 sherpa-onnx 的 OnlineRecognizer 进行实时流式转写。
录音的同时将音频 chunk 喂给识别器，解码线程持续输出中间结果，
让用户在预览浮窗中看到"边说边出字"的效果。

线程模型：
- 音频回调线程 → feed_audio_chunk() → 放入 _audio_queue（非阻塞）
- 解码线程 → 从 queue 取 chunk → accept_waveform → decode_stream → on_partial_result 回调

同时实现 TranscriberProtocol 的 transcribe() 方法，作为非流式回退路径。
"""

import gc
import queue
import threading
from pathlib import Path

from src.logger import setup_logger

log = setup_logger(__name__)


class StreamingTranscriber:
    """
    流式语音转文字处理器。

    使用 sherpa-onnx OnlineRecognizer（Paraformer 流式模型）进行实时转写。
    实现 TranscriberProtocol 接口（鸭子类型），可作为回退的非流式转写器使用。
    """

    def __init__(self, model_dir, num_threads=4, on_partial_result=None):
        """
        初始化流式转写器。

        延迟导入 sherpa_onnx，根据 Paraformer 流式模型文件创建 OnlineRecognizer。

        Args:
            model_dir: 模型文件所在目录（Path 或 str）
            num_threads: 推理线程数
            on_partial_result: 中间结果回调 fn(text: str)，每次识别出新文字时调用

        Raises:
            RuntimeError: sherpa-onnx 未安装或模型加载失败时
        """
        self._model_dir = Path(model_dir)
        self._on_partial_result = on_partial_result
        self._recognizer = None
        self._stream = None
        self._audio_queue = None
        self._decode_thread = None
        self._session_active = False

        # 延迟导入 sherpa_onnx
        try:
            import sherpa_onnx
            self._sherpa_onnx = sherpa_onnx
        except ImportError:
            raise RuntimeError(
                "sherpa-onnx 未安装。请运行: pip install sherpa-onnx\n"
                "或在设置中切换回 Azure 云端转写。"
            )

        # 创建 OnlineRecognizer
        try:
            self._recognizer = self._create_recognizer(num_threads)
            log.info(
                "流式转写器初始化完成（Paraformer 流式，线程数: %d）",
                num_threads,
            )
        except Exception as e:
            raise RuntimeError(f"流式转写模型加载失败: {e}")

    def _create_recognizer(self, num_threads):
        """
        创建 Paraformer 流式在线识别器。

        Args:
            num_threads: 推理线程数

        Returns:
            sherpa_onnx.OnlineRecognizer
        """
        encoder_path = self._model_dir / "encoder.int8.onnx"
        decoder_path = self._model_dir / "decoder.int8.onnx"
        tokens_path = self._model_dir / "tokens.txt"

        if not encoder_path.exists():
            raise FileNotFoundError(f"编码器文件不存在: {encoder_path}")
        if not decoder_path.exists():
            raise FileNotFoundError(f"解码器文件不存在: {decoder_path}")
        if not tokens_path.exists():
            raise FileNotFoundError(f"词表文件不存在: {tokens_path}")

        recognizer = self._sherpa_onnx.OnlineRecognizer.from_paraformer(
            encoder=str(encoder_path),
            decoder=str(decoder_path),
            tokens=str(tokens_path),
            num_threads=num_threads,
            enable_endpoint_detection=False,  # 热键控制，不需要自动端点检测
        )
        log.info("已加载 Paraformer 流式模型: encoder=%s, decoder=%s",
                 encoder_path.name, decoder_path.name)
        return recognizer

    def start_session(self):
        """
        开始一个新的流式转写会话。

        创建新的 OnlineStream，启动解码线程。
        每次按下热键开始录音时调用。
        """
        if self._session_active:
            log.warning("已有活跃的流式会话，先停止旧会话")
            self.stop_session()

        if not self._recognizer:
            log.error("流式转写器未初始化")
            return

        self._stream = self._recognizer.create_stream()
        self._audio_queue = queue.Queue()
        self._session_active = True

        # 启动解码线程
        self._decode_thread = threading.Thread(
            target=self._decode_loop, daemon=True
        )
        self._decode_thread.start()
        log.info("流式转写会话已开始")

    def feed_audio_chunk(self, audio_data, sample_rate=16000):
        """
        喂入一块音频数据（从录音回调线程调用）。

        使用 put_nowait 确保绝不阻塞音频回调线程。

        Args:
            audio_data: numpy 数组，音频采样数据
            sample_rate: 采样率（默认 16000）
        """
        if not self._session_active or self._audio_queue is None:
            return

        try:
            self._audio_queue.put_nowait((audio_data.copy(), sample_rate))
        except queue.Full:
            pass  # 丢弃，绝不阻塞
        except Exception:
            pass  # 音频回调中绝不能抛异常

    def stop_session(self):
        """
        停止当前流式转写会话，获取最终结果。

        往 queue 放 sentinel(None) → 等解码线程退出 → 取最终结果。
        每次松开热键停止录音时调用。

        Returns:
            str: 最终的转写文字（可能为空字符串）
        """
        if not self._session_active:
            return ""

        self._session_active = False

        # 发送 sentinel 通知解码线程退出
        if self._audio_queue is not None:
            try:
                self._audio_queue.put_nowait(None)
            except Exception:
                pass

        # 等待解码线程完成（最多等 5 秒）
        if self._decode_thread and self._decode_thread.is_alive():
            self._decode_thread.join(timeout=5.0)

        # 获取最终结果
        final_text = ""
        if self._stream and self._recognizer:
            try:
                result = self._recognizer.get_result(self._stream)
                final_text = result.strip() if result else ""
            except Exception as e:
                log.error("获取流式转写最终结果失败: %s", e)

        self._stream = None
        self._audio_queue = None
        self._decode_thread = None

        log.info("流式转写会话已结束，结果: %s",
                 final_text[:80] + "..." if len(final_text) > 80 else final_text)
        return final_text

    def _decode_loop(self):
        """
        解码线程主循环。

        从 _audio_queue 中持续取出音频 chunk，喂给 OnlineStream，
        然后调用 decode_stream 进行解码。每次解码后检查结果是否有变化，
        有变化则通过 on_partial_result 回调通知外部。
        """
        last_text = ""
        sample_rate = 16000

        try:
            while True:
                # 从队列取数据（超时 50ms，让循环保持响应）
                try:
                    item = self._audio_queue.get(timeout=0.05)
                except queue.Empty:
                    # 超时无数据，继续尝试解码（可能还有缓冲区数据）
                    if self._stream and self._recognizer:
                        try:
                            while self._recognizer.is_ready(self._stream):
                                self._recognizer.decode_stream(self._stream)
                            text = self._recognizer.get_result(self._stream)
                            text = text.strip() if text else ""
                            if text and text != last_text:
                                last_text = text
                                if self._on_partial_result:
                                    try:
                                        self._on_partial_result(text)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    continue

                # sentinel: None 表示会话结束
                if item is None:
                    if self._stream and self._recognizer:
                        try:
                            # 追加 0.5 秒静音数据，让 Paraformer 的 lookahead 缓冲区有
                            # 足够的上下文来解码最后几个 token（否则短录音容易吞字）
                            import numpy as np
                            silence = np.zeros(int(sample_rate * 0.5), dtype=np.float32)
                            self._stream.accept_waveform(sample_rate, silence)
                            while self._recognizer.is_ready(self._stream):
                                self._recognizer.decode_stream(self._stream)

                            # 通知 stream 音频输入已结束，flush 剩余缓冲区
                            self._stream.input_finished()
                            while self._recognizer.is_ready(self._stream):
                                self._recognizer.decode_stream(self._stream)
                        except Exception as e:
                            log.debug("最终解码出错: %s", e)
                    break

                audio_chunk, sample_rate = item

                # 多声道取第一声道
                if len(audio_chunk.shape) > 1:
                    audio_chunk = audio_chunk[:, 0]

                # 喂给 stream
                if self._stream:
                    try:
                        self._stream.accept_waveform(sample_rate, audio_chunk)

                        # 解码
                        while self._recognizer.is_ready(self._stream):
                            self._recognizer.decode_stream(self._stream)

                        # 检查结果变化
                        text = self._recognizer.get_result(self._stream)
                        text = text.strip() if text else ""
                        if text and text != last_text:
                            last_text = text
                            if self._on_partial_result:
                                try:
                                    self._on_partial_result(text)
                                except Exception:
                                    pass
                    except Exception as e:
                        log.debug("流式解码出错: %s", e)

        except Exception as e:
            log.error("流式解码线程异常: %s", e)

    def transcribe(self, audio_path, language="zh"):
        """
        TranscriberProtocol 兼容接口（非流式回退路径）。

        读取音频文件 → 切 100ms 块 → 逐块 accept → decode → 返回结果。
        当 streaming=False 但选了 paraformer_streaming 模型时使用此路径。

        Args:
            audio_path: WAV 音频文件路径
            language: 语言代码（保留接口一致性）

        Returns:
            str | None: 转写的文字，失败返回 None
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            log.error("音频文件不存在: %s", audio_path)
            return None

        if not self._recognizer:
            log.error("流式转写器未初始化")
            return None

        log.info("🖥️  正在使用 Paraformer 流式模型进行离线转写...")

        try:
            import numpy as np
            import soundfile as sf

            audio_data, sample_rate = sf.read(str(audio_path), dtype="float32")

            # 多声道取第一声道
            if len(audio_data.shape) > 1:
                audio_data = audio_data[:, 0]

            log.debug("音频信息: 采样率=%d, 时长=%.1f秒",
                       sample_rate, len(audio_data) / sample_rate)

            # 创建临时 stream
            stream = self._recognizer.create_stream()

            # 切 100ms 块逐块喂入
            chunk_size = int(sample_rate * 0.1)  # 100ms
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                stream.accept_waveform(sample_rate, chunk)
                while self._recognizer.is_ready(stream):
                    self._recognizer.decode_stream(stream)

            # 追加 0.5 秒静音，确保 Paraformer lookahead 缓冲区有足够数据
            silence = np.zeros(int(sample_rate * 0.5), dtype=np.float32)
            stream.accept_waveform(sample_rate, silence)
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)

            # 通知输入结束 + 最终解码
            stream.input_finished()
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)

            text = self._recognizer.get_result(stream)
            text = text.strip() if text else ""

            if not text:
                log.warning("Paraformer 离线转写结果为空")
                return None

            log.info("✅ Paraformer 离线转写完成: %s",
                     text[:80] + "..." if len(text) > 80 else text)
            return text

        except Exception as e:
            log.error("Paraformer 离线转写失败: %s", e)
            return None

    def unload(self):
        """
        释放模型资源。

        停止活跃会话，删除 recognizer 引用并强制垃圾回收。
        """
        if self._session_active:
            self.stop_session()
        log.info("正在释放流式转写模型...")
        self._recognizer = None
        gc.collect()
        log.info("流式转写模型已释放")
