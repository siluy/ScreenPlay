"""New text invitations preserve the legacy protocol and use the native task caps."""
from collections import Counter
import json
import sqlite3

from screenplay_human.catalog import NEW_TEXT_PACKAGES
from screenplay_human.study import Study
from test_human_study import Runtime


def test_new_text_preset_is_exactly_45_and_disjoint_from_original(tmp_path):
    s = Study(tmp_path / "study", runtime_factory=Runtime)
    try:
        tasks = {t["task_id"]: t for t in s.public_catalog()}
        presets = {p["id"]: p for p in s.invitation_presets()}
        new = presets["new_text45"]
        old = presets["original_text45"]
        assert new["condition"] == "text"
        assert len(new["task_ids"]) == len(set(new["task_ids"])) == 45
        assert Counter(tasks[t]["package"] for t in new["task_ids"]) == {"singularity": 15, "openttd": 15, "enigma": 15}
        assert len(old["task_ids"]) == 45 and set(new["task_ids"]).isdisjoint(old["task_ids"])
        assert len(tasks) == 90 and all(t["text_supported"] for t in tasks.values())
        assert set(new["task_ids"]) | set(old["task_ids"]) == set(tasks)
        assert all(tasks[t]["text_max_decisions"] == s.tasks[t]["max_decisions"] for t in new["task_ids"])
    finally:
        s.close()


def test_invitation_budget_is_saved_and_used_for_native_start(tmp_path):
    s = Study(tmp_path / "study", decisions=77, runtime_factory=Runtime)
    try:
        new = next(p for p in s.invitation_presets() if p["id"] == "new_text45")
        invitation = s.invite("NEW45", new["task_ids"], "text", seed=1)
        pid = invitation["participant_id"]
        plan = json.loads(s.db.execute("SELECT plan FROM participants WHERE id=?", (pid,)).fetchone()[0])
        assert len(plan) == 45 and all(p["condition"] == "text" for p in plan)
        assert all(p["max_decisions"] == s.tasks[p["task_id"]]["max_decisions"] for p in plan)
        assert all(p["assignment_protocol"] == "new-text45-task-native-v1" for p in plan)
        s.consent(pid)
        assert s.state(pid)["participant"]["next_task"]["max_decisions"] == plan[0]["max_decisions"]
        attempt = s.start(pid)
        assert attempt["observation"]["budget_remaining"] == plan[0]["max_decisions"] != 77
        report = s.export()["report"]
        assert all(r["max_decisions"] == s.tasks[r["task_id"]]["max_decisions"] for r in report["rows"])
        assert s.config["max_decisions"] == 77

        original = s.invite("OLD", ["fifteen-01"], "text")
        s.consent(original["participant_id"])
        assert s.start(original["participant_id"])["observation"]["budget_remaining"] == 77
        gui = s.invite("GUI", ["openttd-dispatch"], "gui")
        assert s.state(gui["participant_id"])["participant"]["next_task"]["max_decisions"] == 77
    finally:
        s.close()


def test_old_invitations_survive_upgrade_without_plan_or_limit_rewrite(tmp_path):
    directory = tmp_path / "study"
    s = Study(directory, runtime_factory=Runtime)
    invitation = s.invite("EXISTING", ["fifteen-01", "openttd-dispatch"], "gui")
    pid = invitation["participant_id"]
    original = s.db.execute("SELECT plan FROM participants WHERE id=?", (pid,)).fetchone()[0]
    s.close()
    with sqlite3.connect(directory / "study.sqlite3") as db:
        config = json.loads(db.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])
        config["version"] = "0.2.3"
        db.execute("UPDATE meta SET value=? WHERE key='config'", (json.dumps(config),))
    s = Study(directory, runtime_factory=Runtime)
    try:
        assert s.db.execute("SELECT plan FROM participants WHERE id=?", (pid,)).fetchone()[0] == original
        assert s.identity(s.login("participant", invitation["invitation_code"]))["participant_id"] == pid
        assert s.config["version"] == "0.2.3" and s.config["max_decisions"] == 100
        assert s.state(pid)["participant"]["next_task"]["max_decisions"] == 100
        exported = s.export()["participants"][0]["assignment"]
        assert all(item["max_decisions"] == 100 for item in exported)
    finally:
        s.close()


def test_new_text_observation_whitelist_exposes_controls_not_private_state():
    public = Study._public({"game": "Enigma", "observation": {
        "observation_id": 1, "budget_remaining": 159, "board_text": "Visible board",
        "interface_profile": "enigma-visible-board-impulses-v0", "experimental": True,
        "simulation_updates_remaining": 29994, "native_fixture": "PRIVATE", "reference": "PRIVATE",
        "native_state": {"hidden_color": 3}, "parameters": {"goal": "PRIVATE"}}})
    assert public["interface_profile"] == "enigma-visible-board-impulses-v0"
    assert public["simulation_updates_remaining"] == 29994
    assert "PRIVATE" not in json.dumps(public) and "hidden_color" not in json.dumps(public)
