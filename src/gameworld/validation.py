"""Validate fixtures against real upstream game logic without desktop permissions."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from .build import ROOT, source_spec
from .tasks import catalog, parse_save, evaluate


def reference_commands(actions: list[dict]) -> list[str]:
    """Translate author mouse actions to original midend input events."""
    blocks = []
    for action in actions:
        button = {"left": 512, "middle": 513, "right": 514}[action.get("button", "left")]
        if action["type"] == "click":
            x, y = action["x"], action["y"]
            blocks.append("\n".join([f"input {x} {y} {button}\ninput {x} {y} {button + 6}"] * action.get("count", 1)))
        elif action["type"] == "drag":
            x, y = action["from"]
            tx, ty = action["to"]
            blocks.append(f"input {x} {y} {button}\ninput {tx} {ty} {button + 3}\ninput {tx} {ty} {button + 6}")
        else:
            raise ValueError(f"Unsupported native reference action: {action['type']}")
    return blocks


def engine_run(task: dict, commands: str):
    binary = ROOT / "build/tatham/bin/gw-engine"
    result = subprocess.run([str(binary), task["game"], task["game_id"]],
                            input=commands + "\nsave\n", text=True, capture_output=True,
                            env=dict(os.environ, GAMEWORLD_SESSION="trusted-validation"), timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr)
    serialized = result.stdout.split("SAVE_BEGIN\n",1)[1].split("SAVE_END",1)[0]
    statuses = [int(x) for x in re.findall(r"^STATUS (-?\d+)$", result.stdout, re.M)]
    size = re.search(r"^SIZE (\d+) (\d+)$", result.stdout, re.M)
    return {"serialized": serialized, "status":statuses[-1], "statuses":statuses,
            "size":[int(size[1]),int(size[2])], "output":result.stdout}


def validate(output: Path | None = None) -> dict:
    checks = []
    tasks = {k:v for k,v in catalog().items() if v["package"] == "tatham"}
    for task_id, task in tasks.items():
        first = engine_run(task,"status")
        second = engine_run(task,"status")
        actual_desc = dict(parse_save(first["serialized"]))["DESC"]
        checks.append({"task":task_id,"check":"reset_determinism_and_initial_failure",
                       "passed":first["serialized"] == second["serialized"] and first["status"] == 0
                       and actual_desc == task["expected_desc"]})
        solve = engine_run(task,"solve")
        checks.append({"task":task_id,"check":"native_solver_blocked",
                       "passed":"Solve is disabled" in solve["output"] and solve["status"] == 0})
        if task.get("reference"):
            blocks = reference_commands(task["reference"]["actions"])
            commands = "\n".join(blocks)
            final = engine_run(task,commands)
            score = evaluate(final, task["expected_desc"], task["game"])
            checks.append({"task":task_id,"check":"reference_inputs_reach_native_goal",
                           "passed":score["success"],"input_decisions":len(task["reference"]["actions"])})
            # A reference can contain harmless moves after the first solution.
            # Reject the prefix immediately before the first successful action.
            event_count = 0
            first_success = len(blocks)
            for index, block in enumerate(blocks):
                event_count += len(block.splitlines())
                if final["statuses"][event_count] == 1:
                    first_success = index
                    break
            almost = engine_run(task,"\n".join(blocks[:first_success]))
            checks.append({"task":task_id,"check":"incomplete_solution_rejected",
                           "passed":not evaluate(almost,task["expected_desc"],task["game"])["success"]})
    report = {"created_at":datetime.now(timezone.utc).isoformat(),"source":source_spec(),
              "scope":"real-upstream-engine input and grading; not a GUI or model evaluation",
              "passed":all(c["passed"] for c in checks),"checks":checks,
              "task_count":len(tasks),"upstream_families":1}
    target = output or ROOT / "artifacts/engine-validation.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+"\n")
    return report
