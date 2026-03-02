"""
语音转文字模块

调用 Azure OpenAI 的 Whisper API，将 WAV 录音文件转为文字。
使用 openai 官方 SDK 的 Azure 兼容模式。
"""

from pathlib import Path

from openai import AzureOpenAI

from src.logger import setup_logger

log = setup_logger(__name__)


class Transcriber:
    """
    语音转文字处理器。

    使用 Azure OpenAI 的 Whisper 模型将音频文件转为文字。
    """

    def __init__(self, endpoint, api_key, api_version, deployment):
        """
        初始化 Whisper 转写器。

        Args:
            endpoint: Azure OpenAI 服务端点 URL
            api_key: Azure OpenAI API Key
            api_version: API 版本号
            deployment: Whisper 模型的部署名称
        """
        self.deployment = deployment

        # 创建 Azure OpenAI 客户端
        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

        log.info("Whisper 转写器初始化完成（部署: %s）", deployment)

    def transcribe(self, audio_path, language="zh"):
        """
        将音频文件转为文字。

        Args:
            audio_path: WAV 音频文件路径（str 或 Path）
            language: 语音语言代码，默认 "zh"（中文）。
                      设为 None 或空字符串则让 Whisper 自动检测。

        Returns:
            str | None: 转写的文字内容。如果转写失败返回 None。
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            log.error("音频文件不存在: %s", audio_path)
            return None

        log.info("📡 正在调用 Whisper API 转写语音...")

        try:
            with open(audio_path, "rb") as audio_file:
                # 构建 API 调用参数
                params = {
                    "model": self.deployment,
                    "file": audio_file,
                    "response_format": "text",
                }

                # 如果指定了语言，添加到参数中
                if language:
                    params["language"] = language

                result = self.client.audio.transcriptions.create(**params)

            # result 在 response_format="text" 时是纯字符串
            text = result.strip() if isinstance(result, str) else str(result).strip()

            if not text:
                log.warning("Whisper 返回了空文字，可能录音中没有语音内容")
                return None

            log.info("✅ 转写完成: %s", text[:80] + "..." if len(text) > 80 else text)
            return text

        except Exception as e:
            log.error("Whisper API 调用失败: %s", e)
            log.error("请检查: 1) Azure 端点和 Key 是否正确 "
                       "2) Whisper 部署名称是否正确 "
                       "3) 网络连接是否正常")
            return None

    def cleanup_audio(self, audio_path):
        """
        删除临时音频文件。

        Args:
            audio_path: 要删除的音频文件路径
        """
        try:
            path = Path(audio_path)
            if path.exists():
                path.unlink()
                log.info("已清理临时音频文件: %s", path.name)
        except OSError as e:
            log.warning("清理音频文件失败（不影响使用）: %s", e)
