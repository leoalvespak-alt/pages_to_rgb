"""Contrato consolidado P2A-INTEGRACAO-2026-09-09 §2-§3 — validadores compartilhados.

Fonte: docs/contracts/INTEGRACAO_CONSOLIDADA_2026-09-09.md + S01.
Usado por gateway.py, handwritten.py, gateway_rgb.py e frame_upload.py.
"""

from __future__ import annotations

import re

# Contrato §2: ESP ids 1-63 chars ASCII alnum/_/-, sequence_id 1-64.
ESP_ID_PATTERN = r"^[A-Za-z0-9_-]{1,63}$"
ESP_SEQUENCE_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
_ESP_ID_RE = re.compile(ESP_ID_PATTERN)
_ESP_SEQ_RE = re.compile(ESP_SEQUENCE_PATTERN)

# Contrato §3.10: cursores JSON inteiros exatos 0..2^53-1.
MAX_EXACT_CURSOR = 2**53 - 1  # 9007199254740991

# Comandos conhecidos — §3.9: desconhecido nunca consome cursor.
KNOWN_GATEWAY_COMMANDS = frozenset(
    {"CAPTURE_PROBE", "CAPTURE_FULL", "PAUSE", "RESUME", "PING", "STOP"}
)


def is_valid_esp_id(value: str) -> bool:
    return bool(_ESP_ID_RE.match(value))


def is_valid_sequence_id(value: str) -> bool:
    return bool(_ESP_SEQ_RE.match(value))


def is_valid_cursor(value: int) -> bool:
    return isinstance(value, int) and 0 <= value <= MAX_EXACT_CURSOR


def validate_esp_id_or_raise(value: str, field: str) -> str:
    """Valida sem truncar (contrato §2: nunca truncar, rejeitar excesso)."""
    if not is_valid_esp_id(value):
        raise ValueError(
            f"{field} deve ter 1-63 chars ASCII alfanuméricos, _ ou - (sem truncamento)"
        )
    return value
