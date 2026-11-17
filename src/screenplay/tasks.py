"""Trusted task loading. Return only public_view() to agents."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from .build import ROOT


@dataclass(frozen=True)
class Task:
    task_id: str
    game: str
    game_id: str
    instruction: str
    rules: str
    max_decisions: int
    expected_desc: str | None = None
    package: str = "tatham"
    time_mode: str = "turn_based"
    undo_allowed: bool = True
    parameters: dict = field(default_factory=dict)

    def public_view(self) -> dict:
        view = {"instruction": self.instruction, "rules": self.rules,
                "max_decisions": self.max_decisions, "time_mode": self.time_mode,
                "controls": ["click", "mouse_move", "drag", "key_press", "wait", "finish"],
                "undo_allowed": self.undo_allowed, "solve_allowed": False}
        if "max_updates" in self.parameters:
            view["max_simulation_updates"] = self.parameters["max_updates"]
            view["time_contract"] = {
                "frozen_while_thinking": True,
                "updates_per_input": 8 if self.package == "openttd" else 6,
                "wait_quantum_ms": 30 if self.package == "openttd" else self.parameters.get("update_ms", 33),
                "wait_updates": "ceil(duration_ms / wait_quantum_ms), capped by remaining budget",
                "finish_and_rejected_inputs_updates": 0,
                "meaning": "Updates are simulation opportunities. Native pause, speed and modal state can affect game-time progress; requested updates still consume the budget.",
            }
        return view


def catalog() -> dict[str, dict]:
    tasks = {}
    for path in sorted((ROOT / "game_packages").glob("*/tasks.json")):
        for task_id, item in json.loads(path.read_text()).items():
            if task_id in tasks:
                raise ValueError(f"Duplicate task ID: {task_id}")
            tasks[task_id] = {**item, "package": path.parent.name}
    return tasks


def load_task(task_id: str) -> Task:
    item = catalog().get(task_id)
    if item is None:
        raise ValueError(f"Unknown task: {task_id}")
    return Task(task_id=task_id, **{k: v for k, v in item.items() if k != "reference"})


def parse_save(serialized: str) -> list[tuple[str, str]]:
    """Length-aware parsing of upstream saves; do not split payloads on colons."""
    entries = []
    data = serialized.encode("ascii")
    pos = 0
    while pos < len(data):
        if data[pos:pos + 1] in (b"\r", b"\n"):
            pos += 1
            continue
        if pos + 9 > len(data) or data[pos + 8:pos + 9] != b":":
            raise ValueError("Malformed upstream save record")
        key = data[pos:pos + 8].decode().strip()
        start = pos + 9
        colon = data.find(b":", start)
        if colon < 0 or not data[start:colon].isdigit():
            raise ValueError("Invalid upstream save length")
        size = int(data[start:colon])
        pos = colon + 1
        if pos + size > len(data):
            raise ValueError("Truncated upstream save")
        entries.append((key, data[pos:pos + size].decode()))
        pos += size
    if not entries or entries[0][0] != "SAVEFILE":
        raise ValueError("Missing upstream save header")
    return entries


def evaluate(state: dict, initial_desc: str, game: str) -> dict:
    entries = parse_save(state["serialized"])
    fields = dict(entries)
    violations = []
    if fields.get("GAME") != game or fields.get("DESC") != initial_desc:
        violations.append("initial_puzzle_changed")
    if any(k == "SOLVE" for k, _ in entries):
        violations.append("solver_used")
    success = state["status"] == 1 and not violations
    return {"success": success, "score": float(success), "violations": violations,
            "state_position": int(fields["STATEPOS"]),
            "evaluator": "tatham-native-status-v1", "progress": None}
