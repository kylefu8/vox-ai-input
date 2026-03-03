"""
全局热键监听模块

使用 pynput 监听键盘事件，实现长按快捷键录音、松开触发处理的交互。
支持组合键（如 Ctrl+Shift+Space），并处理按键重复（长按时系统会反复触发 press）。
"""

import platform
import threading

from pynput import keyboard

from src.logger import setup_logger

log = setup_logger(__name__)


def _parse_hotkey_combination(combination_str):
    """
    将配置文件中的快捷键字符串解析为 pynput 按键对象集合。

    支持的修饰键: ctrl, shift, alt/option, cmd/super
    支持的普通键: space, 字母, 数字等

    Args:
        combination_str: 快捷键字符串，如 "ctrl+shift+space"

    Returns:
        tuple: (modifier_keys_set, trigger_key)
            - modifier_keys_set: 修饰键集合，如 {Key.ctrl, Key.shift}
            - trigger_key: 触发键，如 Key.space
    """
    parts = [p.strip().lower() for p in combination_str.split("+")]

    modifier_map = {
        "ctrl": keyboard.Key.ctrl,
        "control": keyboard.Key.ctrl,
        "shift": keyboard.Key.shift,
        "alt": keyboard.Key.alt,
        "option": keyboard.Key.alt,
        "cmd": keyboard.Key.cmd,
        "command": keyboard.Key.cmd,
        "super": keyboard.Key.cmd,
    }

    special_key_map = {
        "space": keyboard.Key.space,
        "tab": keyboard.Key.tab,
        "enter": keyboard.Key.enter,
        "return": keyboard.Key.enter,
        "esc": keyboard.Key.esc,
        "escape": keyboard.Key.esc,
        "f1": keyboard.Key.f1,
        "f2": keyboard.Key.f2,
        "f3": keyboard.Key.f3,
        "f4": keyboard.Key.f4,
        "f5": keyboard.Key.f5,
        "f6": keyboard.Key.f6,
        "f7": keyboard.Key.f7,
        "f8": keyboard.Key.f8,
        "f9": keyboard.Key.f9,
        "f10": keyboard.Key.f10,
        "f11": keyboard.Key.f11,
        "f12": keyboard.Key.f12,
    }

    modifiers = set()
    trigger = None

    for part in parts:
        if part in modifier_map:
            modifiers.add(modifier_map[part])
        elif part in special_key_map:
            trigger = special_key_map[part]
        elif len(part) == 1:
            # 单个字符键
            trigger = keyboard.KeyCode.from_char(part)
        else:
            log.warning("无法识别的按键: '%s'，忽略", part)

    if trigger is None:
        log.error("快捷键配置无效: '%s'，未找到触发键", combination_str)
        raise ValueError(
            f"快捷键配置无效: '{combination_str}'，"
            "请在 config.yaml 中设置正确的 hotkey.combination"
        )

    return modifiers, trigger


