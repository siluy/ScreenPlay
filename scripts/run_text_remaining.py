"""Interactive JSON-lines entry point for the three experimental text adapters.

Example: .venv/bin/python scripts/run_text_remaining.py --task singularity-intrusion
Then send {"type":"click","control":"u1_10"} on stdin. EOF closes the engine.
No model API call, human-study assignment or deployment is performed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameworld.tasks import load_task
from gameworld_text.tatham import make_environment, game_tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--max-decisions", type=int, help="Defaults to this task's native decision budget")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    task = load_task(args.task)
    if task.package not in {"singularity", "openttd", "enigma"}:
        parser.error("This entry point is for the three experimental adapters")
    if args.max_decisions is None:
        args.max_decisions = task.max_decisions
    output = args.output or ROOT / "runs/text-prototype" / (args.task + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    (output / "run_meta.json").write_text(json.dumps({
        "task_id": args.task, "condition": "text-symbolic", "experimental": True,
        "actor": "interactive", "max_decisions": args.max_decisions,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")
    env = make_environment(args.task, max_decisions=args.max_decisions)
    try:
        schemas = game_tools(task.game, "text-symbolic")
        obs = env.observe()
        (output / "initial.json").write_text(json.dumps({"observation": obs, "tools": schemas}, indent=2) + "\n")
        print(json.dumps({"observation": obs, "tools": schemas}, ensure_ascii=False), flush=True)
        with (output / "interactions.jsonl").open("a") as log:
            for line in sys.stdin:
                try:
                    action = json.loads(line)
                except json.JSONDecodeError:
                    print(json.dumps({"error": "invalid_json"}), flush=True)
                    continue
                before = obs
                obs = env.step(action)
                log.write(json.dumps({"before": before, "action": action, "after": obs}, ensure_ascii=False) + "\n")
                log.flush()
                print(json.dumps({"observation": obs}, ensure_ascii=False), flush=True)
                if obs["ended"]:
                    (output / "result.json").write_text(json.dumps(obs["result"], indent=2) + "\n")
                    break
    finally:
        env.close()
        print(f"Trace: {output}; private engine diagnostics: {env.private}", file=sys.stderr)


if __name__ == "__main__":
    main()
