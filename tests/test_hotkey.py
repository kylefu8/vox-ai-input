"""
hotkey 模块的单元测试

测试快捷键解析逻辑和热键监听器的状态管理。
"""

import pytest
from unittest.mock import MagicMock

from pynput import keyboard

from src.hotkey import _parse_hotkey_combination, HotkeyListener


class TestParseHotkeyCombination:
    """快捷键字符串解析的测试。"""

    def test_ctrl_shift_space(self):
        """解析 ctrl+shift+space。"""
        modifiers, trigger = _parse_hotkey_combination("ctrl+shift+space")
        assert keyboard.Key.ctrl in modifiers
        assert keyboard.Key.shift in modifiers
        assert trigger == keyboard.Key.space

    def test_alt_shift_a(self):
        """解析 alt+shift+a，触发键是字母。"""
        modifiers, trigger = _parse_hotkey_combination("alt+shift+a")
        assert keyboard.Key.alt in modifiers
        assert keyboard.Key.shift in modifiers
        assert trigger == keyboard.KeyCode.from_char("a")

    def test_cmd_space(self):
        """解析 cmd+space。"""
        modifiers, trigger = _parse_hotkey_combination("cmd+space")
        assert keyboard.Key.cmd in modifiers
        assert trigger == keyboard.Key.space

    def test_alternative_names(self):
        """支持别名：control=ctrl, option=alt, command=cmd。"""
        modifiers1, _ = _parse_hotkey_combination("control+space")
        assert keyboard.Key.ctrl in modifiers1

        modifiers2, _ = _parse_hotkey_combination("option+space")
        assert keyboard.Key.alt in modifiers2

        modifiers3, _ = _parse_hotkey_combination("command+space")
        assert keyboard.Key.cmd in modifiers3

    def test_function_keys(self):
        """支持功能键 F1-F12。"""
        _, trigger = _parse_hotkey_combination("ctrl+f5")
        assert trigger == keyboard.Key.f5

    def test_case_insensitive(self):
        """大小写不敏感。"""
        modifiers, trigger = _parse_hotkey_combination("Ctrl+Shift+Space")
        assert keyboard.Key.ctrl in modifiers
        assert keyboard.Key.shift in modifiers
        assert trigger == keyboard.Key.space

    def test_whitespace_tolerance(self):
        """容忍空格。"""
        modifiers, trigger = _parse_hotkey_combination("ctrl + shift + space")
        assert keyboard.Key.ctrl in modifiers
        assert keyboard.Key.shift in modifiers

    def test_invalid_key_falls_back_to_space(self):
        """含无法识别的按键时（有有效触发键），无效部分被忽略。"""
        modifiers, trigger = _parse_hotkey_combination("ctrl+unknownkey+space")
        assert trigger == keyboard.Key.space

    def test_no_trigger_key_raises_error(self):
        """只有修饰键没有触发键时，应该抛出 ValueError。"""
        with pytest.raises(ValueError, match="快捷键配置无效"):
            _parse_hotkey_combination("ctrl+shift")


class TestHotkeyListenerMatchKey:
    """按键匹配逻辑的测试。"""

    def setup_method(self):
        """每个测试前创建一个监听器实例。"""
        self.listener = HotkeyListener(
            combination_str="ctrl+shift+space",
            on_activate=MagicMock(),
            on_deactivate=MagicMock(),
        )

    def test_exact_match(self):
        """精确匹配。"""
        assert self.listener._match_key(keyboard.Key.ctrl, keyboard.Key.ctrl)
        assert self.listener._match_key(keyboard.Key.space, keyboard.Key.space)

    def test_left_variant_matches_base(self):
        """左侧修饰键应该匹配基础键。"""
        assert self.listener._match_key(keyboard.Key.ctrl_l, keyboard.Key.ctrl)
        assert self.listener._match_key(keyboard.Key.shift_l, keyboard.Key.shift)

    def test_right_variant_matches_base(self):
        """右侧修饰键应该匹配基础键。"""
        assert self.listener._match_key(keyboard.Key.ctrl_r, keyboard.Key.ctrl)
        assert self.listener._match_key(keyboard.Key.shift_r, keyboard.Key.shift)

    def test_non_match(self):
        """不匹配的键应该返回 False。"""
        assert not self.listener._match_key(keyboard.Key.alt, keyboard.Key.ctrl)
        assert not self.listener._match_key(keyboard.Key.tab, keyboard.Key.space)


