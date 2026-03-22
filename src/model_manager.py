"""
本地 STT 模型管理器

负责管理本地语音识别模型的下载、解压、完整性检查和路径管理。
模型从 sherpa-onnx GitHub Releases 下载（k2-fsa/sherpa-onnx）。

模型存储路径：
- 开发时：<项目根>/models/<model_name>/
- 打包后：<exe 目录>/models/<model_name>/

模型文件不打进安装包（太大），用户通过设置窗口按需下载。
"""

import gc
import os
import shutil
import tarfile
import threading
import urllib.request
from pathlib import Path

from src.logger import setup_logger
from src.paths import get_project_root

log = setup_logger(__name__)

# ==================== 模型注册表 ====================

MODEL_REGISTRY = {
    "sense_voice": {
        "display_name": "SenseVoice（推荐·中文最佳）",
        "download_url": (
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
            "asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
        ),
        "archive_dir": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
        "download_size_mb": 156,
        "required_files": ["model.int8.onnx", "tokens.txt"],
        "description": "中/英/日/韩/粤，速度快，中文质量最佳",
        "streaming": False,
    },
    "whisper_small": {
        "display_name": "Whisper Small（多语言通用）",
        "download_url": (
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
            "asr-models/sherpa-onnx-whisper-small.tar.bz2"
        ),
        "archive_dir": "sherpa-onnx-whisper-small",
        "download_size_mb": 610,
        "required_files": [
            "small-encoder.int8.onnx",
            "small-decoder.int8.onnx",
            "small-tokens.txt",
        ],
        "description": "支持 99 种语言，质量好",
        "streaming": False,
    },
    "paraformer_streaming": {
        "display_name": "Paraformer 流式（实时转写·中英双语）",
        "download_url": (
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
            "asr-models/sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2"
        ),
        "archive_dir": "sherpa-onnx-streaming-paraformer-bilingual-zh-en",
        "download_size_mb": 999,
        "required_files": ["encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"],
        "description": "中英双语流式，边说边出字",
        "streaming": True,
    },
}


def get_models_dir():
    """
    获取模型存放根目录。

    Returns:
        Path: <项目根>/models/
    """
    return get_project_root() / "models"


def get_model_dir(model_name):
    """
    获取指定模型的存放目录。

    Args:
        model_name: 模型名称（如 "sense_voice"）

    Returns:
        Path: <项目根>/models/<model_name>/
    """
    return get_models_dir() / model_name


def is_model_ready(model_name):
    """
    检查指定模型是否已下载且文件完整。

    遍历 MODEL_REGISTRY 中注册的 required_files 列表，
    确认每个文件都存在于模型目录中。

    Args:
        model_name: 模型名称（如 "sense_voice"）

    Returns:
        bool: 所有必需文件都存在返回 True
    """
    if model_name not in MODEL_REGISTRY:
        log.warning("未知模型: %s", model_name)
        return False

    model_dir = get_model_dir(model_name)
    required = MODEL_REGISTRY[model_name]["required_files"]

    for filename in required:
        if not (model_dir / filename).exists():
            log.debug("模型 %s 缺少文件: %s", model_name, filename)
            return False

    return True


