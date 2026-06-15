import time

from src.floating_control import (
    _ACTIVE_WIDTH,
    _CMD_RESET_IDLE,
    _HEIGHT,
    _IDLE_WIDTH,
    _PROCESSING_WIDTH,
    FloatingControl,
    _resting_position_from_window,
    _resting_position_from_window_rect,
    _render_control_image,
    _scaled_dim,
    _window_position_from_resting,
    _window_position_from_resting_rect,
)
from src.tray import STATE_IDLE, STATE_PROCESSING, STATE_RECORDING
from src.ui_theme import UI_THEMES


def _alpha_bbox(image):
    return image.getchannel("A").getbbox()


def test_floating_control_render_states_have_visible_pixels():
    now = time.monotonic()

    cases = [
        (
            (_IDLE_WIDTH, _HEIGHT),
            {
                "current": STATE_IDLE,
                "hover": False,
            },
        ),
        (
            (_PROCESSING_WIDTH, _HEIGHT),
            {
                "current": STATE_IDLE,
                "hover": True,
            },
        ),
        (
            (_ACTIVE_WIDTH, _HEIGHT),
            {
                "current": STATE_RECORDING,
                "bars": [0.2, 0.6, 0.9, 0.4, 0.7, 0.3, 0.5],
                "recording_started_at": now - 7,
            },
        ),
        (
            (_PROCESSING_WIDTH, _HEIGHT),
            {
                "current": STATE_PROCESSING,
                "phase": 1.2,
            },
        ),
    ]

    for expected_size, kwargs in cases:
        image = _render_control_image(
            theme="dark",
            language="zh_CN",
            now=now,
            **kwargs,
        )
        assert image.size == expected_size
        assert _alpha_bbox(image) is not None
        assert image.getchannel("A").getextrema()[1] > 220


def test_native_idle_state_uses_reset_command(monkeypatch):
    control = FloatingControl(enabled=True)
    control._started = True
    control._native_hwnd = 123
    control._state = STATE_PROCESSING
    control._window_width = _PROCESSING_WIDTH
    scheduled = []

    monkeypatch.setattr("src.floating_control.platform.system", lambda: "Windows")
    monkeypatch.setattr(control, "_wake_ui_thread", lambda: None)
    monkeypatch.setattr(control, "_schedule_native_idle_reset", lambda: scheduled.append(True))

    control.set_state(STATE_IDLE)

    cmd, payload = control._cmd_queue.get_nowait()
    assert cmd == _CMD_RESET_IDLE
    assert payload["state"] == STATE_IDLE
    assert scheduled == [True]


def test_native_idle_state_does_not_reset_when_already_collapsed(monkeypatch):
    control = FloatingControl(enabled=True)
    control._started = True
    control._native_hwnd = 123
    control._state = STATE_IDLE
    control._window_width = _IDLE_WIDTH
    scheduled = []

    monkeypatch.setattr("src.floating_control.platform.system", lambda: "Windows")
    monkeypatch.setattr(control, "_wake_ui_thread", lambda: None)
    monkeypatch.setattr(control, "_schedule_native_idle_reset", lambda: scheduled.append(True))

    control.set_state(STATE_IDLE)

    cmd, payload = control._cmd_queue.get_nowait()
    assert cmd != _CMD_RESET_IDLE
    assert payload["state"] == STATE_IDLE
    assert scheduled == []


def test_idle_button_keeps_clean_outer_padding():
    image = _render_control_image(
        theme="dark",
        language="zh_CN",
        current=STATE_IDLE,
        hover=False,
        now=time.monotonic(),
    )

    alpha_bbox = _alpha_bbox(image)
    assert alpha_bbox[0] >= 3
    assert alpha_bbox[1] >= 3
    assert alpha_bbox[2] <= _IDLE_WIDTH - 3
    assert alpha_bbox[3] <= _HEIGHT - 3


