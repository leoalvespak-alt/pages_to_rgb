from types import SimpleNamespace

from src.pages_to_audio.rgb.publisher import _defaults, _snapshot_palette


def test_rgb_defaults_and_palette_come_from_session_snapshot() -> None:
    snapshot = {
        "brightness_percent": 25,
        "on_ms": 1200,
        "off_ms": 800,
        "handwritten_palette": {letter: {"rgb": [3, 4, 5]} for letter in "ABCDE"},
    }
    defaults = _defaults(snapshot)
    assert defaults.brightness_percent == 25
    assert defaults.on_ms == 1200
    assert defaults.off_ms == 800
    session = SimpleNamespace(session_type="HANDWRITTEN_WORD", config_snapshot=snapshot)
    assert _snapshot_palette(session)["A"].rgb == (3, 4, 5)  # type: ignore[arg-type]
