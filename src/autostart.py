"""
开机自启管理模块

跨平台支持：
- Windows: 通过注册表 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
- macOS: 通过 LaunchAgent plist 文件 ~/Library/LaunchAgents/

两种方式都不需要管理员权限。
"""

import platform
import sys
from pathlib import Path

from src.logger import setup_logger

log = setup_logger(__name__)

# 注册表/plist 中使用的应用标识
_APP_NAME = "VoxAIInput"
_MACOS_LABEL = "com.voxaiinput.app"


def get_autostart_supported():
    """
    检查当前平台是否支持开机自启。

    Returns:
        bool: 是否支持
    """
    return platform.system() in ("Windows", "Darwin")


def check_autostart():
    """
    检查当前是否已启用开机自启。

    Returns:
        bool: 是否已启用
    """
    system = platform.system()

    if system == "Windows":
        return _check_autostart_windows()
    elif system == "Darwin":
        return _check_autostart_macos()
    else:
        log.debug("当前平台不支持开机自启: %s", system)
        return False


def set_autostart(enable):
    """
    启用或禁用开机自启。

    Args:
        enable: True 启用，False 禁用

    Returns:
        bool: 操作是否成功
    """
    system = platform.system()

    if system == "Windows":
        return _set_autostart_windows(enable)
    elif system == "Darwin":
        return _set_autostart_macos(enable)
    else:
        log.warning("当前平台不支持开机自启: %s", system)
        return False


# ========== Windows 实现 ==========

def _get_startup_command():
    """
    获取开机自启时要执行的命令字符串。

    Returns:
        str: 启动命令
    """
    exe_path = Path(sys.executable).resolve()
    script_path = Path(sys.argv[0]).resolve()

    # 如果是打包的 exe，直接用 exe 路径
    if not str(exe_path).lower().endswith(("python.exe", "pythonw.exe")):
        return f'"{exe_path}"'

    # 否则用 pythonw（无控制台窗口）+ 脚本路径
    pythonw = str(exe_path).replace("python.exe", "pythonw.exe")
    return f'"{pythonw}" "{script_path}"'


def _check_autostart_windows():
    """检查 Windows 注册表中是否有自启项。"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ
        ) as reg_key:
            winreg.QueryValueEx(reg_key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception as e:
        log.warning("检查自启状态失败: %s", e)
        return False


def _set_autostart_windows(enable):
    """通过注册表设置 Windows 开机自启。"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE
        ) as reg_key:
            if enable:
                command = _get_startup_command()
                winreg.SetValueEx(
                    reg_key, _APP_NAME, 0, winreg.REG_SZ, command
                )
                log.info("已启用开机自启: %s", command)
            else:
                try:
                    winreg.DeleteValue(reg_key, _APP_NAME)
                    log.info("已禁用开机自启")
                except FileNotFoundError:
                    log.debug("自启项不存在，无需删除")

        return True

    except Exception as e:
        log.error("设置开机自启失败: %s", e)
        return False


# ========== macOS 实现 ==========

def _get_plist_path():
    """获取 LaunchAgent plist 文件路径。"""
    return Path.home() / "Library" / "LaunchAgents" / f"{_MACOS_LABEL}.plist"


def _check_autostart_macos():
    """检查 macOS LaunchAgent 是否已安装。"""
    return _get_plist_path().exists()


def _set_autostart_macos(enable):
    """通过 LaunchAgent plist 设置 macOS 开机自启。"""
    import plistlib
    import subprocess

    plist_path = _get_plist_path()

    try:
        if enable:
            # 确保目录存在
            plist_path.parent.mkdir(parents=True, exist_ok=True)

            python_path = str(Path(sys.executable).resolve())
            script_path = str(Path(sys.argv[0]).resolve())

            plist_content = {
                "Label": _MACOS_LABEL,
                "ProgramArguments": [python_path, script_path],
                "RunAtLoad": True,
                "KeepAlive": False,
            }

            with open(plist_path, "wb") as f:
                plistlib.dump(plist_content, f)

            # 加载使本次登录也生效
            subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True,
            )
            log.info("已启用开机自启: %s", plist_path)

        else:
            if plist_path.exists():
                # 先卸载再删除
                subprocess.run(
                    ["launchctl", "unload", str(plist_path)],
                    capture_output=True,
                )
                plist_path.unlink()
                log.info("已禁用开机自启")
            else:
                log.debug("LaunchAgent 不存在，无需删除")

        return True

    except Exception as e:
        log.error("设置 macOS 开机自启失败: %s", e)
        return False
