"""Anthropic Claude provider for Solver/Verifier/Arbiter — §26, §27.1, §42, §43.

Uses httpx REST (no vendor SDK — §26 forbids vendor imports in domain; providers are
infrastructure but we use httpx to stay consistent and avoid optional dependency).

Models are configured via settings, never hardcoded (§8.3.1).
Timeouts: solver/verifier 180s, arbiter 240s (§42).
Retries: 2 internal (§43).
§16: reasoning/private content is never logged or stored.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.domain.ports.reasoning import (
    ArbitrateRequest,
    ArbitrateResult,
    SolveRequest,
    SolveResult,
    VerifyRequest,
    VerifyResult,
)
from src.pages_to_audio.llm.concurrency import get_semaphore
from src.pages_to_audio.llm.prompt_registry import get_prompt
from src.pages_to_audio.llm.schemas import (
    ArbiterOutput,
    SolverOutput,
    VerifierOutput,
    parse_llm_output,
    validate_answer_in_alternatives,
)
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_SOLVER_TIMEOUT_S = 180.0
_ARBITER_TIMEOUT_S = 240.0
_MAX_TOKENS = 512

PROVIDER_NAME = "anthropic"


class AnthropicProvider:
    """Implements ReasoningProvider using Anthropic Messages API."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        self._api_key = cfg.ANTHROPIC_API_KEY.get_secret_value()
        self._model_solver = cfg.ANTHROPIC_MODEL_SOLVER
        self._model_verifier = cfg.ANTHROPIC_MODEL_VERIFIER
        self._model_arbiter = cfg.ANTHROPIC_MODEL_ARBITER

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

    async def _call(
        self,
        model: str,
        system: str,
        user_message: str,
        timeout_s: float,
    ) -> str:
        """POST to Anthropic messages API, return raw text.

        §16: never log the content of responses (may contain reasoning).
        """
        if not self._api_key:
            raise NonRetryableError(
                "ANTHROPIC_API_KEY not configured",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user_message}],
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(_API_URL, headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise RetryableError(
                f"Anthropic timeout after {timeout_s}s",
                reason_code=ReasonCode.LLM_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"Anthropic network error: {exc}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            ) from exc

        if resp.status_code == 429:
            retry_after = resp.headers.get("retry-after", "?")
            raise RetryableError(
                f"Anthropic rate limited (retry-after: {retry_after})",
                reason_code=ReasonCode.LLM_RATE_LIMITED,
            )
        if resp.status_code >= 500:
            raise RetryableError(
                f"Anthropic server error {resp.status_code}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )
        if resp.status_code >= 400:
            raise NonRetryableError(
                f"Anthropic client error {resp.status_code}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )

        data = resp.json()
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]  # type: ignore[no-any-return]
        raise NonRetryableError(
            "Anthropic response contained no text content",
            reason_code=ReasonCode.LLM_SCHEMA_INVALID,
        )

    async def solve(self, request: SolveRequest) -> SolveResult:
        system, _ = get_prompt("solver", "v1")
        alts = "\n".join(f"{k}: {v}" for k, v in request.alternatives.items())
        evidence = "\n---\n".join(request.evidence_refs) if request.evidence_refs else "(none)"
        user_msg = (
            f"Question {request.question_number}:\n{request.text}\n\n"
            f"Alternatives:\n{alts}\n\nEvidence:\n{evidence}"
        )
        sem = get_semaphore(PROVIDER_NAME)
        async with sem:
            raw = await self._call(self._model_solver, system, user_msg, _SOLVER_TIMEOUT_S)
        parsed = parse_llm_output(raw, SolverOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        logger.info(
            "solver_completed",
            question=request.question_number,
            provider=PROVIDER_NAME,
            model=self._model_solver,
        )
        return SolveResult(
            question_number=parsed.question_number,
            answer=parsed.answer,
            evidence_ids=parsed.evidence_ids,
            needs_visual_recheck=parsed.needs_visual_recheck,
            ambiguity_flags=parsed.ambiguity_flags,
        )

    async def verify(self, request: VerifyRequest) -> VerifyResult:
        system, _ = get_prompt("verifier", "v1")
        # §30: payload must NOT contain the Solver's answer
        alts = "\n".join(f"{k}: {v}" for k, v in request.alternatives.items())
        evidence = "\n---\n".join(request.evidence_refs) if request.evidence_refs else "(none)"
        user_msg = (
            f"Question {request.question_number}:\n{request.text}\n\n"
            f"Alternatives:\n{alts}\n\nEvidence:\n{evidence}"
        )
        sem = get_semaphore(PROVIDER_NAME)
        async with sem:
            raw = await self._call(self._model_verifier, system, user_msg, _SOLVER_TIMEOUT_S)
        parsed = parse_llm_output(raw, VerifierOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        logger.info(
            "verifier_completed",
            question=request.question_number,
            provider=PROVIDER_NAME,
            model=self._model_verifier,
        )
        return VerifyResult(
            question_number=parsed.question_number,
            answer=parsed.answer,
            evidence_ids=parsed.evidence_ids,
            verification_status=parsed.verification_status,
            ambiguity_flags=parsed.ambiguity_flags,
        )

    async def arbitrate(self, request: ArbitrateRequest) -> ArbitrateResult:
        system, _ = get_prompt("arbiter", "v1")
        alts = "\n".join(f"{k}: {v}" for k, v in request.alternatives.items())
        evidence = "\n---\n".join(request.evidence_refs) if request.evidence_refs else "(none)"
        user_msg = (
            f"Question {request.question_number}:\n{request.text}\n\n"
            f"Alternatives:\n{alts}\n\n"
            f"Solver answer: {request.solver_answer}\n"
            f"Verifier answer: {request.verifier_answer}\n\n"
            f"Evidence:\n{evidence}"
        )
        sem = get_semaphore(PROVIDER_NAME)
        async with sem:
            raw = await self._call(self._model_arbiter, system, user_msg, _ARBITER_TIMEOUT_S)
        parsed = parse_llm_output(raw, ArbiterOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        logger.info(
            "arbiter_completed",
            question=request.question_number,
            provider=PROVIDER_NAME,
            model=self._model_arbiter,
        )
        return ArbitrateResult(
            question_number=parsed.question_number,
            answer=parsed.answer,
            decision=parsed.decision,
            evidence_ids=parsed.evidence_ids,
            ambiguity_flags=parsed.ambiguity_flags,
        )
