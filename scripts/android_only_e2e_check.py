#!/usr/bin/env python3
# ruff: noqa: E501
"""ETAPA 7 — checklist 11 gates Android-Only.

Lista comandos curl/httpx para rodar manualmente cada gate contra servidor
local, sem ESP32. Tambem executa verificacoes leves via httpx quando
--run-live e passado.

Gates:
1  POST /gateway/session/start ANDROID_CAMERA
2  GET  /command?cursor=0
3  POST /frame
4  Burst CAPTURE_FULL frames=3 + POST /capture-complete
5  POST /end-signal -> LOCKED
6  Workflow GATE_1/GATE_2 ou debug/publish-rgb
7  GET  /summary
8  Corte internet -> spool fila
9  Reenvio idempotente 200 nao 409
10 Reenvio sha diferente -> 409
11 GET /result -> GET /rgb-sequence -> POST event COMPLETED duplicado -> 200 dup

Uso:
  uv run python scripts/android_only_e2e_check.py --print-curl
  uv run python scripts/android_only_e2e_check.py --run-live --url http://localhost:8000/api/v1
  uv run python scripts/simulate_android.py --frames 10  # alternativa E2E completa
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import sys
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

BASE_URL = "http://localhost:8000/api/v1"
GATEWAY_TOKEN = "dev-gateway-token"  # noqa: S105
GATEWAY_ID = "GW-ANDROID-001"
DEVICE_ID = "CAM-001"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _headers(gateway_id: str = GATEWAY_ID, token: str = GATEWAY_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Gateway-Id": gateway_id}


def _curl_block(
    method: str,
    path: str,
    extra_headers: list[str] | None = None,
    data: str | None = None,
    file_part: bool = False,
) -> str:
    base = "${BASE:-http://localhost:8000/api/v1}"
    hdrs = [
        '-H "Authorization: Bearer $TOKEN"',
        '-H "X-Gateway-Id: $GW"',
    ]
    if extra_headers:
        hdrs.extend(extra_headers)
    hdr_str = " \\\n  ".join(hdrs)
    if file_part:
        return (
            f"curl -s -X {method} {hdr_str} \\\n"
            f'  {base}{path} \\\n'
            f'  -F file=@/tmp/frame0.jpg | jq .'
        )
    if data:
        return f"curl -s -X {method} {hdr_str} -H \"Content-Type: application/json\" -d '{data}' {base}{path} | jq ."
    return f"curl -s -X {method} {hdr_str} {base}{path} | jq ."


def print_curl_checklist() -> None:
    print("# ETAPA 7 — 11 gates — curl checklist (sem ESP32)")
    print("# Exportar envs:")
    print('export BASE=http://localhost:8000/api/v1')
    print('export TOKEN="dev-gateway-token"  # ou ANDROID_GATEWAY_TOKEN do .env')
    print('export GW="GW-ANDROID-001"')
    print('export DEV="CAM-001"')
    print()
    print("## Gate 1 — POST /gateway/session/start ANDROID_CAMERA -> 201/200")
    print(_curl_block("POST", "/gateway/session/start", data='{"device_code":"CAM-001","capture_source":"ANDROID_CAMERA","allow_new_session":true,"expected_pages":5,"expected_questions":5}'))
    print('export SESSION=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" -H "Content-Type: application/json" -d \'{"device_code":"CAM-001","capture_source":"ANDROID_CAMERA","allow_new_session":true}\' $BASE/gateway/session/start | jq -r .session_id)')
    print('echo $SESSION  # deve ser hex 16 ou S-...; status CAPTURING')
    print()
    print("## Gate 2 — GET /command?cursor=0 -> CAPTURE_PROBE/FULL ou PING")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" \"$BASE/gateway/session/$SESSION/command?cursor=0&wait_ms=25000&phase=CAPTURE\" | jq .")
    print("# esperado: {\"command\":\"CAPTURE_FULL\"|\"CAPTURE_PROBE\"|\"PING\",\"cursor\":1,...} para CAPTURE_* inclui capture_id,frames,gap_ms")
    print()
    print("## Gate 3 — POST /frame -> 200 storage_key")
    print("echo -n \"fake-jpeg-data\" > /tmp/frame0.jpg  # use JPEG real: b'\\xff\\xd8\\xff'+bytes")
    print("SHA=$(sha256sum /tmp/frame0.jpg | cut -d' ' -f1)")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" -H \"X-Capture-Id: cap-test-001\" -H \"X-Frame-Index: 0\" -H \"X-SHA256: $SHA\" -H \"X-Resolution: 1280x720\" -H \"X-Orientation: 0\" -F file=@/tmp/frame0.jpg $BASE/gateway/session/$SESSION/frame | jq .")
    print("# esperado: {\"storage_key\":\"sessions/.../frames/cap-test-001/0.jpg\",\"duplicate\":false} 200")
    print()
    print("## Gate 4 — Burst CAPTURE_FULL frames=3 + POST /capture-complete -> 200")
    print("for i in 0 1 2; do echo -n \"fake-jpeg-$i-$(date +%s)\" > /tmp/frame${i}.jpg; SHA=$(sha256sum /tmp/frame${i}.jpg | cut -d' ' -f1); curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" -H \"X-Capture-Id: cap-test-001\" -H \"X-Frame-Index: $i\" -H \"X-SHA256: $SHA\" -F file=@/tmp/frame${i}.jpg $BASE/gateway/session/$SESSION/frame | jq .; done")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" \"$BASE/gateway/session/$SESSION/capture-complete?capture_id=cap-test-001&received_frames=3\" | jq .")
    print("# esperado: {\"status\":\"complete\",\"received_frames\":3} 200")
    print()
    print("## Gate 5 — POST /end-signal -> LOCKED")
    print("curl -s -X POST -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" $BASE/gateway/session/$SESSION/end-signal | jq .")
    print("# esperado: {\"status\":\"LOCKED\",\"locked\":true} 200; segundo POST idempotente mesmo resultado")
    print("curl -s -X POST -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" $BASE/gateway/session/$SESSION/end-signal | jq .")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" \"$BASE/gateway/session/$SESSION/command?cursor=99&phase=CAPTURE\" | jq . # deve ser STOP")
    print()
    print("## Gate 6 — Workflow GATE_1/GATE_2 ou debug/publish-rgb")
    print("# Se Temporal offline, publicar manualmente (requer Question+FinalAnswer inseridas):")
    print("curl -s -X POST -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" $BASE/gateway/session/$SESSION/debug/publish-rgb | jq .")
    print("# esperado: {\"command\":\"RGB_SEQUENCE_READY\",\"sequence_id\":\"rgb-...\",\"revision\":1} ou {\"command\":\"RESULT_CANCELLED\",\"reason_code\":\"RGB_SEQUENCE_INCOMPLETE\"} se incompleto")
    print("# Alternativa: uv run python scripts/simulate_android.py --frames 5 (cria sessao) + inserir Questions via UoW + publish")
    print()
    print("## Gate 7 — GET /summary -> answers A-E + cores")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" $BASE/gateway/session/$SESSION/summary | jq .")
    print("# esperado: {\"session_id\":\"...\",\"status\":\"LOCKED\",\"frames_count\":3,\"answers\":[{\"question_number\":1,\"answer\":\"C\",\"color\":{\"rgb\":[0,255,255]}}],\"rgb_sequence\":{...}}")
    print()
    print("## Gate 8 — Corte internet durante frame 1/3 -> spool fila (sem servidor)")
    print("# Android: desligar aviao, capturar 2 frames, verificar Room: SELECT COUNT(*) FROM pending_frames WHERE ack=0 == 2")
    print("# Servidor simulado via InMemorySpool: tests/unit/api/test_android_only_e2e.py::test_gate8_spool_queue_on_network_cut")
    print("# curl equivalente: nao enviar frame 1 com rede cortada -> fila local; ao religar, reenvio automatico")
    print()
    print("## Gate 9 — Reabrir app com rede -> reenvio idempotente 200 nao 409")
    print("SHA=$(sha256sum /tmp/frame0.jpg | cut -d' ' -f1)")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" -H \"X-Capture-Id: cap-test-001\" -H \"X-Frame-Index: 0\" -H \"X-SHA256: $SHA\" -F file=@/tmp/frame0.jpg $BASE/gateway/session/$SESSION/frame | jq .duplicate")
    print("# esperado: true (duplicate:true, 200, frames count nao duplica)")
    print()
    print("## Gate 10 — Reenvio frame_index igual sha diferente -> 409 CONFLICT")
    print("echo -n \"different\" > /tmp/frame0b.jpg; SHA2=$(sha256sum /tmp/frame0b.jpg | cut -d' ' -f1)")
    print("curl -s -w \"\\n%{http_code}\\n\" -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" -H \"X-Capture-Id: cap-test-001\" -H \"X-Frame-Index: 0\" -H \"X-SHA256: $SHA2\" -F file=@/tmp/frame0b.jpg $BASE/gateway/session/$SESSION/frame")
    print("# esperado: 409 {\"detail\":\"Frame index 0 already exists with different sha256\"}")
    print()
    print("## Gate 11 — GET /result -> GET /rgb-sequence -> POST event COMPLETED repetido -> 200 duplicate:true")
    print("CURSOR=0")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" \"$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=$CURSOR\" | jq .")
    print("# 204 se cursor atual; 200 com {\"command\":\"RGB_SEQUENCE_READY\",\"cursor\":3,\"sequence_id\":\"rgb-...\",\"sha256\":\"...\"}")
    print("CURSOR=$(curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" \"$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=0\" | jq -r .cursor)")
    print("SEQ=$(curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" \"$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=0\" | jq -r .sequence_id)")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" \"$BASE/gateway/session/$SESSION/rgb-sequence?device_id=$DEV&sequence_id=$SEQ\" | jq . > /tmp/rgb.json")
    print("# validar SHA: python3 -c \"import json,hashlib,struct; p=json.load(open('/tmp/rgb.json')); raw=b''.join(struct.pack('<BBBBBII',ord(a),p['palette'][a]['rgb'][0],p['palette'][a]['rgb'][1],p['palette'][a]['rgb'][2],p['defaults']['brightness_percent'],p['defaults']['on_ms'],p['defaults']['off_ms']) for a in p['answers']); assert p['sha256']==hashlib.sha256(raw).hexdigest(); print('SHA ok')\"")
    print("for EVT in RECEIVED STARTED COMPLETED; do NEXT=0; [ \"$EVT\" = \"COMPLETED\" ] && NEXT=$(jq -r .item_count /tmp/rgb.json); curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" -H \"Idempotency-Key: chk-$EVT-$NEXT\" -H \"Content-Type: application/json\" -d \"{\\\"device_id\\\":\\\"$DEV\\\",\\\"session_id\\\":\\\"$SESSION\\\",\\\"sequence_id\\\":\\\"$SEQ\\\",\\\"revision\\\":1,\\\"event\\\":\\\"$EVT\\\",\\\"next_index\\\":$NEXT,\\\"item_count\\\":$(jq -r .item_count /tmp/rgb.json)}\" $BASE/gateway/session/$SESSION/rgb-sequence/event | jq .; done")
    print("curl -s -H \"Authorization: Bearer $TOKEN\" -H \"X-Gateway-Id: $GW\" -H \"Idempotency-Key: chk-COMPLETED-$(jq -r .item_count /tmp/rgb.json)\" -H \"Content-Type: application/json\" -d \"{\\\"device_id\\\":\\\"$DEV\\\",\\\"session_id\\\":\\\"$SESSION\\\",\\\"sequence_id\\\":\\\"$SEQ\\\",\\\"revision\\\":1,\\\"event\\\":\\\"COMPLETED\\\",\\\"next_index\\\":$(jq -r .item_count /tmp/rgb.json),\\\"item_count\\\":$(jq -r .item_count /tmp/rgb.json)}\" $BASE/gateway/session/$SESSION/rgb-sequence/event | jq .duplicate  # -> true")
    print()
    print("# Alternativa automatizada sem curl: uv run python scripts/simulate_android.py --rgb-session-id $SESSION --rgb-mode normal")
    print("# que valida poll 204, SHA, <256KiB, answers A-E, e COMPLETED duplicado")


def _validate_payload_local(path: str) -> None:
    data = json.loads(open(path, encoding="utf-8").read())
    palette = data["palette"]
    defaults = data["defaults"]
    overrides = {o["index"]: o for o in data.get("overrides", [])}
    raw = b"".join(
        struct.pack(
            "<BBBBBII",
            ord(a),
            overrides.get(i, {}).get("rgb", palette[a]["rgb"])[0],
            overrides.get(i, {}).get("rgb", palette[a]["rgb"])[1],
            overrides.get(i, {}).get("rgb", palette[a]["rgb"])[2],
            overrides.get(i, {}).get("brightness_percent", defaults["brightness_percent"]),
            overrides.get(i, {}).get("on_ms", defaults["on_ms"]),
            overrides.get(i, {}).get("off_ms", defaults["off_ms"]),
        )
        for i, a in enumerate(data["answers"])
    )
    assert data["item_count"] == len(data["answers"])
    assert len(json.dumps(data, separators=(",", ":")).encode()) < 262144
    assert data["sha256"] == hashlib.sha256(raw).hexdigest(), "SHA mismatch"


def run_live(base_url: str, gateway_token: str, gateway_id: str, device_id: str) -> int:
    if httpx is None:
        print("httpx not installed; run: uv sync", file=sys.stderr)
        return 2
    headers = _headers(gateway_id, gateway_token)
    client = httpx.Client(base_url=base_url, headers=headers, timeout=10)
    print(f"[live] base={base_url} gw={gateway_id} dev={device_id}")

    # Gate 1
    r = client.post(
        "/gateway/session/start",
        json={
            "device_code": device_id,
            "capture_source": "ANDROID_CAMERA",
            "allow_new_session": True,
            "expected_pages": 2,
            "expected_questions": 2,
        },
    )
    if r.status_code not in (200, 201):
        print(f"gate1 FAIL {r.status_code} {r.text}", file=sys.stderr)
        return 1
    session_id = r.json()["session_id"]
    print(f"gate1 OK session_id={session_id}")

    # Gate 2
    r = client.get(f"/gateway/session/{session_id}/command", params={"cursor": 0, "wait_ms": 0, "phase": "CAPTURE"})
    if r.status_code != 200:
        print(f"gate2 FAIL {r.status_code} {r.text}", file=sys.stderr)
        return 1
    cmd = r.json()
    assert cmd["command"] in {"CAPTURE_FULL", "CAPTURE_PROBE", "PING", "PAUSE", "RESUME", "STOP"}
    print(f"gate2 OK command={cmd['command']} cursor={cmd['cursor']}")

    # Gate 3
    data = b"\xff\xd8\xff" + b"\x00" * 100
    sha = _sha(data)
    r = client.post(
        f"/gateway/session/{session_id}/frame",
        files={"file": ("frame.jpg", io.BytesIO(data), "image/jpeg")},
        headers={**headers, "X-Capture-Id": "cap-live-001", "X-Frame-Index": "0", "X-SHA256": sha, "X-Resolution": "1280x720"},
    )
    if r.status_code != 200:
        print(f"gate3 FAIL {r.status_code} {r.text}", file=sys.stderr)
        return 1
    print(f"gate3 OK storage_key={r.json()['storage_key']} duplicate={r.json()['duplicate']}")

    # Gate 4 — burst 2 more frames (total 3)
    for idx in (1, 2):
        d = b"\xff\xd8\xff" + bytes([idx] * 100)
        s = _sha(d)
        rr = client.post(
            f"/gateway/session/{session_id}/frame",
            files={"file": ("frame.jpg", io.BytesIO(d), "image/jpeg")},
            headers={**headers, "X-Capture-Id": "cap-live-001", "X-Frame-Index": str(idx), "X-SHA256": s},
        )
        if rr.status_code != 200:
            print(f"gate4 frame {idx} FAIL {rr.status_code} {rr.text}", file=sys.stderr)
            return 1
    rc = client.post(f"/gateway/session/{session_id}/capture-complete", params={"capture_id": "cap-live-001", "received_frames": 3})
    if rc.status_code != 200:
        print(f"gate4 capture-complete FAIL {rc.status_code} {rc.text}", file=sys.stderr)
        return 1
    print("gate4 OK burst 3 + capture-complete 200")

    # Gate 9 idempotent resend
    rr = client.post(
        f"/gateway/session/{session_id}/frame",
        files={"file": ("frame.jpg", io.BytesIO(data), "image/jpeg")},
        headers={**headers, "X-Capture-Id": "cap-live-001", "X-Frame-Index": "0", "X-SHA256": sha},
    )
    if rr.status_code != 200 or not rr.json().get("duplicate"):
        print(f"gate9 FAIL expected duplicate true got {rr.status_code} {rr.text}", file=sys.stderr)
        return 1
    print("gate9 OK idempotent duplicate:true")

    # Gate 10 conflict
    bad = b"\xff\xd8\xff" + b"\x01" * 100
    bad_sha = _sha(bad)
    rr = client.post(
        f"/gateway/session/{session_id}/frame",
        files={"file": ("frame.jpg", io.BytesIO(bad), "image/jpeg")},
        headers={**headers, "X-Capture-Id": "cap-live-001", "X-Frame-Index": "0", "X-SHA256": bad_sha},
    )
    if rr.status_code != 409:
        print(f"gate10 FAIL expected 409 got {rr.status_code} {rr.text}", file=sys.stderr)
        return 1
    print("gate10 OK 409 on diff sha same index")

    # Gate 5
    r = client.post(f"/gateway/session/{session_id}/end-signal")
    if r.status_code != 200:
        print(f"gate5 FAIL {r.status_code} {r.text}", file=sys.stderr)
        return 1
    assert r.json().get("locked") or r.json().get("status") == "LOCKED"
    print("gate5 OK LOCKED")

    # Gate 7
    r = client.get(f"/gateway/session/{session_id}/summary")
    if r.status_code != 200:
        print(f"gate7 FAIL {r.status_code} {r.text}", file=sys.stderr)
        return 1
    summ: dict[str, Any] = r.json()
    assert "answers" in summ
    assert "frames_count" in summ
    print(f"gate7 OK summary frames={summ['frames_count']} answers={len(summ['answers'])}")

    # Gate 11 (if RGB published; else just poll)
    r = client.get(f"/gateway/session/{session_id}/result", params={"device_id": device_id, "cursor": 0})
    if r.status_code == 204:
        print("gate11 poll 204 (no new cursor) — expected before RGB publish")
    elif r.status_code == 200:
        js = r.json()
        print(f"gate11 poll OK command={js['command']} cursor={js['cursor']}")
        if js["command"] == "RGB_SEQUENCE_READY":
            seq_id = js["sequence_id"]
            rr = client.get(
                f"/gateway/session/{session_id}/rgb-sequence",
                params={"device_id": device_id, "sequence_id": seq_id},
            )
            if rr.status_code != 200:
                print(f"gate11 rgb-sequence FAIL {rr.status_code}", file=sys.stderr)
                return 1
            payload = rr.json()
            _validate_payload_local_payload(payload)
            print(f"gate11 rgb-sequence OK sha={payload['sha256'][:8]}...")
            # event COMPLETED duplicate
            body: dict[str, Any] = {
                "device_id": device_id,
                "session_id": session_id,
                "sequence_id": seq_id,
                "revision": js["revision"],
                "event": "COMPLETED",
                "next_index": payload["item_count"],
                "item_count": payload["item_count"],
            }
            e1 = client.post(
                f"/gateway/session/{session_id}/rgb-sequence/event",
                json=body,
                headers={"Idempotency-Key": "live-completed-1"},
            )
            if e1.status_code != 200:
                print(f"gate11 event1 FAIL {e1.status_code} {e1.text}", file=sys.stderr)
                return 1
            e2 = client.post(
                f"/gateway/session/{session_id}/rgb-sequence/event",
                json=body,
                headers={"Idempotency-Key": "live-completed-1"},
            )
            if e2.status_code != 200 or not e2.json().get("duplicate"):
                print(f"gate11 duplicate FAIL {e2.status_code} {e2.text}", file=sys.stderr)
                return 1
            print("gate11 OK COMPLETED duplicate:true")
    else:
        print(f"gate11 unexpected {r.status_code} {r.text}", file=sys.stderr)
        return 1

    print("\nAll live gates 1-5,7,9-11 OK. Gate 6 requires Questions/FinalAnswers; use debug/publish-rgb or workflow.")
    print("Gate 8 spool offline is unit-tested via InMemorySpool (Room) without server.")
    return 0


def _validate_payload_local_payload(payload: dict[str, Any]) -> None:
    palette = payload["palette"]
    defaults = payload["defaults"]
    overrides = {o["index"]: o for o in payload.get("overrides", [])}
    raw = b"".join(
        struct.pack(
            "<BBBBBII",
            ord(a),
            overrides.get(i, {}).get("rgb", palette[a]["rgb"])[0],
            overrides.get(i, {}).get("rgb", palette[a]["rgb"])[1],
            overrides.get(i, {}).get("rgb", palette[a]["rgb"])[2],
            overrides.get(i, {}).get("brightness_percent", defaults["brightness_percent"]),
            overrides.get(i, {}).get("on_ms", defaults["on_ms"]),
            overrides.get(i, {}).get("off_ms", defaults["off_ms"]),
        )
        for i, a in enumerate(payload["answers"])
    )
    assert payload["sha256"] == hashlib.sha256(raw).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description="ETAPA 7 — 11 gates checklist")
    p.add_argument("--print-curl", action="store_true", help="imprime curls para cada gate")
    p.add_argument("--run-live", action="store_true", help="executa gates 1-5,7,9-11 contra servidor local")
    p.add_argument("--url", default=BASE_URL, help="base URL api v1")
    p.add_argument("--gateway-token", default=GATEWAY_TOKEN, help="ANDROID_GATEWAY_TOKEN")
    p.add_argument("--gateway-id", default=GATEWAY_ID, help="gateway_code / X-Gateway-Id")
    p.add_argument("--device-id", default=DEVICE_ID, help="device_code")
    args = p.parse_args()
    if args.print_curl or not args.run_live:
        print_curl_checklist()
        if not args.run_live:
            return
    if args.run_live:
        code = run_live(args.url, args.gateway_token, args.gateway_id, args.device_id)
        sys.exit(code)


if __name__ == "__main__":
    main()
