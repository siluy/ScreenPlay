"""One focused audit: text actions must reproduce the existing native witnesses."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from screenplay.tasks import catalog
from screenplay.validation import engine_run, reference_commands
from screenplay_text.fifteen import CONDITIONS, FifteenText, build_request, task_ids


def audit() -> dict:
    checks = []
    data = catalog()
    for task in task_ids():
        actions = data[task]["reference"]["actions"]
        native = engine_run(data[task], "\n".join(reference_commands(actions)))
        for condition in CONDITIONS:
            env = FifteenText(task, condition)
            for action in actions:
                mapped = ({"type": "slide", "row": action["y"] // env.tile_size,
                           "column": action["x"] // env.tile_size}
                          if condition == "text-symbolic" else
                          {"type": "click", "x": action["x"], "y": action["y"]})
                env.step(mapped)
                if env.result:
                    break
            assert env.result and env.result["success"], (task, condition, env.result)
            assert env.board == list(range(1, env.width * env.height)) + [0], task
            # The selected fixtures' reference paths first solve on their last action.
            assert env._native["serialized"] == native["serialized"], (task, condition)
            checks.append({"task": task, "condition": condition,
                           "reference_decisions": len(actions), "decisions": env.decisions,
                           "native_save_equal": True, "native_success": True})
    # Non-adjacent native slides, undo/redo/restart, and decision accounting.
    env = FifteenText("fifteen-12")
    initial = list(env.board)
    env.step({"type": "slide", "row": 3, "column": 1})
    assert env.board == [1, 6, 2, 5, 3, 8, 0, 4, 7] and env.decisions == 1
    moved = list(env.board)
    env.step({"type": "undo"}); assert env.board == initial
    env.step({"type": "redo"}); assert env.board == moved
    env.step({"type": "restart"}); assert env.board == initial and env.decisions == 4
    env.step({"type": "slide", "row": 1, "column": 1})
    assert env.board == initial and env.receipt["status"] == "executed"  # diagonal no-op
    for invalid in [{"type": "slide", "row": True, "column": 1},
                    {"type": "slide", "row": 0, "column": 1}, {"type": "solve"},
                    [{"type": "wait"}, {"type": "wait"}]]:
        env.step(invalid)
        assert env.board == initial and env.receipt["status"] == "rejected"
    assert env.decisions == 9
    limited = FifteenText("fifteen-01", max_decisions=1)
    assert limited.step({"type": "slide", "row": 3, "column": 3})["result"]["success"]
    limited = FifteenText("fifteen-12", max_decisions=1)
    assert limited.step({"type": "wait"})["result"]["stop_reason"] == "decision_budget_exhausted"
    assert not limited.result["success"]
    try:
        limited.step({"type": "wait"})
        raise AssertionError("Action after termination was accepted")
    except RuntimeError:
        pass
    finished = FifteenText("fifteen-12")
    assert finished.step({"type": "finish"})["result"]["score"] == 0
    # Six prior observations: retain four boards plus current, but every action/reply.
    env = FifteenText("fifteen-12")
    turns = []
    for index in range(6):
        before = env.observe()
        after = env.step({"type": "wait"})
        turns.append({"observation": before, "receipt": after["receipt"], "assistant": {
            "role": "assistant", "content": None, "reasoning_content": f"synthetic-history-{index}",
            "tool_calls": [{"id": f"call-{index}", "type": "function",
                            "function": {"name": "wait", "arguments": "{}"}}]}})
    request = build_request(turns, env.observe(), window=5)
    users = [json.loads(m["content"]) for m in request["messages"] if m["role"] == "user"]
    assert sum("Row 1:" in o["board_text"] for o in users) == 5
    assert len([m for m in request["messages"] if m["role"] == "assistant"]) == 6
    assert len([m for m in request["messages"] if m["role"] == "tool"]) == 6
    assert [m["reasoning_content"] for m in request["messages"] if m["role"] == "assistant"] == [f"synthetic-history-{i}" for i in range(6)]
    public = env.observe()
    assert not {"reference", "expected_desc", "serialized", "initial_desc", "legal_moves",
                "solution", "difficulty_rationale"}.intersection(public)
    assert "image_url" not in json.dumps(request)
    assert all("Row 1:" not in json.loads(m["content"])["board_text"]
               for m in build_request(turns, env.observe(), window=1)["messages"]
               if m["role"] == "user" and json.loads(m["content"])["observation_id"] < 6)
    return {"created_at": datetime.now(timezone.utc).isoformat(), "passed": True,
            "tasks": len(task_ids()), "conditions": list(CONDITIONS),
            "witness_checks": checks, "edge_cases": ["multi-tile slide", "undo/redo/restart",
            "diagonal no-op", "invalid and solver inputs rejected", "every decision charged",
            "success on final allowed decision", "unsolved budget failure", "finish failure",
            "no actions after termination", "k5 boards with full action/receipt/reasoning history",
            "k1 current board only", "no images or private solution fields in observation"],
            "model_requests_sent": 0, "desktop_actions_sent": 0,
            "scope": "Original native engine parity and public-interface audit; not autonomous model performance."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "research/text-ablation/native-parity.json")
    args = parser.parse_args()
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ["passed", "tasks", "conditions", "model_requests_sent", "desktop_actions_sent"]}))
