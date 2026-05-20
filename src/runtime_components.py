"""
Runtime component factories.

This module centralizes construction of recorder, transcriber, and polisher
instances so GUI mode and test mode use the same wiring rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.config import (
    get_llm_profile_config,
    get_polish_config,
    get_recording_config,
    get_stt_config,
)
from src.interfaces import PolisherProtocol, TranscriberProtocol
from src.llm_clients import create_llm_client
from src.logger import setup_logger
from src.polisher import Polisher
from src.recorder import Recorder

log = setup_logger(__name__)


@dataclass
class TranscriberRuntime:
    """Transcriber plus streaming metadata needed by app controllers."""

    transcriber: TranscriberProtocol
    is_streaming_mode: bool = False
    streaming_transcriber: TranscriberProtocol | None = None


@dataclass
class RuntimeComponents:
    """Core runtime components built from config."""

    recorder: Recorder
    transcriber: TranscriberProtocol
    polisher: PolisherProtocol | None
    polish_cfg: dict
    transcriber_runtime: TranscriberRuntime


def create_recorder(recording_cfg: dict) -> Recorder:
    """Create the microphone recorder from normalized recording config."""
    return Recorder(
        sample_rate=recording_cfg["sample_rate"],
        channels=recording_cfg["channels"],
        max_duration=recording_cfg["max_duration"],
    )


def create_transcriber_runtime(
    stt_cfg: dict,
    language: str = "zh",
    on_streaming_text: Callable[[str], None] | None = None,
) -> TranscriberRuntime:
    """Create a transcriber and return streaming metadata for controllers."""
    from src.model_manager import MODEL_REGISTRY, get_model_dir, is_model_ready

    model_type = stt_cfg.get("model_type", "sense_voice")
    num_threads = stt_cfg.get("num_threads", 4)

    if not is_model_ready(model_type):
        raise RuntimeError(
            f"本地模型 {model_type} 尚未下载。"
            "请在设置中下载模型后再使用本地转写。"
        )

    model_dir = get_model_dir(model_type)
    model_info = MODEL_REGISTRY.get(model_type, {})
    is_streaming_model = model_info.get("streaming", False)
    streaming_enabled = stt_cfg.get("streaming", False)

    if is_streaming_model and streaming_enabled:
        from src.streaming_transcriber import StreamingTranscriber

        transcriber = StreamingTranscriber(
            model_dir=model_dir,
            num_threads=num_threads,
            on_partial_result=on_streaming_text,
        )
        log.info("已创建流式转写器（模型: %s，流式模式）", model_type)
        return TranscriberRuntime(
            transcriber=transcriber,
            is_streaming_mode=True,
            streaming_transcriber=transcriber,
        )

    if is_streaming_model:
        from src.streaming_transcriber import StreamingTranscriber

        transcriber = StreamingTranscriber(
            model_dir=model_dir,
            num_threads=num_threads,
        )
        log.info("已创建 Paraformer 转写器（非流式模式，模型: %s）", model_type)
        return TranscriberRuntime(transcriber=transcriber)

    from src.local_transcriber import LocalTranscriber

    transcriber = LocalTranscriber(
        model_dir=model_dir,
        model_type=model_type,
        num_threads=num_threads,
        language=language,
    )
    log.info("已创建本地转写器（模型: %s）", model_type)
    return TranscriberRuntime(transcriber=transcriber)


def create_polisher(config: dict, polish_cfg: dict) -> PolisherProtocol:
    """Create the selected LLM polisher from polish.profile."""
    profile = get_llm_profile_config(config, polish_cfg.get("profile"))
    llm_client = create_llm_client(profile)
    return Polisher(
        llm_client=llm_client,
        system_prompt=polish_cfg.get("system_prompt", "") or None,
        translate_to=polish_cfg.get("translate_to", ""),
        show_original=polish_cfg.get("show_original", False),
        max_tokens=profile.get("max_tokens"),
        temperature=float(profile.get("temperature", 0)),
    )


def create_runtime_components(
    config: dict,
    on_streaming_text: Callable[[str], None] | None = None,
) -> RuntimeComponents:
    """Create recorder, transcriber, and optional polisher from full config."""
    rec_cfg = get_recording_config(config)
    polish_cfg = get_polish_config(config)
    stt_cfg = get_stt_config(config)

    recorder = create_recorder(rec_cfg)
    transcriber_runtime = create_transcriber_runtime(
        stt_cfg=stt_cfg,
        language=polish_cfg.get("language", "zh"),
        on_streaming_text=on_streaming_text,
    )

    polisher = None
    if polish_cfg.get("enabled", False):
        polisher = create_polisher(config, polish_cfg)

    return RuntimeComponents(
        recorder=recorder,
        transcriber=transcriber_runtime.transcriber,
        polisher=polisher,
        polish_cfg=polish_cfg,
        transcriber_runtime=transcriber_runtime,
    )
