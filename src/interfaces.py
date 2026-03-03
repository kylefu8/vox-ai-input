"""
抽象接口定义

定义 Transcriber 和 Polisher 的接口协议（Protocol），
让具体实现（Azure / OpenAI / 本地模型等）可以自由替换。

使用 Python 的 Protocol 而不是 ABC，因为 Protocol 支持结构化子类型（鸭子类型），
不强制继承，更灵活。
"""

from typing import Protocol, runtime_checkable
from pathlib import Path


@runtime_checkable
class TranscriberProtocol(Protocol):
    """
    语音转文字接口。

    任何实现了 transcribe 方法的类都自动满足此协议。
    cleanup_audio 已移至 transcriber 模块级函数，不再属于接口。
    """

    def transcribe(self, audio_path: Path | str, language: str = "zh") -> str | None:
        """
        将音频文件转为文字。

        Args:
            audio_path: 音频文件路径
            language: 语音语言代码，空字符串表示自动检测

        Returns:
            转写的文字，失败返回 None
        """
        ...


@runtime_checkable
class PolisherProtocol(Protocol):
    """
    文字润色接口。

    任何实现了 polish 方法的类都自动满足此协议。
    """

    def polish(self, raw_text: str) -> str | None:
        """
        对语音转写的原始文字进行润色。

        Args:
            raw_text: 原始转写文字

        Returns:
            润色后的文字。失败时应降级返回原文。
        """
        ...
