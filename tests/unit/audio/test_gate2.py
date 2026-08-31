"""Gate 2 tests for audio path — §9.1, §9.7.2-9.7.3."""

from __future__ import annotations

from src.pages_to_audio.audio.plan import build_audio_plan
from src.pages_to_audio.domain.gates import evaluate_gate_2


class TestGate2AudioRules:
    def test_gate2_blocked_produces_no_audio_plan(self) -> None:
        """§9.7.3: when Gate 2 is blocked, no gabarito audio should be generated."""
        gate = evaluate_gate_2(validated=62, expected_questions=70, minimum_ratio=0.90)
        assert gate.blocked

        # In the real workflow, blocked Gate 2 means build_audio_plan is NOT called.
        # This test verifies the gate result is correctly blocking.
        assert not gate.passed

    def test_gate2_degraded_includes_only_validated(self) -> None:
        """§9.7.2: degraded Gate 2 plan contains only the validated answers."""
        validated_answers = [(i + 1, "A") for i in range(63)]  # 63/70 = degraded pass

        gate = evaluate_gate_2(validated=63, expected_questions=70, minimum_ratio=0.90)
        assert gate.passed
        assert gate.degraded

        plan = build_audio_plan(validated_answers)
        r1 = plan.items_by_round(1)
        assert len(r1) == 63  # only the 63 validated questions

        # No mention of "sem resposta"
        for seg_text in [s.text for s in r1]:
            assert "sem resposta" not in seg_text.lower()

    def test_gate2_full_pass_has_all_70(self) -> None:
        gate = evaluate_gate_2(validated=70, expected_questions=70, minimum_ratio=0.90)
        assert gate.passed
        assert gate.success
        plan = build_audio_plan([(i + 1, "B") for i in range(70)])
        assert plan.speech_count == 140  # 70 x 2 rounds

    def test_gate2_boundary_63_passes(self) -> None:
        r = evaluate_gate_2(63, 70, 0.90)
        assert r.passed

    def test_gate2_boundary_62_blocks(self) -> None:
        r = evaluate_gate_2(62, 70, 0.90)
        assert r.blocked
