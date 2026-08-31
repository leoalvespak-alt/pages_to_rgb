"""Handwritten endpoints — 11 gates adaptada, isolada de EXAM."""

import hashlib
import struct

import pytest

from apps.api.main import create_app
from src.pages_to_audio.handwritten.mapping import word_to_letter
from src.pages_to_audio.rgb.canonical import build_payload, canonical_items_bytes
from src.pages_to_audio.rgb.policy import HANDWRITTEN_PALETTE, DEFAULT_PALETTE


@pytest.mark.unit
def test_handwritten_openapi_exposes_isolated_namespace() -> None:
    app = create_app()
    openapi = app.openapi()
    paths = openapi["paths"]
    required = {
        "/api/v1/handwritten/session/start",
        "/api/v1/handwritten/session/{session_id}/frame",
        "/api/v1/handwritten/session/{session_id}/capture-complete",
        "/api/v1/handwritten/session/{session_id}/end-signal",
        "/api/v1/handwritten/session/{session_id}/summary",
        "/api/v1/handwritten/session/{session_id}/policy",
        "/api/v1/handwritten/session/{session_id}/command",
        "/api/v1/handwritten/session/{session_id}/debug/publish-rgb",
    }
    missing = required - set(paths.keys())
    assert not missing, f"missing handwritten paths: {missing}"
    # Ensure EXAM namespace untouched
    assert "/api/v1/gateway/session/start" in paths


@pytest.mark.unit
def test_handwritten_gateway_routes_still_present() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"].keys())
    # Both namespaces coexist, 11 gates for EXAM still intact
    for p in ["/api/v1/gateway/session/start", "/api/v1/gateway/session/{session_id}/command", "/api/v1/gateway/session/{session_id}/frame"]:
        assert p in paths


@pytest.mark.unit
def test_handwritten_palette_and_defaults_match_exam_structure() -> None:
    from src.pages_to_audio.rgb.schemas import RgbDefaults

    defaults = RgbDefaults()
    # Same structure 12%/3000/5000 checked via canonical
    for letter in "ABCDE":
        assert HANDWRITTEN_PALETTE[letter].rgb is not None
        assert DEFAULT_PALETTE[letter].rgb is not None
    payload_hw, raw_hw = build_payload(
        session_id="S-hw-test",
        sequence_id="rgb-hw-test",
        revision=1,
        answers="ABCDE",
        defaults=defaults,
        palette=HANDWRITTEN_PALETTE,
    )
    payload_ex, raw_ex = build_payload(
        session_id="S-ex-test",
        sequence_id="rgb-ex-test",
        revision=1,
        answers="ABCDE",
        defaults=defaults,
        palette=DEFAULT_PALETTE,
    )
    # Same byte length, different sha due to palette
    assert len(canonical_items_bytes(payload_hw)) == len(canonical_items_bytes(payload_ex)) == 5 * 13
    assert payload_hw.sha256 != payload_ex.sha256
    # Both under 256 KiB
    assert len(raw_hw) < 262144
    assert len(raw_ex) < 262144


@pytest.mark.unit
def test_word_mapping_to_rgb_via_canonical() -> None:
    from src.pages_to_audio.rgb.schemas import RgbDefaults

    words_10 = ["João", "Maria", "Pedro", "Paula", "Fernanda"] * 2
    letters = "".join(word_to_letter(w) for w in words_10)  # type: ignore[arg-type]
    assert letters == "ABCDEABCDE"
    defaults = RgbDefaults()
    payload, raw = build_payload(
        session_id="S-10",
        sequence_id="rgb-10",
        revision=1,
        answers=letters,
        defaults=defaults,
        palette=HANDWRITTEN_PALETTE,
    )
    assert payload.item_count == 10
    # Check byte layout first item João=A=Azul 0,0,255 brightness 12 on 3000 off 5000
    b = canonical_items_bytes(payload)
    first = struct.unpack("<BBBBBII", b[0:13])
    assert first == (ord("A"), 0, 0, 255, 12, 3000, 5000)
    last = struct.unpack("<BBBBBII", b[-13:])
    assert last == (ord("E"), 255, 255, 0, 12, 3000, 5000)
    assert payload.sha256 == hashlib.sha256(b).hexdigest()
    assert len(raw) < 262144


@pytest.mark.unit
def test_r2_storage_adapter_exists_and_respects_immutable() -> None:
    from src.pages_to_audio.storage.r2_storage import R2StorageAdapter
    import asyncio

    adapter = R2StorageAdapter()
    # fake fallback
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(adapter.put_object("pages-to-rgb-originals", "k1", b"data", "image/jpeg", sha256="abc", overwrite=False))
        exists = loop.run_until_complete(adapter.object_exists("pages-to-rgb-originals", "k1"))
        assert exists is True
        # second put same key without overwrite should raise
        with pytest.raises(Exception):
            loop.run_until_complete(adapter.put_object("pages-to-rgb-originals", "k1", b"data2", "image/jpeg", sha256="abc2", overwrite=False))
        url = loop.run_until_complete(adapter.create_signed_url("pages-to-rgb-originals", "k1", 300))
        assert "expires=300" in url or "X-Amz" in url or "fake-r2" in url
    finally:
        loop.close()


@pytest.mark.unit
def test_settings_r2_fields_present() -> None:
    from src.pages_to_audio.config.settings import AppSettings

    s = AppSettings(STORAGE_PROVIDER="r2", R2_ACCOUNT_ID="acc", R2_ENDPOINT="https://acc.r2.cloudflarestorage.com")
    assert s.STORAGE_PROVIDER == "r2"
    assert s.R2_ACCOUNT_ID == "acc"
    assert s.r2.ACCOUNT_ID == "acc"
    assert s.R2_BUCKET_ORIGINALS == "pages-to-rgb-originals"
