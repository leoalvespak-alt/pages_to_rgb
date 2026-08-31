"""ProcessExamWorkflow — 20 steps, §17.1."""

from __future__ import annotations

from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.pages_to_audio.workflows.activities.fakes import (
        fake_arbitrate_disagreements,
        fake_assemble_final_audio,
        fake_complete_session,
        fake_emit_post_correction_status,
        fake_emit_pre_correction_status,
        fake_evaluate_gate1,
        fake_evaluate_gate2,
        fake_generate_answer_audio,
        fake_materialize_logical_pages,
        fake_preprocess_pages,
        fake_publish_final_audio,
        fake_reconstruct_exam,
        fake_rescue_failed_answers,
        fake_rescue_incomplete_questions,
        fake_retrieve_knowledge,
        fake_run_ocr,
        fake_solve_questions,
        fake_validate_final_audio,
        fake_validate_locked_session,
        fake_verify_questions,
    )
    from src.pages_to_audio.workflows.policies import (
        FFMPEG_ACTIVITY_OPTS,
        IMAGE_ACTIVITY_OPTS,
        LLM_ARBITER_ACTIVITY_OPTS,
        LLM_SOLVER_ACTIVITY_OPTS,
        OCR_ACTIVITY_OPTS,
        QUICK_ACTIVITY_OPTS,
        STORAGE_ACTIVITY_OPTS,
    )


@workflow.defn(name="ProcessExamWorkflow")
class ProcessExamWorkflow:
    """
    20-step durable workflow for processing a locked exam session.

    Steps (§17.1):
     1  ValidateLockedSession
     2  MaterializeLogicalPages
     3  PreprocessPages
     4  RunOCR
     5  ReconstructExam
     6  RescueIncompleteQuestions
     7  EvaluateGate1
     8  EmitPreCorrectionStatus
     9  RetrieveKnowledge          ← only if Gate 1 passed
    10  SolveQuestions             ← only if Gate 1 passed (Invariant 5)
    11  VerifyQuestions            ← only if Gate 1 passed
    12  ArbitrateDisagreements     ← only if Gate 1 passed
    13  RescueFailedAnswers        ← only if Gate 1 passed
    14  EvaluateGate2              ← only if Gate 1 passed
    15  EmitPostCorrectionStatus
    16  GenerateAnswerAudio        ← only if Gate 2 passed (Invariant 6)
    17  AssembleFinalAudio         ← only if Gate 2 passed
    18  ValidateFinalAudio         ← only if Gate 2 passed
    19  PublishFinalAudio          ← only if Gate 2 passed
    20  CompleteSession
    """

    @workflow.run
    async def run(self, session_public_id: str) -> dict[str, Any]:
        sid = session_public_id

        # The RGB result channel has its own delivery state; it does not alter
        # the existing SessionState machine or wait for a device ACK.
        await workflow.execute_activity(
            "mark_rgb_result_processing",
            sid,
            **QUICK_ACTIVITY_OPTS,
        )

        # Step 1 — ValidateLockedSession
        await workflow.execute_activity(fake_validate_locked_session, sid, **QUICK_ACTIVITY_OPTS)

        # Step 2 — MaterializeLogicalPages
        await workflow.execute_activity(fake_materialize_logical_pages, sid, **IMAGE_ACTIVITY_OPTS)

        # Step 3 — PreprocessPages
        await workflow.execute_activity(fake_preprocess_pages, sid, **IMAGE_ACTIVITY_OPTS)

        # Step 4 — RunOCR
        await workflow.execute_activity(fake_run_ocr, sid, **OCR_ACTIVITY_OPTS)

        # Step 5 — ReconstructExam
        await workflow.execute_activity(fake_reconstruct_exam, sid, **LLM_SOLVER_ACTIVITY_OPTS)

        # Step 6 — RescueIncompleteQuestions
        await workflow.execute_activity(
            fake_rescue_incomplete_questions, sid, **LLM_SOLVER_ACTIVITY_OPTS
        )

        # Step 7 — EvaluateGate1
        gate1_result: dict[str, Any] = await workflow.execute_activity(
            fake_evaluate_gate1, sid, **QUICK_ACTIVITY_OPTS
        )
        gate1_passed: bool = gate1_result.get("passed", False)

        # Step 8 — EmitPreCorrectionStatus
        await workflow.execute_activity(
            fake_emit_pre_correction_status,
            args=[sid, gate1_result],
            **QUICK_ACTIVITY_OPTS,
        )

        gate2_passed = False
        gate2_result: dict[str, Any] = {}

        if gate1_passed:
            # Step 9 — RetrieveKnowledge (§9, Gate 1 guard — Invariant 5)
            await workflow.execute_activity(
                fake_retrieve_knowledge, sid, **LLM_SOLVER_ACTIVITY_OPTS
            )

            # Step 10 — SolveQuestions (Invariant 5: unreachable without Gate 1)
            await workflow.execute_activity(fake_solve_questions, sid, **LLM_SOLVER_ACTIVITY_OPTS)

            # Step 11 — VerifyQuestions
            await workflow.execute_activity(fake_verify_questions, sid, **LLM_SOLVER_ACTIVITY_OPTS)

            # Step 12 — ArbitrateDisagreements
            await workflow.execute_activity(
                fake_arbitrate_disagreements, sid, **LLM_ARBITER_ACTIVITY_OPTS
            )

            # Step 13 — RescueFailedAnswers
            await workflow.execute_activity(
                fake_rescue_failed_answers, sid, **LLM_SOLVER_ACTIVITY_OPTS
            )

            # Step 14 — EvaluateGate2
            gate2_result = await workflow.execute_activity(
                fake_evaluate_gate2, sid, **QUICK_ACTIVITY_OPTS
            )
            gate2_passed = gate2_result.get("passed", False)

        # Step 15 — EmitPostCorrectionStatus (always — includes failure status)
        await workflow.execute_activity(
            fake_emit_post_correction_status,
            args=[sid, gate2_result],
            **QUICK_ACTIVITY_OPTS,
        )

        # Publish after Gate 2 is definitive. The activity explicitly emits
        # RESULT_CANCELLED when the validated answer set cannot be represented
        # safely as a contiguous A-E sequence.
        await workflow.execute_activity(
            "publish_rgb_result",
            sid,
            **QUICK_ACTIVITY_OPTS,
        )

        if gate2_passed:
            # Steps 16-19 -- TTS pipeline (Invariant 6: unreachable without Gate 2)
            await workflow.execute_activity(
                fake_generate_answer_audio, sid, **LLM_SOLVER_ACTIVITY_OPTS
            )
            await workflow.execute_activity(fake_assemble_final_audio, sid, **FFMPEG_ACTIVITY_OPTS)
            await workflow.execute_activity(fake_validate_final_audio, sid, **QUICK_ACTIVITY_OPTS)
            await workflow.execute_activity(fake_publish_final_audio, sid, **STORAGE_ACTIVITY_OPTS)

        # Step 20 — CompleteSession
        final = await workflow.execute_activity(fake_complete_session, sid, **QUICK_ACTIVITY_OPTS)

        return {
            "session_id": sid,
            "gate1_passed": gate1_passed,
            "gate2_passed": gate2_passed,
            "completed": final.get("completed", False),
        }