def test_floating_palettes_follow_main_ui_theme():
    from src.floating_control import _PALETTES

    assert _PALETTES["dark"]["bg"] == UI_THEMES["dark"]["surface"]
    assert _PALETTES["dark"]["text"] == UI_THEMES["dark"]["text"]
    assert _PALETTES["light"]["bg"] == UI_THEMES["light"]["surface2"]
    assert _PALETTES["light"]["bg"] != "#FFFFFF"
    assert _PALETTES["light"]["bg_hover"] == UI_THEMES["light"]["rail"]
    assert _PALETTES["light"]["idle_bg"] == UI_THEMES["light"]["rail"]
    assert _PALETTES["light"]["text"] == UI_THEMES["light"]["text"]
    assert _PALETTES["light"]["icon"] != _PALETTES["light"]["bg"]


def test_light_theme_renders_with_visible_idle_icon():
    image = _render_control_image(
        theme="light",
        language="zh_CN",
        current=STATE_IDLE,
        hover=False,
        now=time.monotonic(),
    )

    assert image.size == (_IDLE_WIDTH, _HEIGHT)
    assert _alpha_bbox(image) is not None
    assert image.getchannel("A").getextrema()[1] > 220
    assert image.getpixel((_IDLE_WIDTH // 2, 8))[:3] != (255, 255, 255)


def test_floating_control_render_scales_for_large_monitors():
    image = _render_control_image(
        theme="dark",
        language="zh_CN",
        current=STATE_IDLE,
        hover=False,
        now=time.monotonic(),
        ui_scale=1.3,
    )

    assert image.size == (_scaled_dim(_IDLE_WIDTH, 1.3), _scaled_dim(_HEIGHT, 1.3))
    assert _alpha_bbox(image) is not None


def test_position_model_uses_idle_position_as_single_source():
    rest_x, rest_y = 1600, 500

    for width in (_IDLE_WIDTH, _PROCESSING_WIDTH, _ACTIVE_WIDTH):
        expanded_x, expanded_y = _window_position_from_resting(
            rest_x,
            rest_y,
            width,
            screen_width=1920,
            screen_height=1080,
        )
        assert (expanded_x + width, expanded_y) == (rest_x + _IDLE_WIDTH, rest_y)

        collapsed_x, collapsed_y = _resting_position_from_window(
            expanded_x,
            expanded_y,
            width,
            screen_width=1920,
            screen_height=1080,
        )
        assert (collapsed_x, collapsed_y) == (rest_x, rest_y)


def test_position_model_allows_virtual_desktop_coordinates():
    rect = (-1920, 0, 3840, 2160)
    rest_x, rest_y = 2600, 900

    expanded_x, expanded_y = _window_position_from_resting_rect(
        rest_x,
        rest_y,
        _ACTIVE_WIDTH,
        rect,
    )
    assert (expanded_x + _ACTIVE_WIDTH, expanded_y) == (rest_x + _IDLE_WIDTH, rest_y)

    collapsed_x, collapsed_y = _resting_position_from_window_rect(
        expanded_x,
        expanded_y,
        _ACTIVE_WIDTH,
        rect,
    )
    assert (collapsed_x, collapsed_y) == (rest_x, rest_y)

    left_x, left_y = _window_position_from_resting_rect(-1800, 200, _IDLE_WIDTH, rect)
    assert left_x == -1800
    assert left_y == 200


def test_position_model_keeps_scaled_idle_position_as_anchor():
    rect = (-1920, 0, 3840, 2160)
    idle_width = _scaled_dim(_IDLE_WIDTH, 1.3)
    active_width = _scaled_dim(_ACTIVE_WIDTH, 1.3)
    height = _scaled_dim(_HEIGHT, 1.3)
    rest_x, rest_y = 2600, 900

    expanded_x, expanded_y = _window_position_from_resting_rect(
        rest_x,
        rest_y,
        active_width,
        rect,
        idle_width=idle_width,
        height=height,
    )
    assert (expanded_x + active_width, expanded_y) == (rest_x + idle_width, rest_y)

    collapsed_x, collapsed_y = _resting_position_from_window_rect(
        expanded_x,
        expanded_y,
        active_width,
        rect,
        idle_width=idle_width,
        height=height,
    )
    assert (collapsed_x, collapsed_y) == (rest_x, rest_y)
