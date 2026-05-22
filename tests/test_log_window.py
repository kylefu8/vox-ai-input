from unittest.mock import MagicMock, patch

from src.log_window import _CMD_SHOW, LogWindow


def test_log_window_init_does_not_start_tk_thread():
    with patch.object(LogWindow, "_install_handler"), \
         patch("src.log_window.threading.Thread") as thread_cls:
        window = LogWindow()

    assert window._thread is None
    thread_cls.assert_not_called()


def test_log_window_show_starts_tk_thread_and_queues_show():
    with patch.object(LogWindow, "_install_handler"), \
         patch("src.log_window.threading.Thread") as thread_cls:
        thread = MagicMock()
        thread.is_alive.return_value = True
        thread_cls.return_value = thread

        window = LogWindow()
        window.show()

    thread_cls.assert_called_once()
    thread.start.assert_called_once()
    assert window._cmd_queue.get_nowait() == (_CMD_SHOW, None)


def test_log_window_show_reuses_running_thread():
    with patch.object(LogWindow, "_install_handler"), \
         patch("src.log_window.threading.Thread") as thread_cls:
        thread = MagicMock()
        thread.is_alive.return_value = True
        thread_cls.return_value = thread

        window = LogWindow()
        window.show()
        window.show()

    thread_cls.assert_called_once()
    assert thread.start.call_count == 1
    assert window._cmd_queue.qsize() == 2
