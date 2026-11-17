"""Research summaries: one formal outcome per participant/assigned task.

Unknown outcomes never become failures, and missing timing never becomes zero.
Every mean is accompanied by its own non-missing denominator.
"""
from collections import defaultdict
from math import isfinite
from statistics import fmean

PROJECTS = {"tatham": "Tatham Puzzles", "openttd": "OpenTTD", "singularity": "Endgame: Singularity",
            "pysolfc": "PySolFC FreeCell", "enigma": "Enigma", "endless_sky": "Endless Sky"}
DIFFICULTIES = {"easy": "简单", "medium": "中等", "hard": "困难", "unknown": "未标注"}


def number(value):
    return type(value) in (int, float) and isfinite(value) and value >= 0


def metrics(rows):
    scored = [r for r in rows if r["status"] == "scored" and type(r["correct"]) is bool]
    correct = [r for r in scored if r["correct"]]
    times = [r["elapsed_seconds"] for r in scored if number(r["elapsed_seconds"])]
    steps = [r["decisions"] for r in scored if type(r["decisions"]) is int and r["decisions"] >= 0]
    good_times = [r["elapsed_seconds"] for r in correct if number(r["elapsed_seconds"])]
    good_steps = [r["decisions"] for r in correct if type(r["decisions"]) is int and r["decisions"] >= 0]
    return {"assigned_count": len(rows), "scored_count": len(scored), "correct_count": len(correct),
            "incorrect_count": len(scored)-len(correct), "unscored_count": len(rows)-len(scored),
            "active_count": sum(r["status"] in {"starting", "active"} for r in rows),
            "paused_count": sum(r["status"] == "paused" for r in rows),
            "not_started_count": sum(r["status"] == "not_started" for r in rows),
            "interrupted_count": sum(r["status"] == "interrupted" for r in rows),
            "withdrawn_unstarted_count": sum(r["status"] == "withdrawn_unstarted" for r in rows),
            "interrupted_attempt_count": sum(r["interrupted_attempt_count"] for r in rows),
            "accuracy": len(correct)/len(scored) if scored else None,
            "mean_elapsed_seconds": fmean(times) if times else None, "elapsed_n": len(times),
            "elapsed_missing_n": len(scored)-len(times),
            "estimated_elapsed_n": sum(r["elapsed_source"] == "legacy_wall_clock_estimate" and number(r["elapsed_seconds"]) for r in scored),
            "mean_decisions": fmean(steps) if steps else None, "decisions_n": len(steps),
            "decisions_missing_n": len(scored)-len(steps),
            "mean_success_elapsed_seconds": fmean(good_times) if good_times else None,
            "success_elapsed_n": len(good_times),
            "mean_success_decisions": fmean(good_steps) if good_steps else None,
            "success_decisions_n": len(good_steps),
            "participants_n": len({r["participant_id"] for r in rows}),
            "task_conditions_n": len({(r["task_id"], r["condition"]) for r in rows})}


def grouped(rows, key, label):
    groups = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return [{"key": k, "label": label(items[0]), **metrics(items)} for k, items in sorted(groups.items())]


def build_report(participants, attempts, tasks):
    by_assignment = defaultdict(list)
    for attempt in attempts:
        by_assignment[(attempt["participant_id"], attempt["task_index"])].append(attempt)
    rows = []
    for participant in participants:
        for index, assignment in enumerate(participant["assignment"]):
            task = tasks[assignment["task_id"]]
            history = by_assignment[(participant["id"], index)]
            # The study disallows redoing scored tasks. Retain its first formal
            # result even if an externally altered DB contains later duplicates.
            formal = [a for a in history if a["status"] == "scored" and type((a["result"] or {}).get("success")) is bool]
            selected = formal[0] if formal else history[-1] if history else None
            result = selected["result"] or {} if selected else {}
            difficulty = task.get("parameters", {}).get("curriculum", {}).get("difficulty", "unknown")
            rows.append({"participant_id": participant["id"], "participant": participant["alias"],
                         "task_index": index, "question_number": index+1, "task_id": assignment["task_id"],
                         "condition": assignment["condition"], "package": task["package"],
                         "max_decisions": assignment.get("max_decisions"),
                         "assignment_protocol": assignment.get("assignment_protocol", "study_default"),
                         "project": PROJECTS.get(task["package"], task["package"]), "game": task["game"],
                         "difficulty": difficulty, "difficulty_label": DIFFICULTIES.get(difficulty, difficulty),
                         "status": selected["status"] if selected else "withdrawn_unstarted" if participant["withdrawn"] else "not_started",
                         "correct": result.get("success") if formal else None,
                         "decisions": selected.get("decisions") if selected else None,
                         "elapsed_seconds": selected.get("elapsed_seconds") if selected else None,
                         "elapsed_source": selected.get("elapsed_source") if selected else None,
                         "pause_count": selected.get("pause_count", 0) if selected else 0,
                         "paused_seconds": selected.get("paused_seconds") if selected else None,
                         "wall_elapsed_seconds": selected.get("wall_elapsed_seconds") if selected else None,
                         "started_at": selected["started"] if selected else None,
                         "finished_at": selected["finished"] if selected else None,
                         "stop_reason": result.get("stop_reason"), "attempt_id": selected["id"] if selected else None,
                         "attempt_count": len(history),
                         "interrupted_attempt_count": sum(a["status"] == "interrupted" for a in history),
                         "additional_scored_attempts": max(0, len(formal)-1),
                         "app_version": selected.get("app_version") if selected else None})
    views = []
    for pid, alias in [(None, "全部受试者")]+[(p["id"], p["alias"]) for p in participants]:
        for condition in ("all", "gui", "text"):
            subset = [r for r in rows if (pid is None or r["participant_id"] == pid) and (condition == "all" or r["condition"] == condition)]
            views.append({"participant_id": pid, "participant": alias, "condition": condition,
                          "overall": metrics(subset),
                          "by_condition": grouped(subset, lambda r: r["condition"], lambda r: "图片" if r["condition"] == "gui" else "文本"),
                          "by_project": grouped(subset, lambda r: r["package"], lambda r: r["project"]),
                          "by_game": grouped(subset, lambda r: r["game"], lambda r: r["game"]),
                          "by_difficulty": grouped(subset, lambda r: r["difficulty"], lambda r: r["difficulty_label"]),
                          "by_project_difficulty": grouped(subset, lambda r: r["package"]+"/"+r["difficulty"], lambda r: r["project"]+" / "+r["difficulty_label"]),
                          "by_task": grouped(subset, lambda r: r["task_id"], lambda r: r["task_id"])})
    return {"schema_version": 1,
            "policy": {"unit": "one_first_formal_result_per_participant_assignment",
                       "weighting": "each_scored_participant_task_equal_weight",
                       "accuracy_denominator": "scored_count",
                       "mean_denominators": "non_missing_values_in_scored_results; success_means_use_correct_results_only",
                       "unscored": "not_started, active, paused, interrupted, withdrawn_unstarted excluded from outcome means",
                       "elapsed": "server first observation ready to result determined minus explicit pauses; thinking and unpaused disconnection included; startup and process cleanup excluded",
                       "legacy_elapsed": "derived from old finished-started timestamps; may include cleanup; explicitly marked",
                       "steps": "native decisions, including invalid actions, undo and finish; duplicate request replay excluded"},
            "rows": rows, "views": views}
