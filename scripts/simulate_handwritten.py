#!/usr/bin/env python3
"""Handwritten simulator — 10 fotos, 1 palavra cada, 5 nomes x2."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-untyped]

BASE_URL = "http://localhost:8000/api/v1"
GATEWAY_TOKEN = "dev-gateway-token"  # noqa: S105
GATEWAY_ID = "sim-gateway-01"

WORDS = ["João", "Maria", "Pedro", "Paula", "Fernanda"] * 2  # 10

PALETTE = {
    "A": (0, 0, 255),
    "B": (255, 0, 0),
    "C": (0, 255, 0),
    "D": (128, 0, 128),
    "E": (255, 255, 0),
}
WORD_TO_LETTER = {
    "joao": "A",
    "maria": "B",
    "pedro": "C",
    "paula": "D",
    "fernanda": "E",
}


def _make_jpeg_with_word(word: str, index: int) -> bytes:
    img = Image.new("RGB", (800, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 80)
    except Exception:
        font = ImageFont.load_default()
    draw.text((80, 140), word, fill=(0, 0, 0), font=font)
    draw.text((10, 10), f"hw-{index}", fill=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _headers(gateway_id: str = GATEWAY_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {GATEWAY_TOKEN}", "X-Gateway-Id": gateway_id}


def _validate_rgb_payload(payload: dict[str, Any], session_id: str, sequence_id: str) -> None:
    assert payload["schema_version"] == 1
    assert payload["session_id"] == session_id
    assert payload["sequence_id"] == sequence_id
    raw = b"".join(
        struct.pack(
            "<BBBBBII",
            ord(payload["answers"][i]),
            payload["palette"][payload["answers"][i]]["rgb"][0],
            payload["palette"][payload["answers"][i]]["rgb"][1],
            payload["palette"][payload["answers"][i]]["rgb"][2],
            payload["defaults"]["brightness_percent"],
            payload["defaults"]["on_ms"],
            payload["defaults"]["off_ms"],
        )
        for i in range(len(payload["answers"]))
    )
    assert payload["sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(json.dumps(payload, separators=(",", ":")).encode()) <= 262144


def run_simulation(base_url: str, words: list[str] | None = None) -> None:
    words = words or WORDS
    client = httpx.Client(base_url=base_url, headers=_headers(), timeout=30)
    r = client.post(
        "/handwritten/session/start",
        json={"expected_words": len(words), "device_code": "CAM-001", "gateway_code": GATEWAY_ID},
    )
    if r.status_code != 200:
        print(f"handwritten start failed: {r.status_code} {r.text}")
        return
    session_id = r.json()["session_id"]
    print(f"session_id: {session_id} words={len(words)}")
    capture_id = "hw-cap-01"
    for idx, word in enumerate(words):
        data = _make_jpeg_with_word(word, idx)
        sha = _sha256(data)
        files = {"file": ("frame.jpg", io.BytesIO(data), "image/jpeg")}
        resp = client.post(
            f"/handwritten/session/{session_id}/frame",
            files=files,
            headers={
                **_headers(),
                "X-Frame-Index": str(idx),
                "X-Capture-Id": capture_id,
                "X-SHA256": sha,
                "X-Resolution": "800x400",
                "X-Received-Android-At": "2026-08-31T12:00:00Z",
                "X-Orientation": "0",
            },
        )
        print(
            f"  frame {idx} word={word} -> {resp.status_code} {'dup' if resp.json().get('duplicate') else 'ok' if resp.status_code == 200 else resp.text}"
        )
    r = client.post(
        f"/handwritten/session/{session_id}/capture-complete",
        params={"capture_id": capture_id, "received_frames": len(words)},
    )
    print(f"capture-complete: {r.status_code} {r.text}")
    r = client.post(f"/handwritten/session/{session_id}/end-signal", json={})
    print(f"end-signal: {r.status_code} {r.text}")
    r = client.get(f"/handwritten/session/{session_id}/summary")
    print(f"summary: {r.status_code} {json.dumps(r.json(), indent=2, ensure_ascii=False)[:800]}")
    # debug publish
    r = client.post(f"/handwritten/session/{session_id}/debug/publish-rgb")
    print(f"publish-rgb: {r.status_code} {r.text}")
    if r.status_code == 200 and r.json().get("sequence_id"):
        seq_id = r.json()["sequence_id"]
        # try get rgb sequence via gateway? handwritten uses same publisher table, but endpoint for rgb is via gateway? For now use handwritten summary
        print(f"sequence_id: {seq_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Handwritten simulator (10 words)")
    parser.add_argument("--url", default=BASE_URL)
    parser.add_argument("--words", nargs="*", default=None)
    args = parser.parse_args()
    run_simulation(args.url, args.words)


if __name__ == "__main__":
    main()
