#!/usr/bin/env python3
"""Android gateway simulator — §2.6."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import struct
from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "http://localhost:8000/api/v1"
GATEWAY_TOKEN = "dev-gateway-token"  # noqa: S105 - local simulator credential
GATEWAY_ID = "sim-gateway-01"


@dataclass
class SimStats:
    sent: int = 0
    accepted: int = 0
    duplicate_idempotent: int = 0
    conflict: int = 0
    errors: int = 0


def _make_jpeg_bytes(index: int) -> bytes:
    """Generate a minimal JPEG-like payload (fake but valid magic bytes)."""
    data = b"\xff\xd8\xff" + b"\x00" * (100 + index % 50)
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rgb_items(payload: dict[str, Any]) -> bytes:
    answers = payload["answers"]
    defaults = payload["defaults"]
    palette = payload["palette"]
    overrides = {item["index"]: item for item in payload.get("overrides", [])}
    chunks: list[bytes] = []
    for index, answer in enumerate(answers):
        color = palette[answer]["rgb"]
        item = overrides.get(index, {})
        rgb = item.get("rgb", color)
        brightness = item.get("brightness_percent", defaults["brightness_percent"])
        on_ms = item.get("on_ms", defaults["on_ms"])
        off_ms = item.get("off_ms", defaults["off_ms"])
        chunks.append(
            struct.pack(
                "<BBBBBII",
                ord(answer),
                rgb[0],
                rgb[1],
                rgb[2],
                brightness,
                on_ms,
                off_ms,
            )
        )
    return b"".join(chunks)


def _validate_rgb_payload(payload: dict[str, Any], session_id: str, sequence_id: str) -> int:
    if payload["schema_version"] != 1:
        raise ValueError("unsupported RGB schema")
    if payload["session_id"] != session_id or payload["sequence_id"] != sequence_id:
        raise ValueError("RGB sequence metadata mismatch")
    answers = payload["answers"]
    if not answers or len(answers) > 1000 or any(answer not in "ABCDE" for answer in answers):
        raise ValueError("RGB answers are outside firmware limits")
    if payload["item_count"] != len(answers):
        raise ValueError("RGB item_count mismatch")
    raw = _rgb_items(payload)
    expected = hashlib.sha256(raw).hexdigest()
    if payload["sha256"] != expected:
        raise ValueError(f"RGB SHA mismatch: {payload['sha256']} != {expected}")
    if len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) > 262144:
        raise ValueError("RGB JSON exceeds firmware limit")
    return len(answers)


def _headers(gateway_id: str = GATEWAY_ID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {GATEWAY_TOKEN}",
        "X-Gateway-Id": gateway_id,
    }


def run_simulation(
    base_url: str,
    *,
    frames: int = 10,
    duplicate_rate: float = 0.0,
    corrupt_hash_rate: float = 0.0,
    drop_rate: float = 0.0,
    retry: bool = True,
    concurrency: int = 1,
) -> SimStats:
    stats = SimStats()
    client = httpx.Client(base_url=base_url, headers=_headers(), timeout=30)

    # hello
    r = client.post("/gateway/hello", json={"app_version": "sim-1.0", "gateway_code": GATEWAY_ID})
    print(f"hello: {r.status_code} {r.json()}")

    # session start
    r = client.post(
        "/gateway/session/start",
        json={"expected_pages": 5, "expected_questions": 10},
    )
    if r.status_code != 200:
        print(f"session start failed: {r.status_code} {r.text}")
        return stats

    session_id = r.json()["session_id"]
    print(f"session_id: {session_id}")

    capture_id = "capture-sim-01"

    for i in range(frames):
        if random.random() < drop_rate:  # noqa: S311 - fault injection only
            print(f"  frame {i}: dropped (simulated)")
            continue

        data = _make_jpeg_bytes(i)
        sha = _sha256(data)

        if random.random() < corrupt_hash_rate:  # noqa: S311 - fault injection only
            sha = "0" * 64  # bad hash

        is_dup = random.random() < duplicate_rate and i > 0  # noqa: S311 - simulation only
        frame_idx = max(0, i - 1) if is_dup else i

        files = {"file": ("frame.jpg", io.BytesIO(data), "image/jpeg")}
        resp = client.post(
            f"/gateway/session/{session_id}/frame",
            files=files,
            headers={
                **_headers(),
                "X-Frame-Index": str(frame_idx),
                "X-Capture-Id": capture_id,
                "X-SHA256": sha,
            },
        )
        stats.sent += 1

        if resp.status_code == 200:
            stats.accepted += 1
            print(f"  frame {frame_idx}: accepted")
        elif resp.status_code == 409:
            detail = resp.json().get("detail", "")
            if "conflict" in str(detail).lower() or "duplicate" in str(detail).lower():
                stats.conflict += 1
            else:
                stats.duplicate_idempotent += 1
            print(f"  frame {frame_idx}: 409 — {detail}")
        else:
            stats.errors += 1
            print(f"  frame {frame_idx}: error {resp.status_code} — {resp.text}")

    print(
        f"\nResults — sent={stats.sent} accepted={stats.accepted} "
        f"dup_idempotent={stats.duplicate_idempotent} conflicts={stats.conflict} "
        f"errors={stats.errors}"
    )
    return stats


def run_rgb_result_simulation(
    base_url: str,
    *,
    session_id: str,
    device_id: str = "CAM-001",
    polls: int = 5,
    resume_index: int = 0,
    mode: str = "normal",
) -> None:
    """Exercise the server-side result contract used by the Android gateway."""

    if mode == "network-failure":
        try:
            with httpx.Client(base_url="http://127.0.0.1:1", timeout=1) as failure_client:
                failure_client.get("/gateway/session/result")
        except httpx.RequestError as exc:
            print(f"expected network failure without synchronization sleep: {exc}")
            return
        raise RuntimeError("network-failure mode unexpectedly reached a live endpoint")

    gateway_id = "sim-unlinked-gateway" if mode == "unlinked-gateway" else GATEWAY_ID
    client = httpx.Client(base_url=base_url, headers=_headers(gateway_id), timeout=30)
    cursor = 0
    ready: dict[str, Any] | None = None

    for poll_number in range(polls):
        response = client.get(
            f"/gateway/session/{session_id}/result",
            params={"device_id": device_id, "cursor": cursor},
        )
        if response.status_code == 204:
            print(f"rgb poll {poll_number}: 204 cursor={cursor}")
            continue
        if mode == "unlinked-gateway" and response.status_code in {403, 404}:
            print(f"expected unlinked gateway rejection: {response.status_code}")
            return
        response.raise_for_status()
        command = response.json()
        cursor = command["cursor"]
        print(f"rgb poll {poll_number}: {command['command']} cursor={cursor}")
        if command["command"] == "RGB_SEQUENCE_READY":
            ready = command
            break
        if command["command"] == "RESULT_CANCELLED":
            return

    if ready is None:
        return
    assert ready is not None
    ready_command = ready

    sequence_id = ready_command["sequence_id"]
    payload_response = client.get(
        f"/gateway/session/{session_id}/rgb-sequence",
        params={"device_id": device_id, "sequence_id": sequence_id},
    )
    payload_response.raise_for_status()
    payload = payload_response.json()
    if mode == "invalid-hash":
        payload["sha256"] = "0" * 64
    elif mode == "invalid-item-count":
        payload["item_count"] += 1

    try:
        item_count = _validate_rgb_payload(payload, session_id, sequence_id)
    except ValueError as exc:
        if mode in {"invalid-hash", "invalid-item-count"}:
            print(f"expected RGB payload rejection ({mode}): {exc}")
            return
        raise
    if (
        payload["revision"] != ready_command["revision"]
        or payload["sha256"] != ready_command["sha256"]
    ):
        raise ValueError("RGB command and payload metadata differ")

    event_url = f"/gateway/session/{session_id}/rgb-sequence/event"

    def send_event(event: str, next_index: int) -> None:
        event_response = client.post(
            event_url,
            json={
                "device_id": device_id,
                "session_id": session_id,
                "sequence_id": sequence_id,
                "revision": ready_command["revision"],
                "event": event,
                "next_index": next_index,
                "item_count": item_count,
            },
            headers={"Idempotency-Key": f"sim-rgb-{event.lower()}-{next_index}"},
        )
        event_response.raise_for_status()
        print(f"rgb event {event}: {event_response.json()}")

    send_event("RECEIVED", 0)
    if mode == "invalid-event":
        send_event("INVALID", 0)
        return
    send_event("STARTED", 0)
    if resume_index:
        if not 0 < resume_index < item_count:
            raise ValueError("--rgb-resume-index must be inside the sequence")
        send_event("RESUMED", resume_index)
    send_event("COMPLETED", item_count)
    # A repeated COMPLETED must be accepted as an idempotent success.
    send_event("COMPLETED", item_count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Android gateway simulator")
    parser.add_argument("--url", default=BASE_URL)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--duplicate-rate", type=float, default=0.0)
    parser.add_argument("--corrupt-hash-rate", type=float, default=0.0)
    parser.add_argument("--drop-rate", type=float, default=0.0)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--rgb-session-id", default="")
    parser.add_argument("--rgb-device-id", default="CAM-001")
    parser.add_argument("--rgb-polls", type=int, default=5)
    parser.add_argument("--rgb-resume-index", type=int, default=0)
    parser.add_argument(
        "--rgb-mode",
        choices=(
            "normal",
            "invalid-event",
            "invalid-hash",
            "invalid-item-count",
            "unlinked-gateway",
            "network-failure",
        ),
        default="normal",
        help="RGB contract scenario to exercise",
    )
    args = parser.parse_args()

    if args.rgb_session_id:
        run_rgb_result_simulation(
            args.url,
            session_id=args.rgb_session_id,
            device_id=args.rgb_device_id,
            polls=args.rgb_polls,
            resume_index=args.rgb_resume_index,
            mode=args.rgb_mode,
        )
    else:
        run_simulation(
            args.url,
            frames=args.frames,
            duplicate_rate=args.duplicate_rate,
            corrupt_hash_rate=args.corrupt_hash_rate,
            drop_rate=args.drop_rate,
            retry=args.retry,
            concurrency=args.concurrency,
        )


if __name__ == "__main__":
    main()
