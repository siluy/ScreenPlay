"""Exercise each native text adapter through the authenticated human HTTP API.

Only validation-labelled studies are accepted. No model calls or GUI inputs.
"""
import argparse
from http.cookiejar import CookieJar
import json
from pathlib import Path
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
import uuid
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8790")
    parser.add_argument("--admin-token-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-new-text", action="store_true", help="Check all 45 newly supported native text tasks")
    args = parser.parse_args()
    def client():
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        def call(path, body=None):
            request = Request(args.url.rstrip("/")+path,
                              data=json.dumps(body).encode() if body is not None else None,
                              headers={"Content-Type": "application/json", "X-Study-Request": "1",
                                       "Accept": "application/json",
                                       "User-Agent": "Mozilla/5.0 (compatible; ScreenPlayValidation/0.2)"})
            return json.load(opener.open(request, timeout=55))
        return call
    admin = client()
    admin("/api/login", {"kind": "admin", "code": args.admin_token_file.read_text().strip()})
    assert admin("/api/admin/overview")["protocol"]["actor"] == "validation", "Refusing to add test records to a human study"
    catalog = admin("/api/admin/catalog")
    assert sum(t["text_supported"] for t in catalog["tasks"]) == 90
    presets = {p["id"]: p for p in catalog["invitation_presets"]}
    assert len(presets["new_text45"]["task_ids"]) == 45
    task_info = {t["task_id"]: t for t in catalog["tasks"]}
    tasks = presets["new_text45"]["task_ids"] if args.all_new_text else [
        "fifteen-01", "net-3x3", "untangle-6", "pysolfc-freecell-12", "endless-sky-clear-hold",
        "singularity-intrusion", "openttd-dispatch", "enigma-oxyd-pair"]
    results = []
    for task in tasks:
        invitation = admin("/api/admin/invitations", {"alias": "QA_"+uuid.uuid4().hex[:12],
                           "task_ids": [task], "condition": "text", "seed": 0})
        human = client()
        human("/api/login", {"kind": "participant", "code": invitation["invitation_code"]})
        human("/api/consent", {"accepted": True})
        attempt = human("/api/attempts", {})
        assert attempt["observation"]["board_text"] and not attempt["observation"]["ended"]
        assert attempt["observation"]["budget_remaining"] == task_info[task]["text_max_decisions"]
        public = json.dumps(attempt)
        assert all(x not in public for x in ['"serialized"', '"expected_desc"', '"reference"', '"native_fixture"'])
        action = {"type": "wait"}
        if task_info[task]["package"] in {"endless_sky", "singularity", "openttd", "enigma"}:
            action["duration_ms"] = 0
        if task == "singularity-intrusion":
            control = re.search(r"\[(u\d+_\d+)\] button: RESEARCH/TASKS", attempt["observation"]["board_text"])[1]
            action = {"type": "click", "control": control}
        elif task == "openttd-dispatch":
            action = {"type": "open_panel", "panel": "orders"}
        elif task == "enigma-oxyd-pair":
            action = {"type": "push", "dx": 10, "dy": 0}
        request = {"request_id": uuid.uuid4().hex, "observation_id": 0, "action": action}
        path = f"/api/attempts/{attempt['attempt_id']}/actions"
        reply = human(path, request)
        duplicate = human(path, request)
        assert reply["observation"] == duplicate["observation"]
        assert reply["observation"]["receipt"]["status"] == "executed"
        assert reply["observation"]["decision_index"] == 1
        end = human(path, {"request_id": uuid.uuid4().hex, "observation_id": 1, "action": {"type": "finish"}})
        assert end["observation"]["result"]["success"] is False
        assert end["observation"]["result"]["stop_reason"] == "agent_finished"
        results.append({"task": task, "image_free": True, "native_action_executed": action,
                        "initial_decision_budget": attempt["observation"]["budget_remaining"],
                        "duplicate_not_replayed": True, "unsolved_finish_not_success": True})
        print(json.dumps(results[-1]), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"passed": True, "validation_only": True,
                                      "model_requests": 0, "gui_inputs": 0, "checks": results}, indent=2)+"\n")


if __name__ == "__main__":
    main()
