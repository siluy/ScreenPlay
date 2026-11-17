"""Human-facing interface availability; task definitions remain unchanged."""

ORIGINAL_TEXT_PACKAGES = frozenset({"tatham", "pysolfc", "endless_sky"})
NEW_TEXT_PACKAGES = frozenset({"singularity", "openttd", "enigma"})
TEXT_PACKAGES = ORIGINAL_TEXT_PACKAGES | NEW_TEXT_PACKAGES


def text_group(task):
    if task["package"] in NEW_TEXT_PACKAGES:
        return "new_text45"
    if task["package"] in ORIGINAL_TEXT_PACKAGES:
        return "original_text45"
    return None


def decision_limit(task, condition, default):
    return task["max_decisions"] if condition == "text" and task["package"] in NEW_TEXT_PACKAGES else default


def invitation_presets(tasks):
    return [{"id": group, "label": label, "condition": "text",
             "task_ids": sorted(key for key, task in tasks.items() if text_group(task) == group)}
            for group, label in [("new_text45", "全选新增 45 道文本题"),
                                 ("original_text45", "选择原有 45 道文本题")]]
