from __future__ import annotations

from src.pages_to_audio.rgb.policy import AnswerCandidate, validate_complete_answer_set


def _answers(count: int = 3) -> list[AnswerCandidate]:
    return [AnswerCandidate(i, "ABCDE"[(i - 1) % 5], True, "READY") for i in range(1, count + 1)]


def test_complete_answer_set_is_ordered_by_question_number() -> None:
    result, reason = validate_complete_answer_set(3, list(reversed(_answers())))
    assert result == "ABC"
    assert reason is None


def test_missing_question_is_cancelled() -> None:
    result, reason = validate_complete_answer_set(3, _answers(2))
    assert result is None
    assert reason == "RGB_QUESTION_SEQUENCE_GAP"


def test_unvalidated_answer_is_cancelled() -> None:
    candidates = _answers()
    candidates[1] = AnswerCandidate(2, "B", False, "READY")
    result, reason = validate_complete_answer_set(3, candidates)
    assert result is None
    assert reason == "RGB_ANSWER_NOT_VALIDATED"


def test_failed_question_is_never_encoded() -> None:
    candidates = _answers()
    candidates[0] = AnswerCandidate(1, "A", True, "FAILED")
    result, reason = validate_complete_answer_set(3, candidates)
    assert result is None
    assert reason == "RGB_QUESTION_FAILED"


def test_invalid_letter_is_never_encoded() -> None:
    candidates = _answers()
    candidates[0] = AnswerCandidate(1, "Z", True, "READY")
    result, reason = validate_complete_answer_set(3, candidates)
    assert result is None
    assert reason == "RGB_ANSWER_INVALID_ALTERNATIVE"


def test_configured_maximum_is_enforced() -> None:
    result, reason = validate_complete_answer_set(3, _answers(), max_items=2)
    assert result is None
    assert reason == "RGB_EXPECTED_QUESTION_COUNT_OUT_OF_RANGE"
