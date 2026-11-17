"""Protocol invariants using a tiny test double; these are not GUI validations."""
import base64
import json
from dataclasses import replace
from PIL import Image
import pytest
from pydantic import ValidationError
from gameworld.protocol import validate_action
from gameworld.runner import Episode, ProtocolError
from gameworld.tasks import Task, parse_save, evaluate


def save(desc="fixture", solved_move=False):
    rows = [("SAVEFILE","Simon Tatham's Portable Puzzle Collection"), ("GAME","Fifteen"),
            ("DESC",desc), ("STATEPOS","1")]
    if solved_move: rows.append(("SOLVE","solution"))
    return "".join(f"{k:<8}:{len(v)}:{v}\n" for k,v in rows)


class Backend:
    def __init__(self):
        self.initial_desc="fixture"
        self.executed=[]
        self.solved=False
        self.raise_after_input=False
    def start(self,*args): pass
    def capture(self):
        return Image.new("RGB",(100,80)),{"serialized":save(),"status":int(self.solved)}
    def execute(self,action):
        self.executed.append(action)
        if self.raise_after_input: raise RuntimeError("input already happened; private diagnostic")
    def close(self): pass


@pytest.fixture
def episode(tmp_path):
    backend=Backend()
    task=Task("test","Fifteen","private-game-id","Solve the puzzle","rules",3)
    episode=Episode(task,tmp_path/"episode",backend)
    episode.start()
    yield episode
    episode.close()


def request(e, action=None, action_id="one", obs=None):
    return {"episode_id":e.id,"action_id":action_id,
            "based_on_observation_id":e.observation_id if obs is None else obs,
            "action":action or {"type":"click","x":10,"y":10}}


def test_public_observation_has_no_privileged_state(episode):
    response=episode.last_response
    public=json.dumps(response)
    assert all(secret not in public for secret in ["serialized","private-game-id","fixture","state_position"])
    assert "result" not in response
    assert base64.b64decode(response["image"]["base64"]).startswith(b"\x89PNG")


def test_duplicate_action_executes_once_even_after_finish(episode):
    episode.backend.solved=True
    payload=request(episode)
    first=episode.act(payload)
    assert first["ended"]
    assert episode.act(payload)==first
    assert len(episode.backend.executed)==1
    assert episode.steps==1


def test_reused_id_with_changed_payload_is_rejected(episode):
    payload=request(episode)
    episode.act(payload)
    payload["action"]["x"]=11
    with pytest.raises(ProtocolError,match="payload_conflict"): episode.act(payload)
    assert len(episode.backend.executed)==1


def test_stale_observation_does_not_send_input(episode):
    episode.act(request(episode))
    with pytest.raises(ProtocolError,match="stale_observation"):
        episode.act(request(episode,action_id="two",obs=0))
    assert len(episode.backend.executed)==1


def test_invalid_action_consumes_budget_without_executing(episode):
    for i in range(3):
        response=episode.act(request(episode,{"type":"click","x":100,"y":0},str(i)))
        assert response["receipt"]["status"]=="rejected"
    assert response["ended"]
    assert response["result"]["stop_reason"]=="decision_budget_exhausted"
    assert not episode.backend.executed


def test_uncertain_execution_cannot_be_retried_as_a_second_click(episode):
    episode.backend.raise_after_input=True
    payload=request(episode)
    result=episode.act(payload)
    assert result["result"]["score"] is None
    assert "private diagnostic" not in json.dumps(result)
    assert episode.act(payload)==result
    assert len(episode.backend.executed)==1


def test_finish_is_not_success(episode):
    result=episode.act(request(episode,{"type":"finish"}))
    assert result["ended"] and not result["result"]["success"]
    assert not episode.backend.executed


@pytest.mark.parametrize("payload",[
    {"type":"exec","code":"import os"},
    {"type":"key_press","key":"command"},
    {"type":"click","x":True,"y":0},
    {"type":"click","x":0,"y":0,"command":"payload"},
    {"type":"wait","duration_ms":5001},
])
def test_non_gui_or_unbounded_payloads_rejected(payload):
    with pytest.raises((ValueError,ValidationError)): validate_action(payload,100,100)


def test_native_save_parsing_respects_lengths():
    s=save(desc="one:two\nthree")
    assert dict(parse_save(s))["DESC"]=="one:two\nthree"
    with pytest.raises(ValueError): parse_save(s[:-5])


def test_solver_and_wrong_initial_state_cannot_receive_success():
    assert not evaluate({"serialized":save(solved_move=True),"status":1},"fixture","Fifteen")["success"]
    assert not evaluate({"serialized":save("other"),"status":1},"fixture","Fifteen")["success"]


def test_http_authentication_and_agent_client(episode):
    import threading
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from gameworld.client import GameWorldClient
    from gameworld.server import create_server
    server=create_server(episode,"test-token",port=0)
    thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True)
    thread.start()
    base=f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with pytest.raises(HTTPError) as error: urlopen(base+"/v1/observation",timeout=2)
        assert error.value.code==401
        client=GameWorldClient(base,"test-token")
        observation=client.observe()
        payload=client.prepare_action(observation,{"type":"click","x":10,"y":20})
        result=client.send_action(payload)
        assert result["decision_index"]==1
        assert client.send_action(payload)==result
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base+"/private/task.json",headers={"Authorization":"Bearer test-token"}),timeout=2)
        assert error.value.code==404
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
