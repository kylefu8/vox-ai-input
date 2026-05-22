from unittest.mock import patch

from src import dialogs


def test_windows_info_dialog_uses_win32_without_tk():
    with patch("src.dialogs.platform.system", return_value="Windows"), \
         patch("src.dialogs._messagebox_win32") as win32_box, \
         patch("src.dialogs._messagebox_tk") as tk_box:
        dialogs.show_info("Title", "Message")

    win32_box.assert_called_once_with("Title", "Message", 0x00000040)
    tk_box.assert_not_called()


def test_windows_error_dialog_uses_win32_without_tk():
    with patch("src.dialogs.platform.system", return_value="Windows"), \
         patch("src.dialogs._messagebox_win32") as win32_box, \
         patch("src.dialogs._messagebox_tk") as tk_box:
        dialogs.show_error("Title", "Message")

    win32_box.assert_called_once_with("Title", "Message", 0x00000010)
    tk_box.assert_not_called()


def test_windows_yes_no_dialog_returns_win32_choice():
    with patch("src.dialogs.platform.system", return_value="Windows"), \
         patch("src.dialogs._messagebox_win32", return_value=6) as win32_box, \
         patch("src.dialogs._messagebox_tk") as tk_box:
        assert dialogs.ask_yes_no("Title", "Message") is True

    win32_box.assert_called_once_with("Title", "Message", 0x00000004 | 0x00000020)
    tk_box.assert_not_called()
