"""
Core voice processing pipeline.

This module keeps the speech workflow independent from tray icons, hotkeys,
Tkinter overlays, and settings windows. UI layers can subscribe to progress via
callbacks while the pipeline owns the business steps:
transcribe -> optional polish -> paste/output.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.interfaces import PolisherProtocol, TranscriberProtocol
from src.logger import setup_logger
from src.output import paste_text

log = setup_logger(__name__)

TextCallback = Callable[[str], None]


@dataclass
class VoicePipelineResult:
    """Result metadata for one completed pipeline run."""

    raw_text: str
    final_text: str
    duration: float
    api_calls: int = 0
    history_id: str | None = None


class VoicePipeline:
    """Reusable speech-to-output workflow."""

    def __init__(
        self,
        transcriber: TranscriberProtocol | None,
        polisher: PolisherProtocol | None = None,
        polish_enabled: bool = True,
        language: str = "zh",
        stt_counts_as_api: bool = True,
        paste_func: Callable[[str], None] | None = None,
        history_store=None,
        history_metadata: dict | None = None,
    ):
        self.transcriber = transcriber
        self.polisher = polisher
        self.polish_enabled = polish_enabled
        self.language = language
        self.stt_counts_as_api = stt_counts_as_api
        self.paste_func = paste_func or paste_text
        self.history_store = history_store
        self.history_metadata = dict(history_metadata or {})

    def process_audio(
        self,
        wav_path: Path | str,
        on_raw_text: TextCallback | None = None,
        on_final_text: TextCallback | None = None,
    ) -> VoicePipelineResult | None:
        """Transcribe an audio file, optionally polish the text, then paste it."""
        if not self.transcriber:
            log.error("转写器未配置，请先在设置中配置转写引擎")
            return None

        started_at = time.monotonic()
        api_calls = 0

        t1 = time.monotonic()
        raw_text = self.transcriber.transcribe(wav_path, language=self.language)
        if not raw_text:
            log.warning("转写结果为空，跳过")
            return None

        if self.stt_counts_as_api:
            api_calls += 1
        t2 = time.monotonic()
        log.info("⏱️  转写耗时: %.1f 秒", t2 - t1)

        if on_raw_text:
            on_raw_text(raw_text)

        final_text, polish_calls = self._polish(raw_text, fallback_to_raw=False)
        api_calls += polish_calls
        if not final_text:
            log.warning("润色结果为空，跳过")
            return None

        if polish_calls:
            log.info("⏱️  润色耗时: %.1f 秒", time.monotonic() - t2)

        return self._finish(raw_text, final_text, started_at, api_calls, on_final_text, source="audio")

    def process_text(
        self,
        raw_text: str,
        on_raw_text: TextCallback | None = None,
        on_final_text: TextCallback | None = None,
    ) -> VoicePipelineResult | None:
        """Polish an already-transcribed text value, then paste it."""
        if not raw_text:
            log.warning("输入文字为空，跳过")
            return None

        started_at = time.monotonic()
        log.info("流式转写原文: %s", _preview(raw_text))

        if on_raw_text:
            on_raw_text(raw_text)

        t1 = time.monotonic()
        final_text, api_calls = self._polish(raw_text, fallback_to_raw=True)
        if api_calls:
            log.info("⏱️  润色耗时: %.1f 秒", time.monotonic() - t1)

        if not final_text:
            log.warning("润色结果为空，降级使用原始文字")
            final_text = raw_text

        return self._finish(raw_text, final_text, started_at, api_calls, on_final_text, source="streaming")

    def _polish(self, raw_text: str, fallback_to_raw: bool) -> tuple[str | None, int]:
        if not (self.polisher and self.polish_enabled):
            return raw_text, 0

        final_text = self.polisher.polish(raw_text)
        if not final_text and fallback_to_raw:
            return raw_text, 1
        return final_text, 1

    def _finish(
        self,
        raw_text: str,
        final_text: str,
        started_at: float,
        api_calls: int,
        on_final_text: TextCallback | None,
        source: str,
    ) -> VoicePipelineResult:
        if on_final_text:
            on_final_text(final_text)

        log.info("🎯 最终文字: %s", _preview(final_text))
        self.paste_func(final_text)

        duration = time.monotonic() - started_at
        history_id = self._save_history(raw_text, final_text, duration, api_calls, source)
        return VoicePipelineResult(
            raw_text=raw_text,
            final_text=final_text,
            duration=duration,
            api_calls=api_calls,
            history_id=history_id,
        )

    def _save_history(
        self,
        raw_text: str,
        final_text: str,
        duration: float,
        api_calls: int,
        source: str,
    ) -> str | None:
        if not self.history_store:
            return None
        try:
            entry = self.history_store.append(
                raw_text=raw_text,
                final_text=final_text,
                duration=duration,
                api_calls=api_calls,
                source=source,
                metadata=self.history_metadata,
            )
            return getattr(entry, "id", None)
        except Exception as e:
            log.warning("保存历史记录失败: %s", e)
            return None


def _preview(text: str) -> str:
    return text[:80] + "..." if len(text) > 80 else text
