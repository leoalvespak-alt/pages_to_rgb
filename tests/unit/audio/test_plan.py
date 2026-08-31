"""Tests for audio plan — §36, §9.3, §9.7.1, §9.7.2."""

from __future__ import annotations

from src.pages_to_audio.audio.plan import (
    AudioPlan,
    SilenceSegment,
    SpeechSegment,
    _item_text,
    build_audio_plan,
    validate_plan,
)


class TestItemText:
    def test_format_is_exact(self) -> None:
        assert _item_text(1, "B") == "Questão 1. Letra B."

    def test_no_explanation(self) -> None:
        text = _item_text(70, "C")
        assert text == "Questão 70. Letra C."
        assert "porque" not in text.lower()
        assert "resposta" not in text.lower()

    def test_all_questions(self) -> None:
        for n in range(1, 71):
            t = _item_text(n, "A")
            assert f"Questão {n}." in t
            assert "Letra A." in t


class TestBuildAudioPlan:
    def _answers(self, count: int = 70) -> list[tuple[int, str]]:
        letters = "ABCDE"
        return [(i + 1, letters[i % 5]) for i in range(count)]

    def test_70_answers_produces_140_speech_segments(self) -> None:
        plan = build_audio_plan(self._answers(70))
        assert plan.speech_count == 140  # 70 in each round

    def test_rodada1_has_correct_count(self) -> None:
        plan = build_audio_plan(self._answers(70))
        r1 = plan.items_by_round(1)
        assert len(r1) == 70

    def test_rodada2_has_correct_count(self) -> None:
        plan = build_audio_plan(self._answers(70))
        r2 = plan.items_by_round(2)
        assert len(r2) == 70

    def test_inter_round_silence_20s(self) -> None:
        plan = build_audio_plan(self._answers(5))
        inter = [
            s for s in plan.segments
            if isinstance(s, SilenceSegment) and s.label == "inter_round"
        ]
        assert len(inter) == 1
        assert inter[0].duration_seconds == 20.0

    def test_rodada1_gaps_are_2s(self) -> None:
        plan = build_audio_plan(self._answers(3))
        r1_gaps = [
            s for s in plan.segments
            if isinstance(s, SilenceSegment) and "gap_r1" in s.label
        ]
        assert all(g.duration_seconds == 2.0 for g in r1_gaps)
        assert len(r1_gaps) == 2  # N-1 gaps for N items

    def test_rodada2_gaps_are_1s(self) -> None:
        plan = build_audio_plan(self._answers(3))
        r2_gaps = [
            s for s in plan.segments
            if isinstance(s, SilenceSegment) and "gap_r2" in s.label
        ]
        assert all(g.duration_seconds == 1.0 for g in r2_gaps)
        assert len(r2_gaps) == 2

    def test_rodada1_speaking_rate_slower(self) -> None:
        plan = build_audio_plan(self._answers(1))
        r1 = plan.items_by_round(1)
        assert r1[0].speaking_rate < 1.0

    def test_rodada2_speaking_rate_normal(self) -> None:
        plan = build_audio_plan(self._answers(1))
        r2 = plan.items_by_round(2)
        assert r2[0].speaking_rate == 1.0

    def test_empty_answers_empty_plan(self) -> None:
        plan = build_audio_plan([])
        assert plan.speech_count == 0
        assert len(plan.segments) == 0

    def test_plan_structure_is_deterministic(self) -> None:
        answers = self._answers(5)
        plan1 = build_audio_plan(answers)
        plan2 = build_audio_plan(answers)
        texts1 = [s.text for s in plan1.segments if isinstance(s, SpeechSegment)]
        texts2 = [s.text for s in plan2.segments if isinstance(s, SpeechSegment)]
        assert texts1 == texts2

    def test_only_validated_answers_expected(self) -> None:
        # §9.3.4: caller filters to validated=True. This test proves the plan
        # only contains what was passed — no extra items added.
        answers = [(5, "C"), (10, "B")]
        plan = build_audio_plan(answers)
        r1 = plan.items_by_round(1)
        assert [s.question_number for s in r1] == [5, 10]

    def test_no_questao_sem_resposta_in_plan(self) -> None:
        # §9.1.3: "Questão N, sem resposta" must never appear
        plan = build_audio_plan(self._answers(5))
        for seg in plan.segments:
            if isinstance(seg, SpeechSegment):
                assert "sem resposta" not in seg.text.lower()


class TestValidatePlan:
    def _answers(self, count: int = 5) -> list[tuple[int, str]]:
        return [(i + 1, "A") for i in range(count)]

    def test_valid_plan_no_errors(self) -> None:
        plan = build_audio_plan(self._answers(5))
        errors = validate_plan(plan, expected_answers=5)
        assert errors == []

    def test_wrong_item_count_error(self) -> None:
        plan = build_audio_plan(self._answers(5))
        errors = validate_plan(plan, expected_answers=10)
        assert any("Rodada 1" in e for e in errors)

    def test_missing_inter_round_silence_detected(self) -> None:
        plan = AudioPlan()
        plan.segments.append(SpeechSegment(text="Q1", question_number=1, answer="A", round=1))
        plan.segments.append(SpeechSegment(text="Q1", question_number=1, answer="A", round=2))
        errors = validate_plan(plan, expected_answers=1)
        assert any("silence" in e.lower() or "Silence" in e or "inter_round" in e for e in errors)

    def test_empty_speech_text_detected(self) -> None:
        plan = AudioPlan()
        plan.segments.append(SpeechSegment(text="", question_number=1, answer="A", round=1))
        plan.segments.append(SilenceSegment(duration_seconds=20.0, label="inter_round"))
        plan.segments.append(SpeechSegment(text="", question_number=1, answer="A", round=2))
        errors = validate_plan(plan, expected_answers=1)
        assert any("Empty" in e for e in errors)
