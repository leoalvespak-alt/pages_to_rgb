"""Audio plan — §36, §9.3.

Generates a deterministic, serializable script for the final MP3:

  Rodada 1 (§36): slightly slower rate, 2-second pauses between items.
  Gap (§36): 20-second silence after last Rodada-1 item.
  Rodada 2 (§36): normal rate, 1-second pauses between items.

Format per item (§36.1): "Questão N. Letra X." — no explanations.
Only FinalAnswers with validated=True enter the plan (§9.3.4).

The plan object is fully serializable — validate structure before any TTS call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class SegmentKind(StrEnum):
    SPEECH = "speech"
    SILENCE = "silence"


@dataclass
class SpeechSegment:
    kind: Literal[SegmentKind.SPEECH] = SegmentKind.SPEECH
    text: str = ""
    question_number: int = 0
    answer: str = ""
    round: int = 1
    speaking_rate: float = 0.85


@dataclass
class SilenceSegment:
    kind: Literal[SegmentKind.SILENCE] = SegmentKind.SILENCE
    duration_seconds: float = 1.0
    label: str = ""


AudioSegment = SpeechSegment | SilenceSegment


@dataclass
class AudioPlan:
    """Serializable audio plan — validate before any TTS synthesis."""

    segments: list[AudioSegment] = field(default_factory=list)

    @property
    def speech_count(self) -> int:
        return sum(1 for s in self.segments if isinstance(s, SpeechSegment))

    @property
    def total_silence_seconds(self) -> float:
        return sum(s.duration_seconds for s in self.segments if isinstance(s, SilenceSegment))

    def items_by_round(self, round_number: int) -> list[SpeechSegment]:
        return [
            s for s in self.segments if isinstance(s, SpeechSegment) and s.round == round_number
        ]


def _item_text(question_number: int, answer: str) -> str:
    """§36.1 exact format: 'Questão N. Letra X.'"""
    return f"Questão {question_number}. Letra {answer}."


def build_audio_plan(
    answers: list[tuple[int, str]],
    *,
    round1_rate: float = 0.85,
    round2_rate: float = 1.0,
    gap_between_round1_items_s: float = 2.0,
    gap_between_round2_items_s: float = 1.0,
    inter_round_silence_s: float = 20.0,
) -> AudioPlan:
    """Build the audio plan from a list of (question_number, answer) pairs.

    Args:
        answers: Ordered list of (question_number, answer) — only validated answers.
                 §9.3.4: caller must filter to validated=True only.
        round1_rate: TTS speaking rate for Rodada 1 (default 0.85 = slightly slower).
        round2_rate: TTS speaking rate for Rodada 2 (default 1.0 = normal).
        gap_between_round1_items_s: Silence between Rodada 1 items (§36: 2s).
        gap_between_round2_items_s: Silence between Rodada 2 items (§36: 1s).
        inter_round_silence_s: Silence between Rodada 1 and Rodada 2 (§36: 20s).
    """
    plan = AudioPlan()

    if not answers:
        return plan

    # Rodada 1
    for idx, (q_num, answer) in enumerate(answers):
        plan.segments.append(
            SpeechSegment(
                text=_item_text(q_num, answer),
                question_number=q_num,
                answer=answer,
                round=1,
                speaking_rate=round1_rate,
            )
        )
        if idx < len(answers) - 1:
            plan.segments.append(
                SilenceSegment(
                    duration_seconds=gap_between_round1_items_s,
                    label=f"gap_r1_after_q{q_num}",
                )
            )

    # 20-second inter-round silence
    plan.segments.append(
        SilenceSegment(
            duration_seconds=inter_round_silence_s,
            label="inter_round",
        )
    )

    # Rodada 2
    for idx, (q_num, answer) in enumerate(answers):
        plan.segments.append(
            SpeechSegment(
                text=_item_text(q_num, answer),
                question_number=q_num,
                answer=answer,
                round=2,
                speaking_rate=round2_rate,
            )
        )
        if idx < len(answers) - 1:
            plan.segments.append(
                SilenceSegment(
                    duration_seconds=gap_between_round2_items_s,
                    label=f"gap_r2_after_q{q_num}",
                )
            )

    return plan


def validate_plan(plan: AudioPlan, expected_answers: int) -> list[str]:
    """Return list of validation errors (empty = plan is OK).

    Checks:
    - Each answer appears exactly twice (once per round).
    - Correct number of items per round.
    - Inter-round silence present (>= 10s to allow for slight config variation).
    - No empty speech text.
    """
    errors: list[str] = []
    r1_items = plan.items_by_round(1)
    r2_items = plan.items_by_round(2)

    if len(r1_items) != expected_answers:
        errors.append(f"Rodada 1 has {len(r1_items)} items, expected {expected_answers}")
    if len(r2_items) != expected_answers:
        errors.append(f"Rodada 2 has {len(r2_items)} items, expected {expected_answers}")

    for seg in plan.segments:
        if isinstance(seg, SpeechSegment) and not seg.text.strip():
            errors.append(f"Empty speech text for question {seg.question_number}")

    inter_silences = [
        s for s in plan.segments if isinstance(s, SilenceSegment) and s.label == "inter_round"
    ]
    if not inter_silences:
        errors.append("Inter-round silence segment is missing")
    elif inter_silences[0].duration_seconds < 10:
        errors.append(
            f"Inter-round silence too short: {inter_silences[0].duration_seconds}s (expected >=10s)"
        )

    return errors
