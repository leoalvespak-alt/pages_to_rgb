"""DeepSeek provider — §27.2, §73.

Fallback provider when Anthropic fails with a technical error (§27.3).
Uses OpenAI-compatible API with httpx (no vendor SDK).
Thinking enabled; reasoning effort configurable.
Timeouts: 240s (§73). Retries: 2 (§43).

§73: adapter is isolated — changing the model must not require changes in
Solver/Verifier/Arbiter (tested in test_schemas.py).
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

_DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
_TIMEOUT_S = 240.0

PROVIDER_NAME = "deepseek"


class DeepSeekProvider:
    """Implements ReasoningProvider via DeepSeek API (OpenAI-compatible, §73)."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        self._api_key = cfg.DEEPSEEK_API_KEY.get_secret_value()
        self._model = cfg.DEEPSEEK_MODEL

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _call(self, system: str, user_message: str) -> str:
        """POST to DeepSeek chat completions. §16: never log response content."""
        if not self._api_key:
            raise NonRetryableError(
                "DEEPSEEK_API_KEY not configured",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 512,
            "temperature": 0,
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(_DEEPSEEK_API_URL, headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise RetryableError(
                f"DeepSeek timeout after {_TIMEOUT_S}s",
                reason_code=ReasonCode.LLM_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"DeepSeek network error: {exc}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            ) from exc

        if resp.status_code == 429:
            retry_after = resp.headers.get("retry-after", "?")
            raise RetryableError(
                f"DeepSeek rate limited (retry-after: {retry_after})",
                reason_code=ReasonCode.LLM_RATE_LIMITED,
            )
        if resp.status_code >= 500:
            raise RetryableError(
                f"DeepSeek server error {resp.status_code}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )
        if resp.status_code >= 400:
            raise NonRetryableError(
                f"DeepSeek client error {resp.status_code}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )

        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if content:
                return content  # type: ignore[no-any-return]
        raise NonRetryableError(
            "DeepSeek response contained no content",
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
            raw = await self._call(system, user_msg)
        parsed = parse_llm_output(raw, SolverOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        logger.info(
            "solver_completed",
            question=request.question_number,
            provider=PROVIDER_NAME,
            model=self._model,
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
        alts = "\n".join(f"{k}: {v}" for k, v in request.alternatives.items())
        evidence = "\n---\n".join(request.evidence_refs) if request.evidence_refs else "(none)"
        user_msg = (
            f"Question {request.question_number}:\n{request.text}\n\n"
            f"Alternatives:\n{alts}\n\nEvidence:\n{evidence}"
        )
        sem = get_semaphore(PROVIDER_NAME)
        async with sem:
            raw = await self._call(system, user_msg)
        parsed = parse_llm_output(raw, VerifierOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
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
            raw = await self._call(system, user_msg)
        parsed = parse_llm_output(raw, ArbiterOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        return ArbitrateResult(
            question_number=parsed.question_number,
            answer=parsed.answer,
            decision=parsed.decision,
            evidence_ids=parsed.evidence_ids,
            ambiguity_flags=parsed.ambiguity_flags,
        )
