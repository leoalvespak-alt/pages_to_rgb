#!/usr/bin/env python3
"""Full exam simulation — §3.8.1."""

from __future__ import annotations

import random
import time

from scripts.simulate_android import GATEWAY_ID, GATEWAY_TOKEN, _headers, _make_jpeg_bytes, _sha256

import httpx

BASE_URL = "http://localhost:8000/api/v1"


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, headers=_headers(), timeout=30)

    # Start session
    r = client.post("/gateway/session/start", json={"expected_pages": 3})
    session_id = r.json()["session_id"]
    print(f"Session: {session_id}")

    for page in range(3):
        capture_id = f"capture-{page:03d}"

        # Send 3 frames per page
        for f in range(3):
            data = _make_jpeg_bytes(page * 10 + f)
            sha = _sha256(data)

            import io
            files = {"file": ("frame.jpg", io.BytesIO(data), "image/jpeg")}
            r = client.post(
                f"/gateway/session/{session_id}/frame",
                files=files,
                headers={
                    **_headers(),
                    "X-Frame-Index": str(f),
                    "X-Capture-Id": capture_id,
                    "X-SHA256": sha,
                },
            )
            print(f"  Page {page} frame {f}: {r.status_code}")

        time.sleep(0.1)

    print("Exam simulation complete.")


if __name__ == "__main__":
    main()
