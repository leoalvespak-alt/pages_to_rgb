"""Deterministic validators for reconstructed questions — §21.4, §6.5.

Rules:
- Never fill a gap (§60): missing alternative → INCOMPLETE, never invented.
- All 7 checks of §21.4 implemented.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pages_to_audio.domain.models.reconstruction import (
    Completeness,
    ExamReconstructionResult,
    QuestionFlag,
    ReconstructedQuestion,
)
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationIssue:
    question_number: int | None
    flag: QuestionFlag
    detail: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue]
    ready_count: int
    incomplete_count: int
    failed_count: int

    @property
    def total(self) -> int:
        return self.ready_count + self.incomplete_count + self.failed_count


def validate_reconstruction(result: ExamReconstructionResult) -> ValidationReport:
    """
    Apply all 7 deterministic validations of §21.4.
    Mutates question.flags and question.completeness in place.
    """
    issues: list[ValidationIssue] = []
    questions = result.questions

    # Build number-to-question map
    seen_numbers: dict[int, int] = {}  # number → first index
    for i, q in enumerate(questions):
        if q.question_number in seen_numbers:
            # §21.4 check 4: duplicate question numbers
            issues.append(
                ValidationIssue(
                    q.question_number,
                    QuestionFlag.DUPLICATE_NUMBER,
                    f"Question {q.question_number} appears at indices "
                    f"{seen_numbers[q.question_number]} and {i}",
                )
            )
            if QuestionFlag.DUPLICATE_NUMBER not in q.flags:
                q.flags.append(QuestionFlag.DUPLICATE_NUMBER)
            q.completeness = Completeness.PARTIAL
        else:
            seen_numbers[q.question_number] = i

    sorted_numbers = sorted(seen_numbers.keys())

    # §21.4 check 5: sequence gaps
    for idx, num in enumerate(sorted_numbers):
        if idx > 0:
            prev = sorted_numbers[idx - 1]
            if num - prev > 1:
                issues.append(
                    ValidationIssue(
                        num, QuestionFlag.SEQUENCE_GAP, f"Gap between question {prev} and {num}"
                    )
                )
                q = questions[seen_numbers[num]]
                if QuestionFlag.SEQUENCE_GAP not in q.flags:
                    q.flags.append(QuestionFlag.SEQUENCE_GAP)
                if q.completeness == Completeness.COMPLETE:
                    q.completeness = Completeness.PARTIAL

    for q in questions:
        _validate_single(q, issues)

    ready = sum(
        1 for q in questions if q.completeness == Completeness.COMPLETE and not _is_blocking(q)
    )
    incomplete = sum(
        1 for q in questions if q.completeness == Completeness.PARTIAL or _is_blocking(q)
    )
    failed = sum(1 for q in questions if q.completeness == Completeness.MISSING)

    logger.info(
        "reconstruction_validated",
        total=len(questions),
        ready=ready,
        incomplete=incomplete,
        failed=failed,
        issues=len(issues),
    )
    return ValidationReport(
        issues=issues, ready_count=ready, incomplete_count=incomplete, failed_count=failed
    )


def _is_blocking(q: ReconstructedQuestion) -> bool:
    blocking = {QuestionFlag.DUPLICATE_NUMBER, QuestionFlag.NUMBER_MISSING}
    return bool(set(q.flags) & blocking)


def _validate_single(q: ReconstructedQuestion, issues: list[ValidationIssue]) -> None:
    # §21.4 check 1: question number present (already guaranteed by Pydantic ge=1)
    # §21.4 check 2: alternatives not empty — at least 2 non-empty
    non_empty = q.alternatives.non_empty()
    if len(non_empty) < 2:
        issues.append(
            ValidationIssue(
                q.question_number,
                QuestionFlag.ALTERNATIVES_INCOMPLETE,
                f"Question {q.question_number} has only {len(non_empty)} alternatives",
            )
        )
        if QuestionFlag.ALTERNATIVES_INCOMPLETE not in q.flags:
            q.flags.append(QuestionFlag.ALTERNATIVES_INCOMPLETE)
        # Do NOT invent the missing alternative (§60)
        if q.completeness == Completeness.COMPLETE:
            q.completeness = Completeness.PARTIAL

    # §21.4 check 3: question text not empty
    if not q.text.strip():
        issues.append(
            ValidationIssue(
                q.question_number,
                QuestionFlag.NUMBER_MISSING,
                f"Question {q.question_number} has empty text",
            )
        )
        if QuestionFlag.NUMBER_MISSING not in q.flags:
            q.flags.append(QuestionFlag.NUMBER_MISSING)
        q.completeness = Completeness.MISSING

    # §21.4 check 6: visual ambiguity flag (propagated from LLM output)
    if QuestionFlag.VISUAL_AMBIGUITY in q.flags:
        if q.completeness == Completeness.COMPLETE:
            q.completeness = Completeness.PARTIAL

    # §21.4 check 7: OCR conflict flag
    if QuestionFlag.OCR_CONFLICT in q.flags:
        if q.completeness == Completeness.COMPLETE:
            q.completeness = Completeness.PARTIAL
