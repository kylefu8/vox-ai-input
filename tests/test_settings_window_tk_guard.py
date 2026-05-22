from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import src.settings_window as settings_window


class _ImmediateThread:
    def __init__(self, target, daemon=False):
        self._target = target
        self.daemon = daemon

    def start(self):
        self._target()


def test_open_settings_runs_window_inside_tk_guard():
    guard_owners = []

    @contextmanager
    def fake_guard(owner):
        guard_owners.append(owner)
        yield

    settings_window._settings_open = False
    try:
        with patch("src.settings_window.threading.Thread", _ImmediateThread), \
             patch("src.settings_window.exclusive_tk_root", fake_guard), \
             patch("src.settings_window.SettingsWindow") as window_cls:
            window = MagicMock()
            window_cls.return_value = window

            settings_window.open_settings({"ui": {"theme": "dark"}})

        assert guard_owners == ["settings"]
        window_cls.assert_called_once()
        window.run.assert_called_once()
    finally:
        settings_window._settings_open = False


def test_open_settings_marks_open_before_thread_runs():
    started = []

    class DeferredThread:
        def __init__(self, target, daemon=False):
            self._target = target
            self.daemon = daemon

        def start(self):
            started.append(self._target)

    settings_window._settings_open = False
    try:
        with patch("src.settings_window.threading.Thread", DeferredThread), \
             patch("src.settings_window.SettingsWindow") as window_cls:
            settings_window.open_settings({"ui": {"theme": "dark"}})
            settings_window.open_settings({"ui": {"theme": "dark"}})

        assert len(started) == 1
        assert settings_window._settings_open is True
        window_cls.assert_not_called()
    finally:
        settings_window._settings_open = False
