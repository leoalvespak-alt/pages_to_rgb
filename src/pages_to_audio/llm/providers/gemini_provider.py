"""Google Gemini 3.1 Pro multimodal reasoning adapter.

The adapter is intentionally small and provider-specific: OCR reconciliation
receives both the Document AI text and the original image, while the normal
solver/verifier/arbiter calls receive the consolidated text only.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass
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
from src.pages_to_audio.llm.prompt_registry import get_prompt
from src.pages_to_audio.llm.schemas import (
    ArbiterOutput,
    SolverOutput,
    VerifierOutput,
    parse_llm_output,
    validate_answer_in_alternatives,
)

MODEL = "gemini-3.1-pro-preview"
_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Structured result from the multimodal OCR verification pass."""

    text: str
    confidence: float
    uncertainty_flags: list[str]
    critical_confidence: float | None = None
    ambiguous: bool = False
    ambiguity_affects_answer: bool = False

    def __iter__(self) -> Iterator[str | list[str]]:
        """Keep compatibility with integrations that unpacked the old tuple."""
        yield self.text
        yield self.uncertainty_flags


class GeminiProvider:
    """Gemini REST client with deterministic model and no secret logging."""

    def __init__(
        self, settings: AppSettings | None = None, *, api_key: str | None = None, model: str = MODEL
    ) -> None:
        cfg = settings or get_settings()
        self._api_key = api_key if api_key is not None else cfg.GEMINI_API_KEY.get_secret_value()
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def _call(self, parts: list[dict[str, Any]], *, max_tokens: int = 512) -> str:
        if not self._api_key:
            raise NonRetryableError(
                "GEMINI_API_KEY not configured", reason_code=ReasonCode.LLM_PROVIDER_ERROR
            )
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
        }
        url = f"{_API_ROOT}/{self._model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(url, params={"key": self._api_key}, json=payload)
        except httpx.TimeoutException as exc:
            raise RetryableError("Gemini timeout", reason_code=ReasonCode.LLM_TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                "Gemini network error", reason_code=ReasonCode.LLM_PROVIDER_ERROR
            ) from exc
        if response.status_code == 429:
            raise RetryableError("Gemini rate limited", reason_code=ReasonCode.LLM_RATE_LIMITED)
        if response.status_code >= 500:
            raise RetryableError(
                f"Gemini server error {response.status_code}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )
        if response.status_code >= 400:
            raise NonRetryableError(
                f"Gemini client error {response.status_code}",
                reason_code=ReasonCode.LLM_PROVIDER_ERROR,
            )
        data = response.json()
        candidates = data.get("candidates", [])
        if candidates:
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if isinstance(text, str) and text:
                return text
        raise NonRetryableError(
            "Gemini response contained no text", reason_code=ReasonCode.LLM_SCHEMA_INVALID
        )

    async def reconcile_ocr(
        self,
        ocr_text: str,
        image_bytes: bytes,
        *,
        crop_bytes: bytes | None = None,
        context_local: str = "",
        ocr_spans: list[dict[str, Any]] | None = None,
        mime_type: str = "image/jpeg",
        review_mode: str = "verify",
        ocr_confidence: float | None = None,
    ) -> ReconciliationResult:
        """Compare OCR with image evidence and return a confidence-scored text.

        The prompt deliberately encodes the evidence hierarchy and the acceptance
        bands so the provider cannot silently replace a readable OCR span from
        semantic context alone.
        """
        image = {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        }
        parts: list[dict[str, Any]] = [
            {
                "text": (
                    "Você é a segunda camada de conferência visual do OCR. "
                    "Modo solicitado: "
                    f"{review_mode}. Compare o OCR com a imagem original"
                    + (" e o recorte fornecido" if crop_bytes else "")
                    + "."
                )
            },
            image,
        ]
        if crop_bytes:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(crop_bytes).decode("ascii"),
                    }
                }
            )
        local_context = context_local.strip() or "(nenhum contexto local adicional)"
        confidence_hint = "desconhecida" if ocr_confidence is None else f"{ocr_confidence:.3f}"
        spans_hint = json.dumps(ocr_spans or [], ensure_ascii=False)
        prompt = (
            "Use esta ordem de evidência: (1) evidência visual, (2) OCR do Google "
            "Document AI, (3) contexto semântico apenas para desempate. Nunca invente "
            "conteúdo que não esteja sustentado pela foto ou pelo OCR. A recomposição "
            "só é necessária para indícios reais de degradação. Para texto comum, aceite "
            "automaticamente com confiança >= 0.90, confira entre 0.75 e 0.89 e recomponha "
            "abaixo de 0.75. Para termos críticos (NÃO, EXCETO, INCORRETA, números, datas, "
            "artigos, percentuais, símbolos e letras de alternativas), use >= 0.95, confira "
            "entre 0.85 e 0.94 e recomponha abaixo de 0.85. Entre a faixa de conferência e "
            "o aceite, mantenha a melhor leitura e marque confiança moderada. Só marque "
            "manual_review quando a confiança final estiver abaixo do limite de conferência "
            "ou quando duas leituras plausíveis puderem mudar a resposta. Substitua OCR "
            "somente se a leitura visual for claramente superior.\n\n"
            "Responda JSON estrito com consolidated_text (string), confidence (número 0..1), "
            "critical_confidence (número 0..1 ou null), uncertainty_flags (array de strings), "
            "ambiguous (boolean) e ambiguity_affects_answer (boolean).\n\n"
            f"Confiança OCR: {confidence_hint}\nOCR:\n{ocr_text}\n\n"
            f"Trechos OCR e confiança (JSON):\n{spans_hint}\n\n"
            f"Contexto local (desempate apenas):\n{local_context}"
        )
        parts[0] = {"text": prompt}
        raw = await self._call(parts, max_tokens=2048)
        try:
            value = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            text = value.get("consolidated_text")
            confidence = value.get("confidence")
            critical_confidence = value.get("critical_confidence")
            flags = value.get("uncertainty_flags", [])
            ambiguous = value.get("ambiguous", False)
            affects_answer = value.get("ambiguity_affects_answer", False)
            if (
                not isinstance(text, str)
                or not isinstance(confidence, (int, float))
                or not isinstance(flags, list)
                or not isinstance(ambiguous, bool)
                or not isinstance(affects_answer, bool)
                or (
                    critical_confidence is not None
                    and not isinstance(critical_confidence, (int, float))
                )
            ):
                raise ValueError("invalid reconciliation schema")
            score = max(0.0, min(1.0, float(confidence)))
            critical_score = (
                None
                if critical_confidence is None
                else max(0.0, min(1.0, float(critical_confidence)))
            )
            return ReconciliationResult(
                text=text,
                confidence=score,
                uncertainty_flags=[str(flag) for flag in flags],
                critical_confidence=critical_score,
                ambiguous=ambiguous,
                ambiguity_affects_answer=affects_answer,
            )
        except Exception as exc:
            raise NonRetryableError(
                "Gemini OCR reconciliation schema invalid",
                reason_code=ReasonCode.LLM_SCHEMA_INVALID,
            ) from exc

    async def solve(self, request: SolveRequest) -> SolveResult:
        system, _ = get_prompt("solver", "v1")
        question = (
            f"{system}\n\nQuestion {request.question_number}:\n{request.text}\n"
            f"Alternatives: {request.alternatives}"
        )
        raw = await self._call([{"text": question}])
        parsed = parse_llm_output(raw, SolverOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        return SolveResult(
            parsed.question_number,
            parsed.answer,
            parsed.evidence_ids,
            parsed.needs_visual_recheck,
            parsed.ambiguity_flags,
        )

    async def verify(self, request: VerifyRequest) -> VerifyResult:
        system, _ = get_prompt("verifier", "v1")
        question = (
            f"{system}\n\nQuestion {request.question_number}:\n{request.text}\n"
            f"Alternatives: {request.alternatives}"
        )
        raw = await self._call([{"text": question}])
        parsed = parse_llm_output(raw, VerifierOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        return VerifyResult(
            parsed.question_number,
            parsed.answer,
            parsed.evidence_ids,
            parsed.verification_status,
            parsed.ambiguity_flags,
        )

    async def arbitrate(self, request: ArbitrateRequest) -> ArbitrateResult:
        system, _ = get_prompt("arbiter", "v1")
        question = (
            f"{system}\n\nQuestion {request.question_number}:\n{request.text}\n"
            f"Solver: {request.solver_answer}\nVerifier: {request.verifier_answer}\n"
            f"Alternatives: {request.alternatives}"
        )
        raw = await self._call([{"text": question}])
        parsed = parse_llm_output(raw, ArbiterOutput)
        validate_answer_in_alternatives(parsed.answer, request.alternatives)
        return ArbitrateResult(
            parsed.question_number,
            parsed.answer,
            parsed.decision,
            parsed.evidence_ids,
            parsed.ambiguity_flags,
        )
