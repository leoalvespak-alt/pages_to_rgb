"""Centralized timeout, retry and heartbeat policies — §42, §43, §44."""

from __future__ import annotations

from datetime import timedelta

from temporalio.common import RetryPolicy

# ---------------------------------------------------------------------------
# Provider-level timeouts (from §42)
# ---------------------------------------------------------------------------
HTTP_CONNECT_TIMEOUT_S: int = 10
HTTP_READ_TIMEOUT_S: int = 60
OCR_GOOGLE_TIMEOUT_S: int = 90
OCR_AZURE_TIMEOUT_S: int = 90
ANTHROPIC_SOLVER_TIMEOUT_S: int = 180
ANTHROPIC_ARBITER_TIMEOUT_S: int = 240
DEEPSEEK_TIMEOUT_S: int = 240
SUPABASE_TIMEOUT_S: int = 30
FFMPEG_TIMEOUT_S: int = 120

# Provider internal retries (§43)
PROVIDER_INTERNAL_RETRIES: int = 2
# Temporal activity max attempts (§43)
ACTIVITY_MAX_ATTEMPTS: int = 3
# Rescue rounds (§43)
RESCUE_ROUNDS: int = 3

# Heartbeat interval for long activities (§17.4)
HEARTBEAT_INTERVAL_S: int = 10


def activity_timeout(provider_timeout_s: int) -> timedelta:
    """Calculate activity schedule_to_close_timeout.

    Rule §42: activity timeout > provider timeout + (retries * provider_timeout).
    We add a generous buffer so Temporal never cuts off a legitimate retry cycle.
    """
    budget = provider_timeout_s * (PROVIDER_INTERNAL_RETRIES + 1)
    buffer = max(30, provider_timeout_s)
    return timedelta(seconds=budget + buffer)


def default_retry_policy(max_attempts: int = ACTIVITY_MAX_ATTEMPTS) -> RetryPolicy:
    return RetryPolicy(
        initial_interval=timedelta(seconds=2),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=60),
        maximum_attempts=max_attempts,
    )


def ocr_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        initial_interval=timedelta(seconds=5),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=120),
        maximum_attempts=ACTIVITY_MAX_ATTEMPTS,
    )


def llm_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        initial_interval=timedelta(seconds=10),
        backoff_coefficient=1.5,
        maximum_interval=timedelta(seconds=120),
        maximum_attempts=ACTIVITY_MAX_ATTEMPTS,
    )


def no_retry_policy() -> RetryPolicy:
    return RetryPolicy(maximum_attempts=1)


# Activity option bundles
OCR_ACTIVITY_OPTS = {
    "schedule_to_close_timeout": activity_timeout(OCR_GOOGLE_TIMEOUT_S),
    "retry_policy": ocr_retry_policy(),
    "heartbeat_timeout": timedelta(seconds=HEARTBEAT_INTERVAL_S * 3),
}

LLM_SOLVER_ACTIVITY_OPTS = {
    "schedule_to_close_timeout": activity_timeout(ANTHROPIC_SOLVER_TIMEOUT_S),
    "retry_policy": llm_retry_policy(),
    "heartbeat_timeout": timedelta(seconds=HEARTBEAT_INTERVAL_S * 6),
}

LLM_ARBITER_ACTIVITY_OPTS = {
    "schedule_to_close_timeout": activity_timeout(ANTHROPIC_ARBITER_TIMEOUT_S),
    "retry_policy": llm_retry_policy(),
    "heartbeat_timeout": timedelta(seconds=HEARTBEAT_INTERVAL_S * 6),
}

STORAGE_ACTIVITY_OPTS = {
    "schedule_to_close_timeout": activity_timeout(SUPABASE_TIMEOUT_S),
    "retry_policy": default_retry_policy(),
}

FFMPEG_ACTIVITY_OPTS = {
    "schedule_to_close_timeout": activity_timeout(FFMPEG_TIMEOUT_S),
    "retry_policy": default_retry_policy(max_attempts=2),
    "heartbeat_timeout": timedelta(seconds=HEARTBEAT_INTERVAL_S * 3),
}

IMAGE_ACTIVITY_OPTS = {
    "schedule_to_close_timeout": timedelta(seconds=300),
    "retry_policy": default_retry_policy(),
    "heartbeat_timeout": timedelta(seconds=HEARTBEAT_INTERVAL_S * 3),
}

QUICK_ACTIVITY_OPTS = {
    "schedule_to_close_timeout": timedelta(seconds=30),
    "retry_policy": default_retry_policy(),
}

# Non-retryable error types (§17.3) — Temporal will not retry these
NON_RETRYABLE_ERROR_TYPES: list[str] = [
    "NonRetryableError",
    "InvalidStateTransition",
    "FrameConflictError",
    "StorageOverwriteForbidden",
    "AuthError",
]
