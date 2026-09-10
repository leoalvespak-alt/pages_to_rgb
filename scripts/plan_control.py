#!/usr/bin/env python3
"""Persistent gate controller for the Pages to Audio production plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "PLANO_MESTRE_PRODUCAO_CAMERA_RGB_2026-09-09.md"
STATE = ROOT / "docs" / "progress" / "EXECUCAO_PLANO_MESTRE.json"
DASHBOARD = ROOT / "docs" / "progress" / "EXECUCAO_PLANO_MESTRE.md"

STATUSES = {
    "PENDENTE",
    "EM_EXECUCAO",
    "IMPLEMENTADO",
    "VALIDADO_LOCAL",
    "VALIDADO_FISICO",
    "PUBLICADO",
    "VALIDADO_PRODUCAO",
    "BLOQUEADO",
}
KINDS = {
    "command",
    "test",
    "commit",
    "artifact",
    "deployment",
    "physical",
    "documentation",
    "note",
}

# Completed gates are preserved. Remaining work is consolidated so expensive
# validation happens once at the appropriate confidence level.
DEFINITIONS = [
    ("G00-A", "Baseline, caminhos, Git e diffs preservados", "VALIDADO_LOCAL", ["command", "note"]),
    ("G09", "Repositório e branch legítimos do firmware", "VALIDADO_LOCAL", ["command", "note"]),
    ("G01", "Migração aditiva e persistência", "VALIDADO_LOCAL", ["command", "test"]),
    ("G02", "Matriz OV2640 confirmada", "VALIDADO_LOCAL", ["documentation", "note"]),
    ("G03", "Backend de capacidades e perfis", "VALIDADO_LOCAL", ["test"]),
    ("G04", "Upload, original e telemetria", "VALIDADO_LOCAL", ["test"]),
    ("G05", "Backend RGB físico", "VALIDADO_LOCAL", ["test"]),
    ("G06", "Android bridge e spool duráveis", "VALIDADO_LOCAL", ["test"]),
    ("G07", "Onda integrada de implementação", "VALIDADO_LOCAL", ["test"]),
    ("G13", "Validação local integrada e candidata", "VALIDADO_LOCAL", ["test", "artifact"]),
    ("G17", "Release, commits, PRs e CI", "VALIDADO_LOCAL", ["artifact", "commit", "test"]),
    (
        "G19",
        "Deploy e instalações piloto",
        "VALIDADO_PRODUCAO",
        ["deployment", "artifact", "physical", "test"],
    ),
    (
        "G22",
        "Campanha física e produção integrada",
        "VALIDADO_PRODUCAO",
        ["deployment", "physical", "test", "note"],
    ),
    ("G24", "Documentação e fechamento final", "VALIDADO_PRODUCAO", ["documentation", "commit"]),
]

ABSORBED_GATES = {
    "G08",
    "G10",
    "G11",
    "G12",
    "G14",
    "G15",
    "G16",
    "G18",
    "G20",
    "G21",
    "G23",
}


class ControlError(RuntimeError):
    pass


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_state() -> dict[str, Any]:
    gates: dict[str, Any] = {}
    previous = None
    for gate_id, title, target, required in DEFINITIONS:
        gates[gate_id] = {
            "title": title,
            "status": "PENDENTE",
            "target_status": target,
            "depends_on": [previous] if previous else [],
            "required_evidence": required,
            "started_at": None,
            "completed_at": None,
            "summary": None,
            "evidence": [],
            "blockers": [],
        }
        previous = gate_id
    now = timestamp()
    return {
        "schema_version": 1,
        "plan": str(PLAN.relative_to(ROOT)).replace("\\", "/"),
        "created_at": now,
        "updated_at": now,
        "workflow": [item[0] for item in DEFINITIONS],
        "gates": gates,
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(create: bool = False) -> dict[str, Any]:
    if not STATE.exists():
        if not create:
            raise ControlError(f"State missing: {STATE}. Run init.")
        data = new_state()
        save(data)
        return data
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlError(f"Cannot read state: {exc}") from exc


def save(data: dict[str, Any]) -> None:
    data["updated_at"] = timestamp()
    atomic_write(STATE, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    render(data)


def complete(gate: dict[str, Any]) -> bool:
    return gate["status"] == gate["target_status"]


def active(data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for gate_id in data["workflow"]:
        gate = data["gates"][gate_id]
        if not complete(gate):
            return gate_id, gate
    return None


def errors(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    expected = [item[0] for item in DEFINITIONS]
    by_id = {item[0]: item for item in DEFINITIONS}
    if not PLAN.is_file():
        found.append(f"canonical plan missing: {PLAN}")
    if data.get("schema_version") != 1:
        found.append("unsupported schema_version")
    if data.get("workflow") != expected:
        found.append("workflow differs from controller")
    gates = data.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(expected):
        return [*found, "gate set differs from controller"]
    for gate_id in expected:
        gate = gates[gate_id]
        definition = by_id[gate_id]
        if gate.get("status") not in STATUSES:
            found.append(f"{gate_id}: invalid status")
        if gate.get("target_status") != definition[2]:
            found.append(f"{gate_id}: invalid target")
        if gate.get("required_evidence") != definition[3]:
            found.append(f"{gate_id}: invalid evidence requirements")
        if not isinstance(gate.get("evidence"), list):
            found.append(f"{gate_id}: evidence is not a list")
        elif any(entry.get("kind") not in KINDS for entry in gate["evidence"]):
            found.append(f"{gate_id}: invalid evidence kind")
        if not isinstance(gate.get("blockers"), list):
            found.append(f"{gate_id}: blockers is not a list")
        expected_dependency = (
            [] if gate_id == expected[0] else [expected[expected.index(gate_id) - 1]]
        )
        if gate.get("depends_on") != expected_dependency:
            found.append(f"{gate_id}: invalid dependency")
    return found


def require_gate(data: dict[str, Any], gate_id: str) -> dict[str, Any]:
    if gate_id not in data["gates"]:
        raise ControlError(f"Unknown gate: {gate_id}")
    return data["gates"][gate_id]


def dependency_errors(data: dict[str, Any], gate_id: str) -> list[str]:
    result = []
    for dependency in data["gates"][gate_id]["depends_on"]:
        dependency_gate = data["gates"][dependency]
        if not complete(dependency_gate):
            result.append(
                f"{dependency} is {dependency_gate['status']}, "
                f"expected {dependency_gate['target_status']}"
            )
    return result


def recorded_kinds(gate: dict[str, Any]) -> set[str]:
    return {entry["kind"] for entry in gate["evidence"]}


def render(data: dict[str, Any]) -> None:
    done = sum(complete(data["gates"][gate_id]) for gate_id in data["workflow"])
    current = active(data)
    current_id = current[0] if current else "nenhum; todos concluídos"
    lines = [
        "# Execução do plano mestre",
        "",
        "> Gerado por scripts/plan_control.py. Não editar manualmente.",
        "",
        f"- Atualizado em: {data['updated_at']}",
        f"- Progresso: **{done}/{len(data['workflow'])} gates**",
        f"- Próximo gate: **{current_id}**",
        "",
        "## Gates",
        "",
        "| Ordem | Gate | Estado | Alvo | Descrição | Evidências |",
        "|---:|---|---|---|---|---:|",
    ]
    for index, gate_id in enumerate(data["workflow"], 1):
        gate = data["gates"][gate_id]
        title = gate["title"].replace("|", "\\|")
        lines.append(
            f"| {index} | {gate_id} | {gate['status']} | "
            f"{gate['target_status']} | {title} | {len(gate['evidence'])} |"
        )
    lines += ["", "## Bloqueios ativos", ""]
    blockers = [
        (gate_id, item)
        for gate_id in data["workflow"]
        for item in data["gates"][gate_id]["blockers"]
        if item.get("resolved_at") is None
    ]
    lines += (
        [f"- **{gate_id}**: {item['reason']}" for gate_id, item in blockers]
        if blockers
        else ["- Nenhum."]
    )
    lines += ["", "## Resumos concluídos", ""]
    summaries = [
        f"- **{gate_id}**: {data['gates'][gate_id]['summary']}"
        for gate_id in data["workflow"]
        if data["gates"][gate_id].get("summary")
    ]
    lines += summaries if summaries else ["- Nenhum gate concluído."]
    lines += [
        "",
        "## Retomada",
        "",
        "    rtk python scripts/plan_control.py verify",
        "    rtk python scripts/plan_control.py status",
        "    rtk python scripts/plan_control.py next",
        "",
    ]
    atomic_write(DASHBOARD, "\n".join(lines))


def cmd_init(_: argparse.Namespace) -> None:
    if STATE.exists():
        raise ControlError(f"State already exists: {STATE}")
    data = load(create=True)
    print(f"Initialized {len(data['workflow'])} gates at {STATE}")


def cmd_verify(_: argparse.Namespace) -> None:
    data = load()
    found = errors(data)
    if found:
        raise ControlError("; ".join(found))
    render(data)
    print(f"OK: {len(data['workflow'])} gates; dashboard synchronized.")


def cmd_sync_plan(_: argparse.Namespace) -> None:
    """Safely absorb untouched legacy gates into the streamlined workflow."""
    data = load()
    expected = [item[0] for item in DEFINITIONS]
    if data.get("workflow") == expected and set(data.get("gates", {})) == set(expected):
        found = errors(data)
        if found:
            raise ControlError("; ".join(found))
        render(data)
        print("Plan state already uses the streamlined workflow.")
        return

    gates = data.get("gates", {})
    removed = set(gates) - set(expected)
    unknown = removed - ABSORBED_GATES
    if unknown:
        raise ControlError("Cannot absorb unknown gates: " + ", ".join(sorted(unknown)))
    for gate_id in sorted(removed):
        gate = gates[gate_id]
        if (
            gate.get("status") != "PENDENTE"
            or gate.get("started_at") is not None
            or gate.get("completed_at") is not None
            or gate.get("evidence")
            or gate.get("blockers")
        ):
            raise ControlError(f"Cannot absorb non-empty gate: {gate_id}")

    by_id = {item[0]: item for item in DEFINITIONS}
    for index, gate_id in enumerate(expected):
        if gate_id not in gates:
            raise ControlError(f"Required preserved gate missing: {gate_id}")
        gate = gates[gate_id]
        definition = by_id[gate_id]
        gate["title"] = definition[1]
        gate["target_status"] = definition[2]
        gate["required_evidence"] = definition[3]
        gate["depends_on"] = [] if index == 0 else [expected[index - 1]]

    active_gate = next((gate_id for gate_id in expected if not complete(gates[gate_id])), None)
    if active_gate:
        gates[active_gate]["evidence"].append(
            {
                "recorded_at": timestamp(),
                "kind": "note",
                "value": (
                    "Plano remanescente consolidado com autorização do usuário: "
                    "gates futuros vazios foram absorvidos; evidências e estados "
                    "dos gates concluídos/ativo foram preservados."
                ),
            }
        )
    data["workflow"] = expected
    data["gates"] = {gate_id: gates[gate_id] for gate_id in expected}
    save(data)
    print(f"Plan state synchronized: {len(expected)} gates; absorbed {len(removed)}.")


def cmd_status(args: argparse.Namespace) -> None:
    data = load()
    if errors(data):
        raise ControlError("Invalid state; run verify")
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print("GATE   STATUS              TARGET               EVIDENCE  TITLE")
    for gate_id in data["workflow"]:
        gate = data["gates"][gate_id]
        print(
            f"{gate_id:<6} {gate['status']:<19} {gate['target_status']:<20} "
            f"{len(gate['evidence']):<9} {gate['title']}"
        )


def cmd_next(_: argparse.Namespace) -> None:
    data = load()
    current = active(data)
    if current is None:
        print("All gates reached target status. Run final-check.")
        return
    gate_id, gate = current
    print(f"{gate_id}: {gate['title']}")
    print(f"status={gate['status']} target={gate['target_status']}")
    print("required_evidence=" + ",".join(gate["required_evidence"]))
    for item in gate["blockers"]:
        if item.get("resolved_at") is None:
            print(f"BLOCKED: {item['reason']}")


def ensure_active(data: dict[str, Any], gate_id: str) -> dict[str, Any]:
    current = active(data)
    expected = current[0] if current else "none"
    if current is None or expected != gate_id:
        raise ControlError(f"Out of order: expected {expected}, got {gate_id}")
    problems = dependency_errors(data, gate_id)
    if problems:
        raise ControlError("; ".join(problems))
    return current[1]


def cmd_start(args: argparse.Namespace) -> None:
    data = load()
    gate = ensure_active(data, args.gate)
    if gate["status"] == "BLOQUEADO":
        raise ControlError("Gate is blocked; use unblock after resolution")
    if gate["status"] == "PENDENTE":
        gate["status"] = "EM_EXECUCAO"
        gate["started_at"] = timestamp()
        save(data)
    print(f"{args.gate} is {gate['status']}.")


def cmd_evidence(args: argparse.Namespace) -> None:
    data = load()
    gate = ensure_active(data, args.gate)
    if gate["status"] in {"PENDENTE", "BLOQUEADO"}:
        raise ControlError("Start or unblock the gate before adding evidence")
    value = args.value.strip()
    if len(value) < 8:
        raise ControlError("Evidence is too vague")
    gate["evidence"].append({"recorded_at": timestamp(), "kind": args.kind, "value": value})
    save(data)
    print(f"Evidence added to {args.gate}: {args.kind}.")


def cmd_complete(args: argparse.Namespace) -> None:
    data = load()
    gate = ensure_active(data, args.gate)
    if gate["status"] == "BLOQUEADO":
        raise ControlError("Blocked gate cannot be completed")
    missing = sorted(set(gate["required_evidence"]) - recorded_kinds(gate))
    if missing:
        raise ControlError("Missing required evidence: " + ", ".join(missing))
    summary = args.summary.strip()
    if len(summary) < 12:
        raise ControlError("Completion summary is too vague")
    gate["status"] = gate["target_status"]
    gate["completed_at"] = timestamp()
    gate["summary"] = summary
    save(data)
    print(f"{args.gate} completed as {gate['target_status']}.")


def cmd_block(args: argparse.Namespace) -> None:
    data = load()
    gate = ensure_active(data, args.gate)
    reason = args.reason.strip()
    if len(reason) < 12:
        raise ControlError("Blocker reason is too vague")
    gate["started_at"] = gate["started_at"] or timestamp()
    gate["status"] = "BLOQUEADO"
    gate["blockers"].append({"created_at": timestamp(), "reason": reason, "resolved_at": None})
    save(data)
    print(f"{args.gate} blocked.")


def cmd_unblock(args: argparse.Namespace) -> None:
    data = load()
    gate = require_gate(data, args.gate)
    if gate["status"] != "BLOQUEADO":
        raise ControlError("Gate is not blocked")
    unresolved = [item for item in gate["blockers"] if item.get("resolved_at") is None]
    if not unresolved:
        raise ControlError("No unresolved blocker")
    for item in unresolved:
        item["resolved_at"] = timestamp()
    gate["status"] = "EM_EXECUCAO"
    save(data)
    print(f"{args.gate} unblocked.")


def cmd_final(_: argparse.Namespace) -> None:
    data = load()
    found = errors(data)
    for gate_id in data["workflow"]:
        gate = data["gates"][gate_id]
        if not complete(gate):
            found.append(f"{gate_id}: {gate['status']} != {gate['target_status']}")
        missing = sorted(set(gate["required_evidence"]) - recorded_kinds(gate))
        if missing:
            found.append(f"{gate_id}: missing {','.join(missing)}")
        if any(item.get("resolved_at") is None for item in gate["blockers"]):
            found.append(f"{gate_id}: unresolved blocker")
    if found:
        for item in found:
            print(f"INCOMPLETE: {item}")
        raise ControlError(f"Final check failed with {len(found)} issue(s)")
    print("FINAL CHECK PASSED: all gates reached verified target states.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subs = result.add_subparsers(dest="command", required=True)
    for name, handler in [
        ("init", cmd_init),
        ("verify", cmd_verify),
        ("next", cmd_next),
        ("final-check", cmd_final),
        ("sync-plan", cmd_sync_plan),
    ]:
        child = subs.add_parser(name)
        child.set_defaults(handler=handler)
    child = subs.add_parser("status")
    child.add_argument("--json", action="store_true")
    child.set_defaults(handler=cmd_status)
    for name, handler in [("start", cmd_start), ("unblock", cmd_unblock)]:
        child = subs.add_parser(name)
        child.add_argument("gate")
        child.set_defaults(handler=handler)
    child = subs.add_parser("evidence")
    child.add_argument("gate")
    child.add_argument("kind", choices=sorted(KINDS))
    child.add_argument("value")
    child.set_defaults(handler=cmd_evidence)
    child = subs.add_parser("complete")
    child.add_argument("gate")
    child.add_argument("--summary", required=True)
    child.set_defaults(handler=cmd_complete)
    child = subs.add_parser("block")
    child.add_argument("gate")
    child.add_argument("reason")
    child.set_defaults(handler=cmd_block)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
        return 0
    except ControlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
