from unittest.mock import MagicMock, patch

from src.app import AIInputApp


def _app_with_updater(updater):
    app = AIInputApp.__new__(AIInputApp)
    app._updater = updater
    return app


def _updater(state):
    updater = MagicMock()
    updater.state = state
    updater.current_version = "1.2.3"
    updater.latest_version = "1.2.4"
    updater.download_size = 2048
    updater.update_mode = "lightweight"
    updater.download_url = "https://example.test/app.zip"
    updater.error_message = "network down"
    return updater


def test_update_flow_up_to_date_uses_shared_dialog():
    updater = _updater("up_to_date")
    app = _app_with_updater(updater)

    with patch("src.app.show_info") as show_info, \
         patch("src.app.show_error") as show_error, \
         patch("src.app.ask_yes_no") as ask_yes_no:
        app._update_flow()

    updater.check_for_updates.assert_called_once_with(background=False)
    show_info.assert_called_once()
    show_error.assert_not_called()
    ask_yes_no.assert_not_called()


def test_update_flow_error_uses_shared_dialog():
    updater = _updater("error")
    app = _app_with_updater(updater)

    with patch("src.app.show_info") as show_info, \
         patch("src.app.show_error") as show_error, \
         patch("src.app.ask_yes_no") as ask_yes_no:
        app._update_flow()

    show_info.assert_not_called()
    show_error.assert_called_once_with("检查更新失败", "network down")
    ask_yes_no.assert_not_called()


def test_update_flow_source_mode_opens_release_when_confirmed():
    updater = _updater("available")
    app = _app_with_updater(updater)

    with patch("src.updater._is_frozen", return_value=False), \
         patch("src.app.ask_yes_no", return_value=True) as ask_yes_no:
        app._update_flow()

    ask_yes_no.assert_called_once()
    updater.open_release_page.assert_called_once()


def test_update_flow_frozen_mode_downloads_when_confirmed():
    updater = _updater("available")
    app = _app_with_updater(updater)
    app._do_download_and_apply = MagicMock()

    with patch("src.updater._is_frozen", return_value=True), \
         patch("src.app.ask_yes_no", return_value=True):
        app._update_flow()

    app._do_download_and_apply.assert_called_once()


def test_download_error_uses_shared_dialog():
    updater = _updater("error")
    app = _app_with_updater(updater)

    with patch("src.app.show_error") as show_error:
        app._do_download_and_apply()

    updater.download_update.assert_called_once_with(background=False)
    show_error.assert_called_once_with("下载失败", "network down")


def test_download_ready_applies_update_when_confirmed():
    updater = _updater("ready")
    updater.apply_update.return_value = False
    app = _app_with_updater(updater)

    with patch("src.app.ask_yes_no", return_value=True):
        app._do_download_and_apply()

    updater.download_update.assert_called_once_with(background=False)
    updater.apply_update.assert_called_once()
