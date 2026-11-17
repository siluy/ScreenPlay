"""One human attempt, isolated from other participants and model credentials.

The parent owns authentication, persistence, idempotency and deadlines. This
process only runs the existing native environment and its original evaluator.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys


def emit(value):
    sys.__stdout__.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--condition", choices=["gui", "text"], required=True)
    parser.add_argument("--decisions", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--actor", choices=["human", "validation"], default="human")
    args = parser.parse_args()
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    env = None
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from gameworld.runner import Episode, append_json, write_json
            from gameworld.tasks import load_task
            task = load_task(args.task)
            if args.condition == "gui":
                from gameworld.desktop import require_permissions
                require_permissions()
                env = Episode(replace(task, max_decisions=args.decisions), args.directory)
                obs = env.start()
                schemas = []
            else:
                from gameworld_text.tatham import make_environment
                from gameworld_text.fifteen import tools
                args.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
                (args.directory / "private").mkdir(mode=0o700)
                env = make_environment(args.task, "text-symbolic", args.decisions)
                obs = env.observe()
                schemas = tools("text-symbolic", task.game)
                write_json(args.directory / "run_meta.json", {
                    "task_id": args.task, "condition": "text-symbolic",
                    "actor": args.actor, "max_decisions": args.decisions,
                    "interface_profile": obs.get("interface_profile"),
                    "experimental_interface": obs.get("experimental", False),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                })
            write_json(args.directory / "human_provenance.json", {
                "actor": args.actor, "autonomous_model": False if args.actor == "human" else None,
                "interface": "browser", "condition": args.condition,
            })
        emit({"observation": obs, "schemas": schemas, "game": task.game})
        for line in sys.stdin:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if request["method"] == "close":
                    break
                before = obs
                if args.condition == "gui":
                    obs = env.act({"episode_id": env.id, "action_id": request["action_id"],
                                   "based_on_observation_id": request["observation_id"],
                                   "action": request["action"]})
                else:
                    obs = env.step(request["action"])
                    append_json(args.directory / "interactions.jsonl", {
                        "actor": args.actor, "action_id": request["action_id"],
                        "before": before, "action": request["action"], "after": obs,
                    })
                    if hasattr(env, "native_state"):
                        append_json(args.directory / "private/native_states.jsonl", env.native_state())
                    if obs.get("ended"):
                        write_json(args.directory / "result.json", obs["result"])
            emit({"observation": obs, "schemas": schemas, "game": task.game})
    except BaseException as exc:
        # Private diagnostics stay in stderr; no native saves or tracebacks enter
        # the browser protocol. Startup/execution errors are never human failures.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        emit({"error": "environment_error"})
        return 1
    finally:
        if env is not None and hasattr(env, "close"):
            with contextlib.redirect_stdout(sys.stderr):
                env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
