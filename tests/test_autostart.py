"""
autostart 模块的单元测试

测试跨平台开机自启逻辑（Windows 注册表 / macOS LaunchAgent）。
所有系统级操作均使用 mock 替代。
"""

import platform
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.autostart import (
    get_autostart_supported,
    check_autostart,
    set_autostart,
    _APP_NAME,
    _MACOS_LABEL,
)


class TestGetAutostartSupported:
    """平台支持检测测试。"""

    def test_windows_supported(self):
        """Windows 应该支持开机自启。"""
        with patch("src.autostart.platform.system", return_value="Windows"):
            assert get_autostart_supported() is True

    def test_macos_supported(self):
        """macOS 应该支持开机自启。"""
        with patch("src.autostart.platform.system", return_value="Darwin"):
            assert get_autostart_supported() is True

    def test_linux_not_supported(self):
        """Linux 暂不支持开机自启。"""
        with patch("src.autostart.platform.system", return_value="Linux"):
            assert get_autostart_supported() is False


class TestCheckAutostart:
    """检查自启状态测试。"""

    def test_unsupported_platform_returns_false(self):
        """不支持的平台应返回 False。"""
        with patch("src.autostart.platform.system", return_value="Linux"):
            assert check_autostart() is False

    def test_windows_check_enabled(self):
        """Windows 注册表中存在自启项时应返回 True。"""
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(
            return_value=mock_key
        )
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_winreg.QueryValueEx.return_value = ("some_command", 1)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019

        with patch("src.autostart.platform.system", return_value="Windows"), \
             patch.dict("sys.modules", {"winreg": mock_winreg}):
            # 重新导入以使用 mock 的 winreg
            from src.autostart import _check_autostart_windows
            result = _check_autostart_windows()
            assert result is True

    def test_windows_check_disabled(self):
        """Windows 注册表中不存在自启项时应返回 False。"""
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(
            return_value=mock_key
        )
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019

        with patch("src.autostart.platform.system", return_value="Windows"), \
             patch.dict("sys.modules", {"winreg": mock_winreg}):
            from src.autostart import _check_autostart_windows
            result = _check_autostart_windows()
            assert result is False

    def test_macos_check_enabled(self, tmp_path):
        """macOS LaunchAgent plist 存在时应返回 True。"""
        plist_path = tmp_path / f"{_MACOS_LABEL}.plist"
        plist_path.write_text("fake plist")

        with patch("src.autostart.platform.system", return_value="Darwin"), \
             patch("src.autostart._get_plist_path", return_value=plist_path):
            from src.autostart import _check_autostart_macos
            assert _check_autostart_macos() is True

    def test_macos_check_disabled(self, tmp_path):
        """macOS LaunchAgent plist 不存在时应返回 False。"""
        plist_path = tmp_path / f"{_MACOS_LABEL}.plist"

        with patch("src.autostart.platform.system", return_value="Darwin"), \
             patch("src.autostart._get_plist_path", return_value=plist_path):
            from src.autostart import _check_autostart_macos
            assert _check_autostart_macos() is False


class TestSetAutostart:
    """设置自启开关测试。"""

    def test_unsupported_platform_returns_false(self):
        """不支持的平台应返回 False。"""
        with patch("src.autostart.platform.system", return_value="Linux"):
            assert set_autostart(True) is False
            assert set_autostart(False) is False

    def test_macos_enable_creates_plist(self, tmp_path):
        """macOS 启用应该创建 plist 文件。"""
        plist_path = tmp_path / "LaunchAgents" / f"{_MACOS_LABEL}.plist"

        with patch("src.autostart.platform.system", return_value="Darwin"), \
             patch("src.autostart._get_plist_path", return_value=plist_path), \
             patch("subprocess.run"):
            from src.autostart import _set_autostart_macos
            result = _set_autostart_macos(True)

            assert result is True
            assert plist_path.exists()

    def test_macos_disable_removes_plist(self, tmp_path):
        """macOS 禁用应该删除 plist 文件。"""
        plist_dir = tmp_path / "LaunchAgents"
        plist_dir.mkdir()
        plist_path = plist_dir / f"{_MACOS_LABEL}.plist"
        plist_path.write_text("fake plist")

        with patch("src.autostart.platform.system", return_value="Darwin"), \
             patch("src.autostart._get_plist_path", return_value=plist_path), \
             patch("subprocess.run"):
            from src.autostart import _set_autostart_macos
            result = _set_autostart_macos(False)

            assert result is True
            assert not plist_path.exists()

    def test_macos_disable_nonexistent_no_error(self, tmp_path):
        """macOS 禁用不存在的 plist 应该不报错。"""
        plist_path = tmp_path / f"{_MACOS_LABEL}.plist"

        with patch("src.autostart.platform.system", return_value="Darwin"), \
             patch("src.autostart._get_plist_path", return_value=plist_path):
            from src.autostart import _set_autostart_macos
            result = _set_autostart_macos(False)
            assert result is True
