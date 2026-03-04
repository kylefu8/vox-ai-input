"""
路径工具模块

统一处理 PyInstaller 打包（frozen）和普通 Python 脚本两种运行模式下的路径差异。

PyInstaller --onedir 模式下：
- sys.executable → exe 路径（如 C:/Program Files/VoxAIInput/VoxAIInput.exe）
- sys._MEIPASS → _internal 目录（存放依赖和资源，等同于 exe 旁边的 _internal/）
- __file__ → 指向 _internal 目录内的 .pyc

目录结构（安装后）：
    VoxAIInput/
    ├── VoxAIInput.exe
    ├── _internal/          ← sys._MEIPASS
    │   ├── src/
    │   ├── assets/sounds/
    │   └── ...
    ├── config.yaml         ← 用户文件
    └── config.example.yaml

所以需要两个路径函数：
- get_project_root(): 用于定位 config.yaml 等用户文件（exe 所在目录）
- get_resource_dir(): 用于定位 assets/sounds 等只读资源（_internal 目录）
"""

import sys
from pathlib import Path


def get_project_root():
    """
    获取项目根目录（用于定位用户文件）。

    - 打包模式: exe 所在目录（config.yaml 放在这里）
    - 脚本模式: 代码根目录（包含 run.py 的目录）

    Returns:
        Path: 项目根目录
    """
    if getattr(sys, "frozen", False):
        # PyInstaller --onedir：exe 所在目录
        return Path(sys.executable).parent
    # 普通脚本模式：paths.py 所在的 src/ 的上一级
    return Path(__file__).resolve().parent.parent


def get_resource_dir():
    """
    获取资源文件目录（用于定位只读资源）。

    - 打包模式: sys._MEIPASS（--onedir 下即 _internal 目录）
    - 脚本模式: 代码根目录

    Returns:
        Path: 资源文件根目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def get_internal_dir():
    """
    获取 _internal 目录（用于增量更新时定位需替换的文件）。

    - 打包模式: sys._MEIPASS
    - 脚本模式: 返回 None（源码不适用）

    Returns:
        Path | None
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return None


def is_frozen():
    """
    检查当前是否运行在 PyInstaller 打包模式下。

    Returns:
        bool: 是否为打包模式
    """
    return getattr(sys, "frozen", False)
