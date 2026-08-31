from __future__ import annotations

import uuid


def new_uuid() -> str:
    return str(uuid.uuid4())


def new_public_id() -> str:
    return uuid.uuid4().hex[:16]
