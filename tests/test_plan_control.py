from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "plan_control.py"
SPEC = importlib.util.spec_from_file_location("plan_control_under_test", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
plan_control = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plan_control
SPEC.loader.exec_module(plan_control)


def arguments(**values: str) -> argparse.Namespace:
    return argparse.Namespace(**values)


class PlanControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.original_paths = (
            plan_control.ROOT,
            plan_control.PLAN,
            plan_control.STATE,
            plan_control.DASHBOARD,
        )
        plan_control.ROOT = root
        plan_control.PLAN = root / "plan.md"
        plan_control.STATE = root / "state.json"
        plan_control.DASHBOARD = root / "dashboard.md"
        plan_control.PLAN.write_text("# plan\n", encoding="utf-8")
        plan_control.load(create=True)

    def tearDown(self) -> None:
        (
            plan_control.ROOT,
            plan_control.PLAN,
            plan_control.STATE,
            plan_control.DASHBOARD,
        ) = self.original_paths
        self.temporary.cleanup()

    def test_initial_state_points_to_first_gate(self) -> None:
        data = plan_control.load()

        self.assertEqual(plan_control.errors(data), [])
        self.assertEqual(plan_control.active(data)[0], "G00-A")
        self.assertEqual(data["gates"]["G00-A"]["status"], "PENDENTE")
        self.assertEqual(len(data["workflow"]), 14)
        self.assertNotIn("G08", data["workflow"])

    def test_rejects_out_of_order_start(self) -> None:
        with self.assertRaisesRegex(plan_control.ControlError, "expected G00-A"):
            plan_control.cmd_start(arguments(gate="G09"))

    def test_requires_evidence_before_completion(self) -> None:
        plan_control.cmd_start(arguments(gate="G00-A"))

        with self.assertRaisesRegex(plan_control.ControlError, "Missing required evidence"):
            plan_control.cmd_complete(
                arguments(gate="G00-A", summary="Baseline realmente validado")
            )

    def test_completes_and_advances_with_required_evidence(self) -> None:
        plan_control.cmd_start(arguments(gate="G00-A"))
        plan_control.cmd_evidence(
            arguments(gate="G00-A", kind="command", value="git status registrado")
        )
        plan_control.cmd_evidence(
            arguments(gate="G00-A", kind="note", value="Diff do usuário preservado")
        )
        plan_control.cmd_complete(
            arguments(gate="G00-A", summary="Baseline e diffs foram validados")
        )
        data = plan_control.load()

        self.assertEqual(data["gates"]["G00-A"]["status"], "VALIDADO_LOCAL")
        self.assertEqual(plan_control.active(data)[0], "G09")
        self.assertTrue(plan_control.DASHBOARD.is_file())

    def test_block_and_unblock_active_gate(self) -> None:
        plan_control.cmd_block(
            arguments(
                gate="G00-A",
                reason="Remote legítimo ainda não foi fornecido",
            )
        )
        blocked = plan_control.load()["gates"]["G00-A"]
        self.assertEqual(blocked["status"], "BLOQUEADO")
        self.assertIsNone(blocked["blockers"][0]["resolved_at"])

        plan_control.cmd_unblock(arguments(gate="G00-A"))
        resumed = plan_control.load()["gates"]["G00-A"]
        self.assertEqual(resumed["status"], "EM_EXECUCAO")
        self.assertIsNotNone(resumed["blockers"][0]["resolved_at"])

    def test_final_check_rejects_incomplete_plan(self) -> None:
        with self.assertRaisesRegex(plan_control.ControlError, "Final check failed"):
            plan_control.cmd_final(arguments())

    def test_sync_plan_absorbs_only_empty_legacy_gates(self) -> None:
        data = plan_control.load()
        data["workflow"].insert(data["workflow"].index("G13"), "G08")
        data["gates"]["G08"] = {
            "title": "Painel administrativo",
            "status": "PENDENTE",
            "target_status": "VALIDADO_LOCAL",
            "depends_on": ["G07"],
            "required_evidence": ["test"],
            "started_at": None,
            "completed_at": None,
            "summary": None,
            "evidence": [],
            "blockers": [],
        }
        plan_control.save(data)

        plan_control.cmd_sync_plan(arguments())
        migrated = plan_control.load()

        self.assertNotIn("G08", migrated["workflow"])
        self.assertEqual(plan_control.errors(migrated), [])

    def test_sync_plan_rejects_non_empty_legacy_gate(self) -> None:
        data = plan_control.load()
        data["workflow"].append("G08")
        data["gates"]["G08"] = {
            "title": "Painel administrativo",
            "status": "EM_EXECUCAO",
            "target_status": "VALIDADO_LOCAL",
            "depends_on": ["G07"],
            "required_evidence": ["test"],
            "started_at": "2026-09-09T00:00:00+00:00",
            "completed_at": None,
            "summary": None,
            "evidence": [],
            "blockers": [],
        }
        plan_control.save(data)

        with self.assertRaisesRegex(plan_control.ControlError, "Cannot absorb non-empty gate"):
            plan_control.cmd_sync_plan(arguments())


if __name__ == "__main__":
    unittest.main()