def download_model(model_name, on_progress=None, on_complete=None, on_error=None):
    """
    在后台线程中下载并解压模型文件。

    下载流程：
    1. 从 GitHub Releases 下载 tar.bz2 压缩包
    2. 从压缩包中选择性解压 required_files 到模型目录
    3. 删除压缩包

    Args:
        model_name: 模型名称（如 "sense_voice"）
        on_progress: 进度回调 fn(percent: float, status: str)，0.0~100.0
        on_complete: 下载完成回调 fn(success: bool)
        on_error: 错误回调 fn(error_msg: str)
    """
    if model_name not in MODEL_REGISTRY:
        msg = f"未知模型: {model_name}"
        log.error(msg)
        if on_error:
            on_error(msg)
        return

    def _download_thread():
        """下载线程的实际工作函数。"""
        info = MODEL_REGISTRY[model_name]
        url = info["download_url"]
        archive_dir = info["archive_dir"]
        required = info["required_files"]
        model_dir = get_model_dir(model_name)

        # 创建模型目录
        try:
            model_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            msg = f"无法创建模型目录: {e}"
            log.error(msg)
            if on_error:
                on_error(msg)
            if on_complete:
                on_complete(False)
            return

        # 下载压缩包到临时文件
        archive_path = model_dir / f"{model_name}.tar.bz2"
        log.info("开始下载模型 %s: %s", model_name, url)

        try:
            if on_progress:
                on_progress(0.0, "正在连接...")

            def _report_hook(block_num, block_size, total_size):
                """urllib 下载进度回调。"""
                if total_size > 0:
                    downloaded = block_num * block_size
                    # 下载阶段占 0-80% 进度
                    percent = min(downloaded / total_size * 80.0, 80.0)
                    size_mb = downloaded / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    if on_progress:
                        on_progress(percent, f"下载中 {size_mb:.0f}/{total_mb:.0f} MB")

            urllib.request.urlretrieve(url, str(archive_path), reporthook=_report_hook)
            log.info("下载完成: %s", archive_path.name)

        except Exception as e:
            msg = f"下载失败: {e}"
            log.error(msg)
            # 清理未完成的下载
            _safe_delete(archive_path)
            if on_error:
                on_error(msg)
            if on_complete:
                on_complete(False)
            return

        # 解压所需文件
        try:
            if on_progress:
                on_progress(82.0, "正在解压...")
            log.info("正在解压模型文件...")

            with tarfile.open(str(archive_path), "r:bz2") as tar:
                for filename in required:
                    # 压缩包内的路径：<archive_dir>/<filename>
                    member_name = f"{archive_dir}/{filename}"
                    try:
                        member = tar.getmember(member_name)
                    except KeyError:
                        msg = f"压缩包中找不到文件: {member_name}"
                        log.error(msg)
                        if on_error:
                            on_error(msg)
                        if on_complete:
                            on_complete(False)
                        return

                    # 解压到模型目录，去掉顶层目录前缀
                    member.name = filename
                    tar.extract(member, path=str(model_dir))
                    log.info("已解压: %s", filename)

            if on_progress:
                on_progress(95.0, "正在清理...")

        except Exception as e:
            msg = f"解压失败: {e}"
            log.error(msg)
            if on_error:
                on_error(msg)
            if on_complete:
                on_complete(False)
            return

        finally:
            # 删除压缩包（无论成功与否）
            _safe_delete(archive_path)

        # 验证文件完整性
        if is_model_ready(model_name):
            log.info("模型 %s 下载并解压完成，文件完整", model_name)
            if on_progress:
                on_progress(100.0, "完成！")
            if on_complete:
                on_complete(True)
        else:
            msg = "解压后文件不完整，请重新下载"
            log.error(msg)
            if on_error:
                on_error(msg)
            if on_complete:
                on_complete(False)

    thread = threading.Thread(target=_download_thread, daemon=True)
    thread.start()
    return thread


def delete_model(model_name):
    """
    删除已下载的模型文件。

    Args:
        model_name: 模型名称（如 "sense_voice"）

    Returns:
        bool: 是否删除成功
    """
    model_dir = get_model_dir(model_name)
    if not model_dir.exists():
        log.info("模型 %s 不存在，无需删除", model_name)
        return True

    try:
        shutil.rmtree(str(model_dir))
        log.info("已删除模型: %s", model_name)
        # 强制垃圾回收
        gc.collect()
        return True
    except OSError as e:
        log.error("删除模型失败: %s", e)
        return False


def get_model_info(model_name):
    """
    获取模型的注册信息。

    Args:
        model_name: 模型名称

    Returns:
        dict | None: 模型信息字典，未注册返回 None
    """
    return MODEL_REGISTRY.get(model_name)


def list_models():
    """
    列出所有已注册的模型及其状态。

    Returns:
        list[dict]: 每个模型的信息 + ready 状态
    """
    result = []
    for name, info in MODEL_REGISTRY.items():
        result.append({
            "name": name,
            "display_name": info["display_name"],
            "description": info["description"],
            "download_size_mb": info["download_size_mb"],
            "ready": is_model_ready(name),
        })
    return result


def _safe_delete(path):
    """
    安全删除文件，忽略不存在的情况。

    Args:
        path: 要删除的文件路径
    """
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except OSError as e:
        log.warning("清理文件失败（不影响使用）: %s", e)
