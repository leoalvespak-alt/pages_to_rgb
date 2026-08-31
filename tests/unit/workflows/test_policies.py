"""Unit tests for workflow timeout/retry policies — §42, §43."""

from __future__ import annotations

from datetime import timedelta

from src.pages_to_audio.workflows.policies import (
    ACTIVITY_MAX_ATTEMPTS,
    ANTHROPIC_ARBITER_TIMEOUT_S,
    ANTHROPIC_SOLVER_TIMEOUT_S,
    OCR_GOOGLE_TIMEOUT_S,
    PROVIDER_INTERNAL_RETRIES,
    SUPABASE_TIMEOUT_S,
    activity_timeout,
    default_retry_policy,
    llm_retry_policy,
    no_retry_policy,
    ocr_retry_policy,
)


def test_activity_timeout_exceeds_provider_plus_retries() -> None:
    """Rule §42: activity timeout > provider_timeout * (retries + 1)."""
    for provider_s in (OCR_GOOGLE_TIMEOUT_S, ANTHROPIC_SOLVER_TIMEOUT_S, SUPABASE_TIMEOUT_S):
        minimum = timedelta(seconds=provider_s * (PROVIDER_INTERNAL_RETRIES + 1))
        actual = activity_timeout(provider_s)
        assert actual > minimum, (
            f"activity_timeout({provider_s}s) must exceed minimum {minimum}"
        )


def test_default_retry_policy_max_attempts() -> None:
    p = default_retry_policy()
    assert p.maximum_attempts == ACTIVITY_MAX_ATTEMPTS


def test_no_retry_policy() -> None:
    p = no_retry_policy()
    assert p.maximum_attempts == 1


def test_ocr_retry_policy_sane() -> None:
    p = ocr_retry_policy()
    assert p.maximum_attempts >= 2
    assert p.backoff_coefficient is not None and p.backoff_coefficient >= 1.5


def test_llm_retry_policy_sane() -> None:
    p = llm_retry_policy()
    assert p.maximum_attempts >= 2


def test_all_timeouts_positive() -> None:
    from src.pages_to_audio.workflows.policies import (
        FFMPEG_ACTIVITY_OPTS,
        IMAGE_ACTIVITY_OPTS,
        LLM_ARBITER_ACTIVITY_OPTS,
        LLM_SOLVER_ACTIVITY_OPTS,
        OCR_ACTIVITY_OPTS,
        QUICK_ACTIVITY_OPTS,
        STORAGE_ACTIVITY_OPTS,
    )
    for bundle_name, bundle in [
        ("OCR", OCR_ACTIVITY_OPTS),
        ("LLM_SOLVER", LLM_SOLVER_ACTIVITY_OPTS),
        ("LLM_ARBITER", LLM_ARBITER_ACTIVITY_OPTS),
        ("STORAGE", STORAGE_ACTIVITY_OPTS),
        ("FFMPEG", FFMPEG_ACTIVITY_OPTS),
        ("IMAGE", IMAGE_ACTIVITY_OPTS),
        ("QUICK", QUICK_ACTIVITY_OPTS),
    ]:
        timeout = bundle.get("schedule_to_close_timeout")
        assert isinstance(timeout, timedelta), f"{bundle_name} must have timedelta timeout"
        assert timeout.total_seconds() > 0, f"{bundle_name} timeout must be positive"


def test_arbiter_timeout_exceeds_solver() -> None:
    solver = activity_timeout(ANTHROPIC_SOLVER_TIMEOUT_S)
    arbiter = activity_timeout(ANTHROPIC_ARBITER_TIMEOUT_S)
    assert arbiter > solver, "Arbiter must have more time budget than Solver"
