"""
Small audio-file utilities shared by runtime paths.
"""

from __future__ import annotations

from pathlib import Path

from src.logger import setup_logger

log = setup_logger(__name__)


def cleanup_audio(audio_path):
    """
    Delete a temporary audio file.

    Windows can hold a short-lived exclusive lock after recording stops, so the
    deletion gets one retry before giving up.
    """
    import time as _time

    path = Path(audio_path)
    if not path.exists():
        return

    for attempt in range(2):
        try:
            path.unlink()
            log.debug("已清理临时音频文件: %s", path.name)
            return
        except PermissionError:
            if attempt == 0:
                _time.sleep(0.5)
        except OSError as e:
            log.warning("清理音频文件失败（不影响使用）: %s", e)
            return

    log.warning("清理音频文件失败（文件可能被占用）: %s", path.name)
