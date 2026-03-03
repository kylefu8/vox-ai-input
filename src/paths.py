"""
路径工具模块

统一处理 PyInstaller 打包（frozen）和普通 Python 脚本两种运行模式下的路径差异。

PyInstaller --onefile 模式下：
- sys.executable → exe 自身路径（如 C:/Users/.../VoxAIInput.exe）
- sys._MEIPASS → 临时解压目录（只读，存放 bundle 内的资源文件）
- __file__ → 指向临时解压目录内的 .pyc，不能用来定位用户文件

所以需要两个路径函数：
- get_project_root(): 用于定位 config.yaml 等用户文件（在 exe 旁边）
- get_resource_dir(): 用于定位 assets/sounds 等只读资源（在 bundle 内部）
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
        # PyInstaller 打包模式：exe 所在目录
        return Path(sys.executable).parent
    # 普通脚本模式：paths.py 所在的 src/ 的上一级
    return Path(__file__).resolve().parent.parent


def get_resource_dir():
    """
    获取资源文件目录（用于定位只读资源）。

    - 打包模式: sys._MEIPASS（PyInstaller 临时解压目录）
    - 脚本模式: 代码根目录

    Returns:
        Path: 资源文件根目录
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 打包模式：临时解压目录
        return Path(sys._MEIPASS)
    # 普通脚本模式：和 get_project_root() 一致
    return Path(__file__).resolve().parent.parent


def is_frozen():
    """
    检查当前是否运行在 PyInstaller 打包模式下。

    Returns:
        bool: 是否为打包模式
    """
    return getattr(sys, "frozen", False)
