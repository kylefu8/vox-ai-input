"""
剪贴板输出模块

负责将润色后的文字粘贴到当前激活的应用中：
1. 备份当前剪贴板内容
2. 将润色文字写入剪贴板
3. 模拟 Cmd+V（macOS）或 Ctrl+V（Windows）粘贴
4. 短暂等待后恢复原剪贴板内容（即使出错也会恢复）
"""

import platform
import time

import pyperclip

from src.logger import setup_logger

log = setup_logger(__name__)

# Controller 延迟初始化，避免在 import 时触发系统 Accessibility 框架连接
# （在无 GUI 的 CI 环境中，立即初始化可能挂起或报错）
_keyboard_controller = None

# 粘贴时序常量（秒），可根据不同系统/应用微调
_CLIPBOARD_WRITE_DELAY = 0.05   # 写入剪贴板后等待，确保系统同步
_PASTE_RESTORE_DELAY = 0.3      # 粘贴后等待，确保目标应用接收完成再恢复剪贴板


def _get_controller():
    """
    获取 pynput 键盘控制器（延迟初始化单例）。

    Returns:
        pynput.keyboard.Controller 实例
    """
    global _keyboard_controller
    if _keyboard_controller is None:
        from pynput.keyboard import Controller
        _keyboard_controller = Controller()
    return _keyboard_controller


def paste_text(text):
    """
    将文字粘贴到当前激活的应用中。

    工作流程：备份剪贴板 → 写入文字 → 模拟粘贴 → 恢复剪贴板。
    无论粘贴是否成功，都会尝试恢复原剪贴板内容。

    Args:
        text: 要粘贴的文字

    Returns:
        bool: 是否成功粘贴
    """
    if not text:
        log.warning("文字为空，跳过粘贴")
        return False

    original_clipboard = _backup_clipboard()
    success = False

    try:
        # 1. 将润色文字写入剪贴板
        pyperclip.copy(text)
        log.info("📋 文字已写入剪贴板（%d 字符）", len(text))

        # 2. 短暂等待，确保剪贴板更新完成
        time.sleep(_CLIPBOARD_WRITE_DELAY)

        # 3. 模拟粘贴快捷键
        _simulate_paste()

        log.info("✅ 文字已粘贴到当前应用")
        success = True

    except Exception as e:
        log.error("粘贴文字失败: %s", e)

    finally:
        # 4. 无论成功与否，等待后恢复原剪贴板
        time.sleep(_PASTE_RESTORE_DELAY)
        _restore_clipboard(original_clipboard)

    return success


def _backup_clipboard():
    """
    备份当前剪贴板中的文字内容。

    Returns:
        str | None: 剪贴板中的文字，如果读取失败返回 None
    """
    try:
        content = pyperclip.paste()
        return content
    except Exception as e:
        log.warning("无法读取剪贴板内容（不影响使用）: %s", e)
        return None


def _restore_clipboard(original_content):
    """
    恢复剪贴板为原来的内容。

    Args:
        original_content: 之前备份的剪贴板内容
    """
    if original_content is None:
        return

    try:
        pyperclip.copy(original_content)
        log.debug("剪贴板已恢复为原内容")
    except Exception as e:
        log.warning("恢复剪贴板失败（不影响使用）: %s", e)


def _simulate_paste():
    """
    模拟粘贴快捷键。

    macOS: Cmd+V
    Windows: Ctrl+V

    使用延迟初始化的 Controller 单例来模拟按键。
    """
    from pynput.keyboard import Key

    system = platform.system()
    controller = _get_controller()

    try:
        if system == "Darwin":
            # macOS: Cmd+V
            controller.press(Key.cmd)
            controller.press("v")
            controller.release("v")
            controller.release(Key.cmd)
            log.debug("模拟 Cmd+V 粘贴")
        else:
            # Windows / Linux: Ctrl+V
            controller.press(Key.ctrl)
            controller.press("v")
            controller.release("v")
            controller.release(Key.ctrl)
            log.debug("模拟 Ctrl+V 粘贴")

    except Exception as e:
        log.error("模拟粘贴键失败: %s", e)
        log.error("请确保已在系统设置中授权辅助功能权限")
        raise
