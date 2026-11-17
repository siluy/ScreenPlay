import json
import uuid
import threading
from http.cookiejar import CookieJar
from urllib.request import build_opener, ProxyHandler, HTTPCookieProcessor, Request

import pytest

from screenplay_human.study import Study, StudyError
from screenplay_human.server import create_server
from test_human_study import Runtime, participant, payload


def control(s,pid,kind,*,accepted=False):
    state=s.state(pid);current=state['active'] or state['paused_attempt']
    request={'request_id':uuid.uuid4().hex,'attempt_id':current['attempt_id'] if current else None,
             'revision':state['participant']['control_revision'],'accepted':accepted}
    return s.participation(pid,kind,request),request


def test_pause_keeps_same_board_steps_and_budget_and_excludes_break(tmp_path,monkeypatch):
    clock=[100.0];monkeypatch.setattr('screenplay_human.study.time.monotonic',lambda:clock[0])
    s=Study(tmp_path/'study',runtime_factory=Runtime,wall_seconds=60)
    try:
        pid,code=participant(s);a=s.start(pid)
        before=s.action(pid,a['attempt_id'],payload())['observation']
        clock[0]=105.0;paused,pause_request=control(s,pid,'pause')
        assert paused['active'] is None and paused['paused_attempt']['remaining_seconds']==55
        assert paused['participant']['paused'] and not paused['participant']['withdrawn']
        assert Runtime.instances[-1].moves==1 and not Runtime.instances[-1].closed
        clock[0]=1000.0
        assert s.state(pid)['paused_attempt'] and s.export()['attempts'][0]['elapsed_seconds']==5
        assert s.identity(s.login('participant',code))['participant_id']==pid
        with pytest.raises(StudyError,match='attempt_paused'):s.action(pid,a['attempt_id'],payload(obs=1,rid='while-paused'))
        resumed,resume_request=control(s,pid,'resume')
        assert resumed['active']['attempt_id']==a['attempt_id'] and resumed['active']['observation']==before
        deadline=s.live[a['attempt_id']].deadline
        s.participation(pid,'pause',pause_request)  # A late retry cannot pause a resumed task.
        s.participation(pid,'resume',resume_request)
        assert s.state(pid)['active'] and s.live[a['attempt_id']].deadline==deadline
        clock[0]=1006
        s.action(pid,a['attempt_id'],payload(obs=1,rid='finish',action={'type':'finish'}))
        row=s.export()['report']['rows'][0]
        assert row['decisions']==2 and row['elapsed_seconds']==11 and row['paused_seconds']==895
        assert row['wall_elapsed_seconds']==906 and row['pause_count']==1
        assert row['elapsed_source']=='monotonic_excluding_pauses'
    finally:s.close()


def test_between_task_break_and_rejoin_keep_formal_results(tmp_path):
    s=Study(tmp_path/'study',runtime_factory=Runtime)
    try:
        invite=s.invite('P1',['fifteen-01','net-3x3'],'text');pid=invite['participant_id'];s.consent(pid)
        a=s.start(pid);s.action(pid,a['attempt_id'],payload(action={'type':'finish'}))
        original=s.db.execute('SELECT result FROM attempts WHERE id=?',(a['attempt_id'],)).fetchone()[0]
        control(s,pid,'pause');assert s.state(pid)['participant']['completed']==1
        assert not s.live
        with pytest.raises(StudyError,match='participant_paused'):s.start(pid)
        control(s,pid,'resume');control(s,pid,'withdraw',accepted=True)
        with pytest.raises(StudyError,match='rejoin_consent_required'):control(s,pid,'resume')
        result,_=control(s,pid,'resume',accepted=True)
        assert not result['participant']['withdrawn'] and result['participant']['completed']==1
        b=s.start(pid);assert b['attempt_id']!=a['attempt_id']
        assert s.db.execute('SELECT task_index FROM attempts WHERE id=?',(b['attempt_id'],)).fetchone()[0]==1
        assert s.db.execute('SELECT result FROM attempts WHERE id=?',(a['attempt_id'],)).fetchone()[0]==original
        event=next(e for e in s.export()['participation_events'] if e['event']=='rejoined')
        assert event['details']['previous_withdrawn_at']
    finally:s.close()


def test_pause_reserves_desktop_and_stale_controls_cannot_override_choice(tmp_path):
    s=Study(tmp_path/'study',runtime_factory=Runtime)
    try:
        pid,_=participant(s,'P1','gui');other,_=participant(s,'P2','gui')
        a=s.start(pid);control(s,pid,'pause')
        with pytest.raises(StudyError,match='desktop_busy'):s.start(other)
        with pytest.raises(StudyError,match='participation_state_changed'):
            s.participation(other,'resume',{'request_id':'other','attempt_id':a['attempt_id'],'revision':0})
        old_revision=s.state(pid)['participant']['control_revision']
        control(s,pid,'resume');control(s,pid,'withdraw',accepted=True)
        with pytest.raises(StudyError,match='participation_state_changed'):
            s.participation(pid,'resume',{'request_id':'late','attempt_id':None,'revision':old_revision,'accepted':True})
        assert s.state(pid)['participant']['withdrawn']
        s.start(other)
    finally:s.close()


def test_restart_retains_break_and_does_not_claim_board_was_restored(tmp_path):
    s=Study(tmp_path/'study',runtime_factory=Runtime)
    pid,_=participant(s);a=s.start(pid);control(s,pid,'pause');s.close()
    s=Study(tmp_path/'study',runtime_factory=Runtime)
    try:
        state=s.state(pid)
        assert state['participant']['paused'] and state['paused_attempt'] is None
        assert state['attempts'][0]['result']['success'] is None
        control(s,pid,'resume')
        b=s.start(pid);assert b['attempt_id']!=a['attempt_id']
    finally:s.close()


def test_timeout_uses_remaining_active_time_after_break(tmp_path,monkeypatch):
    clock=[100.0];monkeypatch.setattr('screenplay_human.study.time.monotonic',lambda:clock[0])
    s=Study(tmp_path/'study',runtime_factory=Runtime,wall_seconds=60)
    try:
        pid,_=participant(s);s.start(pid)
        clock[0]=105;control(s,pid,'pause');clock[0]=1000;control(s,pid,'resume')
        clock[0]=1056;state=s.state(pid)
        assert state['attempts'][0]['result']['stop_reason']=='wall_budget_exhausted'
        assert s.export()['report']['rows'][0]['elapsed_seconds']==60
    finally:s.close()


def test_old_exit_request_becomes_break_and_can_resume(tmp_path):
    s=Study(tmp_path/'study',runtime_factory=Runtime)
    pid,code=participant(s);a=s.start(pid)
    server=create_server(s,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    def post(path,body):
        return json.load(opener.open(Request(f'http://127.0.0.1:{server.server_address[1]}'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Study-Request':'1'}),timeout=3))
    try:
        post('/api/login',{'kind':'participant','code':code})
        state=post('/api/withdraw',{})
        assert state['participant']['paused'] and not state['participant']['withdrawn']
        state=post('/api/resume',{'request_id':'resume','attempt_id':a['attempt_id'],'revision':state['participant']['control_revision']})
        assert state['active']['attempt_id']==a['attempt_id']
    finally:server.shutdown();server.server_close();thread.join(timeout=2);s.close()