class HotkeyListener:
    """
    全局热键监听器。

    监听键盘的 press 和 release 事件，当检测到指定的快捷键组合时：
    - 按下（press）: 调用 on_activate 回调
    - 松开（release）: 调用 on_deactivate 回调

    会自动处理长按时的重复 press 事件（只触发一次 on_activate）。
    """

    def __init__(self, combination_str, on_activate, on_deactivate, on_cancel=None):
        """
        初始化热键监听器。

        Args:
            combination_str: 快捷键字符串，如 "ctrl+shift+space"
            on_activate: 按下快捷键时的回调函数（开始录音）
            on_deactivate: 松开快捷键时的回调函数（停止录音）
            on_cancel: 按 Esc 时的回调函数（取消录音），可选
        """
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate
        self.on_cancel = on_cancel

        # 解析快捷键
        self._modifiers, self._trigger = _parse_hotkey_combination(combination_str)
        log.info("快捷键配置: %s（修饰键: %s, 触发键: %s）",
                  combination_str, self._modifiers, self._trigger)

        # 当前按下的修饰键集合
        self._pressed_modifiers = set()
        # 触发键是否按下
        self._trigger_pressed = False
        # 是否已经激活（防止重复触发）
        self._is_active = False
        # 线程锁
        self._lock = threading.Lock()

        # pynput 监听器
        self._listener = None

    def start(self):
        """
        开始监听全局键盘事件。

        这个方法会阻塞当前线程（pynput 的事件循环）。
        通常在主线程中调用，让程序保持运行。
        """
        system = platform.system()
        if system == "Darwin":
            log.info("macOS 提示: 请确保终端/Python 已在 系统设置 > 隐私与安全 > 辅助功能 中获得授权")

        log.info("开始监听全局热键... 按 Ctrl+C 退出")

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        self._listener.join()  # 阻塞等待

    def stop(self):
        """停止监听。"""
        if self._listener:
            self._listener.stop()
            log.info("热键监听已停止")

    def _match_key(self, key, target):
        """
        比较两个按键是否匹配。

        需要处理 pynput 在不同平台上的按键表示差异。
        例如 ctrl_l 和 ctrl 都应该匹配 Key.ctrl。

        Args:
            key: 实际按下的键
            target: 目标键

        Returns:
            bool: 是否匹配
        """
        if key == target:
            return True

        # 处理左右修饰键的变体
        variants = {
            keyboard.Key.ctrl: (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r),
            keyboard.Key.shift: (keyboard.Key.shift_l, keyboard.Key.shift_r),
            keyboard.Key.alt: (keyboard.Key.alt_l, keyboard.Key.alt_r),
            keyboard.Key.cmd: (keyboard.Key.cmd_l, keyboard.Key.cmd_r),
        }

        for base_key, (left, right) in variants.items():
            if target == base_key and key in (left, right):
                return True

        return False

    def _on_press(self, key):
        """
        按键按下事件处理。

        检查当前按下的键是否构成完整的快捷键组合。
        按 Esc 键时，如果正在录音，则取消。
        """
        with self._lock:
            # 检查是否按了 Esc（取消录音）
            if key == keyboard.Key.esc and self._is_active:
                self._is_active = False
                self._trigger_pressed = False
                self._pressed_modifiers.clear()  # 清除残留的修饰键状态
                log.info("❌ 按下 Esc — 取消录音")
                if self.on_cancel:
                    try:
                        self.on_cancel()
                    except Exception as e:
                        log.error("on_cancel 回调出错: %s", e)
                return

            # 检查是否是修饰键
            for mod in self._modifiers:
                if self._match_key(key, mod):
                    self._pressed_modifiers.add(mod)
                    return

            # 检查是否是触发键
            if self._match_key(key, self._trigger):
                self._trigger_pressed = True

                # 检查所有修饰键是否都已按下
                if self._modifiers.issubset(self._pressed_modifiers):
                    if not self._is_active:
                        # 首次触发，调用 on_activate
                        self._is_active = True
                        log.info("🔴 热键按下 — 触发录音")
                        try:
                            self.on_activate()
                        except Exception as e:
                            log.error("on_activate 回调出错: %s", e)

    def _deactivate(self):
        """
        内部方法：执行去激活操作（停止录音回调）。

        必须在 self._lock 锁内调用。
        """
        self._is_active = False
        self._trigger_pressed = False
        log.info("⚪ 热键松开 — 停止录音")
        try:
            self.on_deactivate()
        except Exception as e:
            log.error("on_deactivate 回调出错: %s", e)

    def _on_release(self, key):
        """
        按键松开事件处理。

        当触发键或任何修饰键松开时，如果之前处于激活状态，
        则调用 on_deactivate 回调。
        """
        with self._lock:
            # 检查是否松开了修饰键
            for mod in self._modifiers:
                if self._match_key(key, mod):
                    self._pressed_modifiers.discard(mod)
                    if self._is_active:
                        self._deactivate()
                    return

            # 检查是否松开了触发键
            if self._match_key(key, self._trigger):
                self._trigger_pressed = False
                if self._is_active:
                    self._deactivate()
