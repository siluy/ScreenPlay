"""Export the authored v1 task catalogue and recorded desktop evidence."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gameworld.tasks import catalog, load_task
from gameworld.protocol import ACTION

NAMES = {"tatham": "Tatham Puzzles", "openttd": "OpenTTD", "singularity": "Endgame: Singularity",
         "pysolfc": "PySolFC / FreeCell", "enigma": "Enigma", "endless_sky": "Endless Sky"}
LEVELS = {"easy": "简单", "medium": "中等", "hard": "困难"}


def semantic_fixture(task):
    return {"game": task["game"], "game_id": task["game_id"],
            "expected_desc": task.get("expected_desc"),
            "parameters": {k: v for k, v in task.get("parameters", {}).items() if k != "curriculum"}}


def main():
    tasks = catalog()
    counts = Counter((t["package"], t["parameters"]["curriculum"]["difficulty"]) for t in tasks.values())
    assert len(tasks) == 90 and all(counts[p, d] == 5 for p in NAMES for d in LEVELS)
    attempts = {name: [] for name in tasks}
    for path in sorted((ROOT / "runs/v1-acceptance").glob("*/private/task.json")):
        snapshot = json.loads(path.read_text())
        name = snapshot["task_id"]
        if name not in tasks or semantic_fixture(snapshot) != semantic_fixture(tasks[name]):
            continue
        run = path.parent.parent
        if tasks[name]["package"] == "enigma":
            level = path.parent / "level.xml"
            current = ROOT / "game_packages/enigma/levels" / f"{tasks[name]['game_id']}.xml"
            if not level.exists() or level.read_bytes() != current.read_bytes():
                continue
        result_path = run / "result.json"
        if not result_path.exists():
            continue
        result = json.loads(result_path.read_text())
        current_invariants = True
        if tasks[name]["package"] == "endless_sky":
            states_path = path.parent / "states.jsonl"
            if states_path.exists():
                last_state = json.loads(states_path.read_text().splitlines()[-1])["state"]
                current_invariants = last_state.get("outfits_kept") is True
            else:
                current_invariants = False
        interactions = run / "interactions.jsonl"
        actions = [json.loads(x) for x in interactions.read_text().splitlines()] if interactions.exists() else []
        real_inputs = all(x.get("input_provider") == "pyautogui" for x in actions)
        frames_present = (run / "frames/000000.png").exists() and all(
            not x.get("frame_after") or (run / x["frame_after"]).exists() for x in actions)
        attempts[name].append({"directory": str(run.relative_to(ROOT)), "result": result,
                               "recorded_desktop_success": bool(result.get("success") and current_invariants and real_inputs and frames_present and actions
                                                                and result.get("decisions", 0) <= tasks[name]["max_decisions"])})
    rows = []
    for package in NAMES:
        for difficulty in LEVELS:
            for task_id, item in tasks.items():
                curriculum = item["parameters"]["curriculum"]
                if item["package"] != package or curriculum["difficulty"] != difficulty:
                    continue
                task = load_task(task_id)
                reference = item.get("reference", {})
                for action in reference.get("actions", []):
                    ACTION.validate_python(action)
                rows.append({"task_id": task_id, "package": package, "game": task.game,
                             **curriculum, "difficulty_status": "author_estimate",
                             "instruction": task.instruction, "max_decisions": task.max_decisions,
                             "max_simulation_updates": task.parameters.get("max_updates"),
                             "reference_actions": len(reference.get("actions", [])) or None,
                             "desktop_success": any(a["recorded_desktop_success"] for a in attempts[task_id]),
                             "desktop_attempts": attempts[task_id]})
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "version": "v1-development-90",
              "task_count": len(rows), "project_count": 6, "difficulty_status": "author_estimate",
              "desktop_success_count": sum(r["desktop_success"] for r in rows), "tasks": rows}
    (ROOT / "artifacts").mkdir(parents=True, exist_ok=True)
    (ROOT / "artifacts/v1-task-catalog.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# GameWorld 初版 90 题目录", "", "六个独立项目，每个 15 题；简单、中等、困难各 5 题。全部属于 development 集，难度是作者预估，尚未经统一人类与模型实验校准。Tatham 的三个子游戏共同计为一个项目。", "",
             "难度依据规划依赖、状态与记忆负担、资源约束、操作精度及恢复空间。参考轨迹长度是可行性证据，不是最优解或难度标签。不同项目的同一难度标签不表示难度相等。", "",
             f"当前目录中的 **{report['desktop_success_count']}/90** 题已有与当前场景参数一致的成功桌面记录。下表仅将真实截图、PyAutoGUI 输入及原生成功判分同时具备的记录标为「已通关」；原生规则可解性、静态拓扑检查和初态启动属于其他证据。", "",
             "[结构化目录](artifacts/v1-task-catalog.json) · [开发与验证说明](docs/development.md)", ""]
    for package, title in NAMES.items():
        lines += [f"## {title}", "", f"[任务定义](game_packages/{package}/tasks.json)", "",
                  "| 任务 | 难度 | 机制 | 桌面证据 |", "|---|---|---|---|"]
        for row in (r for r in rows if r["package"] == package):
            good = next((a for a in reversed(row["desktop_attempts"]) if a["recorded_desktop_success"]), None)
            evidence = f"[已通关]({good['directory']}/replay.html)" if good else "待通关验收"
            lines.append(f"| {row['task_id']} | {LEVELS[row['difficulty']]} | {', '.join(row['mechanisms'])} | {evidence} |")
        lines.append("")
        for row in (r for r in rows if r["package"] == package):
            lines += [f"### {row['task_id']}", "", row["instruction"].replace("$", "\\$"), "", "分层依据：" + row["difficulty_rationale"], ""]
    (ROOT / "90题任务目录.md").write_text("\n".join(lines))
    print(json.dumps({k: v for k, v in report.items() if k != "tasks"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
