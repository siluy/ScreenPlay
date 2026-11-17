"""Study-level isolation and delivery regressions; no claims of native GUI QA."""
import copy
import json
import threading
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

import pytest

from screenplay_human.server import create_server
from screenplay_human.study import Study, StudyError


class Runtime:
    instances = []

    def __init__(self, task, condition, decisions, directory):
        self.moves = 0
        self.closed = False
        self.uncertain = False
        self.initial = {"observation": {"observation_id": 0, "instruction": "A public goal",
                        "rules": "Public rules", "board_text": "1 2 / blank 3",
                        "budget_remaining": decisions, "ended": False,
                        "serialized": "PRIVATE-SAVE", "reference": "PRIVATE-SOLUTION"},
                        "game": "Fifteen", "schemas": []}
        self.instances.append(self)

    def act(self, action_id, observation_id, action):
        self.moves += 1
        if self.uncertain:
            raise RuntimeError("native input may have executed")
        response = copy.deepcopy(self.initial)
        response["observation"].update(observation_id=self.moves, decision_index=self.moves,
                                      receipt={"status": "executed"})
        if action["type"] == "finish":
            response["observation"].update(ended=True, result={"success": False, "score": 0,
                                                             "stop_reason": "agent_finished", "decisions": self.moves})
        return response

    def close(self):
        self.closed = True


@pytest.fixture
def study(tmp_path):
    Runtime.instances = []
    s = Study(tmp_path / "study", runtime_factory=Runtime)
    yield s
    s.close()


def participant(s, name="P001", condition="text"):
    invitation = s.invite(name, ["fifteen-01"], condition)
    pid = invitation["participant_id"]
    s.consent(pid)
    return pid, invitation["invitation_code"]


def payload(obs=0, rid="one", action=None):
    return {"request_id": rid, "observation_id": obs, "action": action or {"type": "wait"}}


def test_action_delivery_and_uncertain_execution_are_not_replayed(study):
    pid, _ = participant(study)
    a = study.start(pid)
    assert "PRIVATE" not in json.dumps(a)
    first = study.action(pid, a["attempt_id"], payload())
    duplicate = study.action(pid, a["attempt_id"], payload())
    assert first["observation"] == duplicate["observation"]
    assert Runtime.instances[-1].moves == 1
    with pytest.raises(StudyError, match="payload_conflict"):
        study.action(pid, a["attempt_id"], payload(action={"type": "finish"}))
    with pytest.raises(StudyError, match="stale_observation"):
        study.action(pid, a["attempt_id"], payload(rid="stale"))
    Runtime.instances[-1].uncertain = True
    result = study.action(pid, a["attempt_id"], payload(obs=1, rid="uncertain"))
    assert result["observation"]["result"]["success"] is None
    assert study.action(pid, a["attempt_id"], payload(obs=1, rid="uncertain"))["observation"] == result["observation"]
    assert Runtime.instances[-1].moves == 2
    assert study.state(pid)["participant"]["completed"] == 0


def test_roles_ownership_and_completed_attempts(study):
    pid, code = participant(study)
    other, _ = participant(study, "P002")
    token = study.login("participant", code)
    with pytest.raises(StudyError) as exc:
        study.identity(token, "admin")
    assert exc.value.status == 403
    a = study.start(pid)
    with pytest.raises(StudyError) as exc:
        study.action(other, a["attempt_id"], payload())
    assert exc.value.status == 404
    study.action(pid, a["attempt_id"], payload(action={"type": "finish"}))
    with pytest.raises(StudyError, match="all_tasks_complete"):
        study.start(pid)
    exported = json.dumps(study.export())
    assert code not in exported and token not in exported and "code_hash" not in exported


def test_restart_retains_attempt_and_requires_explicit_new_start(tmp_path):
    directory = tmp_path / "resume"
    s = Study(directory, runtime_factory=Runtime)
    pid, _ = participant(s)
    a = s.start(pid)
    response = s.action(pid, a["attempt_id"], payload())
    s.close()
    s = Study(directory, runtime_factory=Runtime)
    try:
        assert s.state(pid)["active"] is None
        assert s.state(pid)["attempts"][0]["result"]["success"] is None
        assert s.action(pid, a["attempt_id"], payload())["observation"] == response["observation"]
        b = s.start(pid)
        assert b["attempt_id"] != a["attempt_id"]
        assert len(s.state(pid)["attempts"]) == 2
    finally:
        s.close()


