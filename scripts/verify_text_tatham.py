"""Verify Net/Untangle text controls against original native author mouse traces."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gameworld.tasks import catalog
from gameworld.validation import engine_run, reference_commands
from gameworld_text.fifteen import build_request
from gameworld_text.tatham import make_environment
from gameworld_text.agent import parse_action


def audit():
    checks = []
    data = {k:v for k,v in catalog().items() if v["game"] in {"Net", "Untangle"}}
    for task, item in data.items():
        env = make_environment(task)
        initial = env.observe()
        assert not initial["ended"] and env._score["score"] == 0
        native_prefix = []
        for a in item["reference"]["actions"]:
            if item["game"] == "Net":
                action = {"type": "rotate", "row": a["y"]//32, "column": a["x"]//32,
                          "direction": "clockwise" if a.get("button") == "right" else "counterclockwise"}
            else:
                node = min(range(env.node_count), key=lambda i:sum((env.points[i][j]-a["from"][j])**2 for j in (0,1)))
                assert sum((env.points[node][j]-a["from"][j])**2 for j in (0,1)) <= 2
                action = {"type": "move_node", "node": node+1, "x": a["to"][0], "y": a["to"][1]}
            env.step(action)
            native_prefix += reference_commands([a])
            expected = engine_run(item, "\n".join(native_prefix))
            assert env._native["serialized"] == expected["serialized"], (task, env.decisions)
            assert env._native["status"] == expected["status"]
            if env.result:
                break
        assert env.result and env.result["success"], (task, env.result)
        public = json.dumps(build_request([], initial))
        for forbidden in ['AUXINFO', 'SOLVE', 'expected_desc', 'serialized', 'reference_actions', 'solution_layout', 'image_url']:
            assert forbidden not in public, (task, forbidden)
        checks.append({"task": task, "game": item["game"], "native_success": True,
                       "every_prefix_save_equal": True, "decisions": env.decisions,
                       "reference_actions": len(item["reference"]["actions"])})
    net = make_environment("net-3x3")
    assert net.tiles == [2, 9, 4, 6, 14, 9, 9, 5, 2]
    net.step({"type":"rotate","row":1,"column":1,"direction":"clockwise"})
    assert net.tiles[0] == 1
    net.step({"type":"undo"}); assert net.tiles[0] == 2
    net.step({"type":"redo"}); assert net.tiles[0] == 1
    net.step({"type":"toggle_lock","row":1,"column":1}); assert net.tiles[0] == 17
    net.step({"type":"rotate","row":1,"column":1,"direction":"counterclockwise"}); assert net.tiles[0] == 17
    net.step({"type":"restart"}); assert net.tiles[0] == 2
    net.step({"type":"solve"}); assert net.receipt["status"] == "rejected" and net.decisions == 7
    barrier = make_environment("net-barriers"); assert barrier.barriers[1] & 8 and barrier.barriers[5] & 2
    wrapped = make_environment("net-wrapping"); assert wrapped.wrapping and all(x == 0 for x in wrapped.barriers)
    unt = make_environment("untangle-6"); initial = list(unt.points)
    unt.step({"type":"move_node","node":1,"x":33,"y":44}); assert unt.points[0] == (33,44)
    unt.step({"type":"undo"}); assert unt.points == initial
    unt.step({"type":"redo"}); assert unt.points[0] == (33,44)
    unt.step({"type":"move_node","node":2,"x":33,"y":44}); assert unt.points[1] == (33,44)
    unt.step({"type":"move_node","node":2,"x":55,"y":66}); assert unt.points[0] == (55,66) and unt.points[1] == (33,44)
    unt.step({"type":"restart"}); assert unt.points == initial
    for task in data:
        env = make_environment(task, max_decisions=1)
        assert env.step({"type":"wait"})["result"]["stop_reason"] == "decision_budget_exhausted"
        request = build_request([], env.observe())
        function = request["tools"][0]["function"]
        raw = {"choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"name":function["name"],"arguments":"{}"}}]}}]}
        assert parse_action(raw, "text-symbolic", env.game_name)[1] is None
    return {"created_at":datetime.now(timezone.utc).isoformat(), "passed":True,
            "tasks":len(data), "checks":checks, "edge_cases":["Net rotation directions","locks prevent rotation",
            "barrier symmetry and wrapping", "undo/redo/restart", "solver rejected", "Untangle native overlap picking",
            "one-step budget failure", "game-specific model tools", "private solver metadata excluded"],
            "model_requests_sent":0,"desktop_actions_sent":0,
            "scope":"Native transition and evaluator parity, not model performance or a GUI replay."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"research/text-ablation/tatham9-native-parity.json")
    args = parser.parse_args()
    result = audit();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ["passed","tasks","model_requests_sent","desktop_actions_sent"]}))
