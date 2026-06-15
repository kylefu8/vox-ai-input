from src.preview_overlay import (
    _MAX_WIDTH,
    _HEIGHT_STATUS_ONLY,
    _position_preview,
    _render_preview_image,
)
from src.floating_control import _scaled_dim


def _alpha_bbox(image):
    return image.getchannel("A").getbbox()


def test_preview_overlay_render_states_have_visible_pixels():
    cases = [
        {"status": "🎤 正在录音...", "text": ""},
        {"status": "📡 转写中...", "text": ""},
        {"status": "🤖 润色中...", "text": "这是一段正在处理的转写文本，用来验证结果预览胶囊的换行和高度。"},
        {"status": "✅ 完成", "text": "最终文本"},
        {"status": "⚠️ 润色失败，已使用原文", "text": "降级文本"},
    ]

    for kwargs in cases:
        image = _render_preview_image(theme="dark", **kwargs)
        assert image.width <= _MAX_WIDTH
        assert image.height >= _HEIGHT_STATUS_ONLY
        assert _alpha_bbox(image) is not None
        assert image.getchannel("A").getextrema()[1] > 220


def test_preview_overlay_light_theme_uses_main_ui_palette():
    image = _render_preview_image(
        text="Preview",
        status="完成",
        theme="light",
        phase=0,
    )

    assert image.size[0] >= 236
    assert image.getchannel("A").getbbox() is not None
    assert image.getchannel("A").getextrema()[1] > 220


def test_preview_overlay_render_scales_for_large_monitors():
    normal = _render_preview_image(
        text="Preview",
        status="Done",
        theme="dark",
        phase=0,
    )
    scaled = _render_preview_image(
        text="Preview",
        status="Done",
        theme="dark",
        phase=0,
        ui_scale=1.3,
    )

    assert scaled.width == _scaled_dim(normal.width, 1.3)
    assert scaled.height == _scaled_dim(normal.height, 1.3)
    assert _alpha_bbox(scaled) is not None


def test_preview_overlay_positions_below_anchor_when_possible():
    x, y = _position_preview(
        (260, 76),
        anchor=(100, 200, 42, 42),
        bounds=(0, 0, 800, 600),
    )

    assert y > 200 + 42
    assert 0 <= x <= 800 - 260


def test_preview_overlay_uses_bottom_center_without_anchor():
    x, y = _position_preview((260, 76), anchor=None, bounds=(0, 0, 800, 600))

    assert x == 270
    assert y == 600 - 76 - 88