def test_deadline_survives_idle_browser_and_releases_capacity(tmp_path):
    s = Study(tmp_path / "timed", wall_seconds=1, runtime_factory=Runtime)
    try:
        p1, _ = participant(s, "P001", "gui")
        p2, _ = participant(s, "P002", "gui")
        s.start(p1)
        with pytest.raises(StudyError, match="desktop_busy"):
            s.start(p2)
        time.sleep(1.7)  # No HTTP polling/action is needed for the watchdog.
        row = s.db.execute("SELECT status,result FROM attempts WHERE participant_id=?", (p1,)).fetchone()
        assert row["status"] == "scored"
        assert json.loads(row["result"])["stop_reason"] == "wall_budget_exhausted"
        assert s.export()["report"]["rows"][0]["elapsed_seconds"] == 1
        assert Runtime.instances[-1].closed
        s.start(p2)
        s.withdraw(p2)
        assert s.state(p2)["participant"]["withdrawn"]
        assert s.state(p2)["attempts"][-1]["result"]["success"] is None
    finally:
        s.close()


def test_http_boundary_participant_cannot_export_or_read_workspace(study):
    _, code = participant(study)
    server = create_server(study, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    def post(path, data, **headers):
        return opener.open(Request(base+path, data=json.dumps(data).encode(),
                           headers={"Content-Type": "application/json", "X-Study-Request": "1", **headers}), timeout=3)
    try:
        response = post("/api/login", {"kind": "participant", "code": code})
        assert "HttpOnly" in response.headers["Set-Cookie"]
        for path in ["/api/admin/export.json", "/api/admin/catalog", "/api/admin/results.csv", "/api/admin/summary.csv", "/.env", "/private/task.json", "/../study.sqlite3"]:
            with pytest.raises(HTTPError) as exc:
                opener.open(base+path)
            assert exc.value.code in {403, 404}
        with pytest.raises(HTTPError) as exc:
            post("/api/attempts", {}, Origin="https://untrusted.invalid")
        assert exc.value.code == 403
        with pytest.raises(HTTPError) as exc:
            opener.open(Request(base+"/api/session", headers={"Host": "untrusted.invalid"}))
        assert exc.value.code == 403
        post("/api/login", {"kind": "admin", "code": (study.directory/"admin-token.txt").read_text().strip()})
        data = json.load(opener.open(base+"/api/admin/export.json"))
        assert data["protocol"]["actor"] == "human"
        assert data["participants"][0]["alias"] == "P001"
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def test_public_origin_keeps_local_admin_and_remote_secure_cookies(study):
    _, code = participant(study)
    origin = "https://study.example.org"
    server = create_server(study, port=0, public_origin=origin)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
    def login(host, request_origin, kind, value):
        return opener.open(Request(base+"/api/login", data=json.dumps({"kind":kind,"code":value}).encode(),
            headers={"Content-Type":"application/json", "X-Study-Request":"1",
                     "Host":host, "Origin":request_origin}), timeout=3)
    try:
        response = login("study.example.org", origin, "participant", code)
        assert "; Secure" in response.headers["Set-Cookie"]
        local_host = base.split("//")[1]
        response = login(local_host, base, "admin", (study.directory/"admin-token.txt").read_text().strip())
        assert "; Secure" not in response.headers["Set-Cookie"]
        catalog = json.load(opener.open(base+"/api/admin/catalog"))
        assert catalog["participant_origin"] == origin
        with pytest.raises(HTTPError) as exc:
            login("study.example.org", base, "participant", code)
        assert exc.value.code == 403
        with pytest.raises(HTTPError) as exc:
            login("attacker.example.org", origin, "participant", code)
        assert exc.value.code == 403
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def test_remote_login_rate_limit_is_scoped_to_validated_client_address(study):
    _, code = participant(study)
    origin = "https://study.example.org"
    server = create_server(study, port=0, public_origin=origin, trusted_proxy=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    opener = build_opener(ProxyHandler({}))
    def login(ip, value):
        return opener.open(Request(base+"/api/login",data=json.dumps({"kind":"participant","code":value}).encode(),
            headers={"Host":"study.example.org","Origin":origin,"Content-Type":"application/json",
                     "X-Study-Request":"1","X-Screenplay-Client-IP":ip}),timeout=3)
    try:
        for _ in range(10):
            with pytest.raises(HTTPError) as exc: login("203.0.113.1","invalid-invitation")
            assert exc.value.code==401
        with pytest.raises(HTTPError) as exc: login("203.0.113.1",code)
        assert exc.value.code==429
        assert json.load(login("203.0.113.2",code))["ok"] is True
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
