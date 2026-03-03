"""
提示音与通知模块

播放录音开始/结束的提示音，让用户知道当前状态。
使用 sounddevice 播放 WAV 文件（复用已有依赖，无需引入新库）。
"""

import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from src.logger import setup_logger
from src.paths import get_resource_dir, is_frozen

log = setup_logger(__name__)

# 提示音文件目录（打包模式下在 bundle 内部，脚本模式下在代码目录）
SOUNDS_DIR = get_resource_dir() / "assets" / "sounds"

# 提示音内存缓存：{name: (audio_data, sample_rate)}
# 在 create_default_sounds() 时填充，play_sound() 直接从这里读取
_sound_cache = {}


def _generate_beep(frequency=800, duration=0.15, sample_rate=44100, volume=0.3):
    """
    生成一个简短的正弦波提示音。

    当 WAV 文件不存在时作为备用方案。

    Args:
        frequency: 频率（Hz）
        duration: 时长（秒）
        sample_rate: 采样率
        volume: 音量（0.0 ~ 1.0）

    Returns:
        numpy.ndarray: 音频数据
    """
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # 正弦波 + 淡入淡出（避免爆音）
    wave = np.sin(2 * np.pi * frequency * t) * volume

    # 应用简单的淡入淡出
    fade_samples = int(sample_rate * 0.01)  # 10ms 淡入淡出
    if fade_samples > 0 and len(wave) > 2 * fade_samples:
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        wave[:fade_samples] *= fade_in
        wave[-fade_samples:] *= fade_out

    return wave.astype(np.float32)


def play_sound(sound_name, blocking=False):
    """
    播放提示音。

    优先尝试播放 assets/sounds/ 目录下的 WAV 文件，
    如果文件不存在则使用程序生成的提示音。

    Args:
        sound_name: 提示音名称，如 "start" 或 "stop"
        blocking: 是否阻塞等待播放完成，默认 False（后台播放）
    """
    def _play():
        try:
            # 优先从内存缓存读取
            if sound_name in _sound_cache:
                data, samplerate = _sound_cache[sound_name]
                sd.play(data, samplerate)
                sd.wait()
                return

            wav_path = SOUNDS_DIR / f"{sound_name}.wav"

            if wav_path.exists():
                # 播放 WAV 文件
                data, samplerate = sf.read(str(wav_path), dtype="float32")
                # 缓存到内存供下次使用
                _sound_cache[sound_name] = (data, samplerate)
                sd.play(data, samplerate)
                sd.wait()
            else:
                # 使用生成的提示音
                if sound_name == "start":
                    # 录音开始：上升音调（较高频率）
                    audio = _generate_beep(frequency=880, duration=0.12)
                elif sound_name == "stop":
                    # 录音结束：下降音调（较低频率）
                    audio = _generate_beep(frequency=440, duration=0.15)
                else:
                    audio = _generate_beep()

                sd.play(audio, 44100)
                sd.wait()

        except Exception as e:
            # 提示音播放失败不应影响核心功能
            log.warning("提示音播放失败（不影响使用）: %s", e)

    if blocking:
        _play()
    else:
        # 后台线程播放，不阻塞主流程
        thread = threading.Thread(target=_play, daemon=True)
        thread.start()


def play_start_sound():
    """播放录音开始提示音。"""
    play_sound("start")


def play_stop_sound():
    """播放录音结束提示音。"""
    play_sound("stop")


def create_default_sounds():
    """
    生成默认的提示音 WAV 文件到 assets/sounds/ 目录。

    如果文件已存在则跳过。
    打包模式下跳过文件生成（提示音已打包在 bundle 内，且目录只读）。
    """
    sounds = {
        "start": {"frequency": 880, "duration": 0.12},
        "stop": {"frequency": 440, "duration": 0.15},
    }

    # 打包模式下不生成文件（bundle 内只读），只预加载缓存
    if not is_frozen():
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

        for name, params in sounds.items():
            wav_path = SOUNDS_DIR / f"{name}.wav"
            if not wav_path.exists():
                try:
                    audio = _generate_beep(**params)
                    sf.write(str(wav_path), audio, 44100)
                    log.info("已生成默认提示音: %s", wav_path)
                except Exception as e:
                    log.warning("生成提示音文件失败: %s", e)

    # 预加载提示音到内存缓存，后续播放不再读磁盘
    for name in sounds:
        if name not in _sound_cache:
            wav_path = SOUNDS_DIR / f"{name}.wav"
            if wav_path.exists():
                try:
                    data, samplerate = sf.read(str(wav_path), dtype="float32")
                    _sound_cache[name] = (data, samplerate)
                except Exception as e:
                    log.warning("预加载提示音失败: %s", e)