class TestHotkeyListenerCallbacks:
    """回调触发逻辑的测试。"""

    def setup_method(self):
        """每个测试前创建一个监听器实例。"""
        self.on_activate = MagicMock()
        self.on_deactivate = MagicMock()
        self.on_cancel = MagicMock()
        self.listener = HotkeyListener(
            combination_str="ctrl+shift+space",
            on_activate=self.on_activate,
            on_deactivate=self.on_deactivate,
            on_cancel=self.on_cancel,
        )

    def test_full_combo_activates(self):
        """按下完整组合键应该触发 activate。"""
        # 按下 ctrl + shift + space
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.shift_l)
        self.listener._on_press(keyboard.Key.space)

        self.on_activate.assert_called_once()

    def test_incomplete_combo_no_activate(self):
        """不完整的组合键不应触发 activate。"""
        # 只按 ctrl + space（缺少 shift）
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.space)

        self.on_activate.assert_not_called()

    def test_release_trigger_deactivates(self):
        """松开触发键应该调用 deactivate。"""
        # 先激活
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.shift_l)
        self.listener._on_press(keyboard.Key.space)
        # 松开 space
        self.listener._on_release(keyboard.Key.space)

        self.on_deactivate.assert_called_once()

    def test_release_modifier_deactivates(self):
        """松开修饰键也应该调用 deactivate。"""
        # 先激活
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.shift_l)
        self.listener._on_press(keyboard.Key.space)
        # 松开 shift（修饰键）
        self.listener._on_release(keyboard.Key.shift_l)

        self.on_deactivate.assert_called_once()

    def test_no_duplicate_activate_on_repeat(self):
        """长按重复 press 不应重复触发 activate。"""
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.shift_l)
        # 多次 press space（模拟长按重复）
        self.listener._on_press(keyboard.Key.space)
        self.listener._on_press(keyboard.Key.space)
        self.listener._on_press(keyboard.Key.space)

        # 只应触发一次
        self.on_activate.assert_called_once()


class TestHotkeyListenerCancel:
    """Esc 取消录音逻辑的测试。"""

    def setup_method(self):
        """每个测试前创建一个监听器实例。"""
        self.on_activate = MagicMock()
        self.on_deactivate = MagicMock()
        self.on_cancel = MagicMock()
        self.listener = HotkeyListener(
            combination_str="ctrl+shift+space",
            on_activate=self.on_activate,
            on_deactivate=self.on_deactivate,
            on_cancel=self.on_cancel,
        )

    def test_esc_during_active_calls_cancel(self):
        """录音中按 Esc 应该触发 cancel 回调并清除修饰键状态。"""
        # 先激活
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.shift_l)
        self.listener._on_press(keyboard.Key.space)
        # 按 Esc
        self.listener._on_press(keyboard.Key.esc)

        self.on_cancel.assert_called_once()
        self.on_deactivate.assert_not_called()
        # Esc 应该清除残留的修饰键状态
        assert len(self.listener._pressed_modifiers) == 0

    def test_esc_when_not_active_does_nothing(self):
        """未录音时按 Esc 不应触发任何回调。"""
        self.listener._on_press(keyboard.Key.esc)

        self.on_cancel.assert_not_called()
        self.on_deactivate.assert_not_called()

    def test_esc_resets_active_state(self):
        """Esc 取消后，状态应重置为非激活，可以重新开始录音。"""
        # 第一次：激活 → Esc 取消
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.shift_l)
        self.listener._on_press(keyboard.Key.space)
        self.listener._on_press(keyboard.Key.esc)

        # 松开所有键
        self.listener._on_release(keyboard.Key.space)
        self.listener._on_release(keyboard.Key.shift_l)
        self.listener._on_release(keyboard.Key.ctrl_l)

        # 第二次：重新激活应该成功
        self.listener._on_press(keyboard.Key.ctrl_l)
        self.listener._on_press(keyboard.Key.shift_l)
        self.listener._on_press(keyboard.Key.space)

        assert self.on_activate.call_count == 2

    def test_no_cancel_callback_no_error(self):
        """没有设置 on_cancel 回调时，按 Esc 不应报错。"""
        listener_no_cancel = HotkeyListener(
            combination_str="ctrl+shift+space",
            on_activate=MagicMock(),
            on_deactivate=MagicMock(),
        )
        # 激活
        listener_no_cancel._on_press(keyboard.Key.ctrl_l)
        listener_no_cancel._on_press(keyboard.Key.shift_l)
        listener_no_cancel._on_press(keyboard.Key.space)
        # 按 Esc — 不应崩溃
        listener_no_cancel._on_press(keyboard.Key.esc)


class TestWinKeySupport:
    """Win/Windows 键支持的测试。"""

    def test_win_as_modifier(self):
        """win 应该被识别为修饰键（等同于 cmd）。"""
        modifiers, trigger = _parse_hotkey_combination("win+space")
        assert keyboard.Key.cmd in modifiers
        assert trigger == keyboard.Key.space

    def test_windows_as_modifier(self):
        """windows 也应该被识别为修饰键。"""
        modifiers, trigger = _parse_hotkey_combination("windows+space")
        assert keyboard.Key.cmd in modifiers
        assert trigger == keyboard.Key.space

    def test_ctrl_win_combination(self):
        """ctrl+win+空格 应该能正确解析。"""
        modifiers, trigger = _parse_hotkey_combination("ctrl+win+space")
        assert keyboard.Key.ctrl in modifiers
        assert keyboard.Key.cmd in modifiers
        assert trigger == keyboard.Key.space

    def test_ctrl_win_without_trigger_raises(self):
        """ctrl+win 没有触发键应该报错。"""
        with pytest.raises(ValueError, match="快捷键配置无效"):
            _parse_hotkey_combination("ctrl+win")
