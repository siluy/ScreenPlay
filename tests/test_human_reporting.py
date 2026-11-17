import csv
import io
import json
import sqlite3

import pytest

from gameworld.tasks import catalog
from screenplay_human.reporting import build_report
from screenplay_human.server import results_csv, summary_csv
from screenplay_human.study import Study
from test_human_study import Runtime, participant, payload


def fixture_report():
    people = [{"id":pid,"alias":pid,"withdrawn":None,"assignment":[
        {"task_id":"fifteen-01","condition":"gui"},{"task_id":"net-3x3","condition":"text"}]}
        for pid in ("A","B")]
    def attempt(aid,pid,index,success,seconds,steps,status="scored"):
        return {"id":aid,"participant_id":pid,"task_index":index,"status":status,
                "result":{"success":success,"decisions":steps},"decisions":steps,
                "elapsed_seconds":seconds,"elapsed_source":"monotonic","started":None,"finished":None,"app_version":"0.2.2"}
    attempts=[attempt("interrupted","A",0,None,100,99,"interrupted"),
              attempt("a","A",0,True,12,3),attempt("b","A",1,False,30,8),
              attempt("c","B",0,True,None,5)]
    return people, attempts, build_report(people,attempts,catalog())


def test_weighting_missingness_and_recovery_do_not_distort_means():
    people, attempts, report=fixture_report()
    m=report["views"][0]["overall"]
    assert len(report["rows"])==4
    assert (m["assigned_count"],m["scored_count"],m["correct_count"],m["not_started_count"])==(4,3,2,1)
    assert m["accuracy"]==pytest.approx(2/3)
    assert m["mean_elapsed_seconds"]==21 and m["elapsed_n"]==2 and m["elapsed_missing_n"]==1
    assert m["mean_decisions"]==pytest.approx(16/3)
    assert m["mean_success_elapsed_seconds"]==12 and m["success_elapsed_n"]==1
    assert m["mean_success_decisions"]==4
    assert m["interrupted_attempt_count"]==1
    assert next(v for v in report["views"] if v["participant_id"]=="A" and v["condition"]=="text")["overall"]["accuracy"]==0
    assert {r["label"] for r in report["views"][0]["by_game"]}=={"Fifteen","Net"}
    assert len(report["views"][0]["by_project"])==1
    assert report["views"][0]["by_difficulty"]
    assert report["views"][0]["by_project_difficulty"]
    data={"report":report}
    rows=list(csv.DictReader(io.StringIO(results_csv(data).lstrip('\ufeff'))))
    assert [r["correct"] for r in rows]==['1','0','1','']
    totals=next(r for r in csv.DictReader(io.StringIO(summary_csv(data).lstrip('\ufeff'))) if r['participant_scope']=='ALL' and r['condition']=='all' and r['group_type']=='overall')
    assert float(totals['mean_elapsed_seconds'])==21 and int(totals['scored_count'])==3


def test_empty_groups_have_null_means_and_real_zero_is_not_missing():
    empty=build_report([],[],catalog())["views"][0]["overall"]
    assert empty["accuracy"] is None and empty["mean_elapsed_seconds"] is None
    people,attempts,_=fixture_report()
    attempts[1].update(elapsed_seconds=0,decisions=0)
    report=build_report(people[:1],attempts[:2],catalog())
    m=report["views"][0]["overall"]
    assert m['mean_elapsed_seconds']==0 and m['mean_decisions']==0
    assert m['elapsed_n']==m['decisions_n']==1


def test_monotonic_duration_excludes_cleanup_and_duplicate_delivery(tmp_path, monkeypatch):
    clock=[100.0]
    monkeypatch.setattr('screenplay_human.study.time.monotonic',lambda:clock[0])
    class SlowCleanup(Runtime):
        def close(self):
            clock[0]+=100
            super().close()
    s=Study(tmp_path/'study',runtime_factory=SlowCleanup)
    try:
        pid,_=participant(s)
        a=s.start(pid)
        clock[0]=112.25
        request=payload(action={"type":"finish"})
        s.action(pid,a['attempt_id'],request)
        s.action(pid,a['attempt_id'],request)
        exported=s.export()
        row=exported['report']['rows'][0]
        assert row['elapsed_seconds']==12.25 and row['elapsed_source']=='monotonic'
        assert row['decisions']==1
        assert exported['report']['views'][0]['overall']['scored_count']==1
    finally:s.close()


def test_legacy_upgrade_preserves_invitation_results_and_marks_estimated_time(tmp_path):
    directory=tmp_path/'legacy'
    s=Study(directory,runtime_factory=Runtime)
    pid,code=participant(s)
    a=s.start(pid);s.action(pid,a['attempt_id'],payload(action={'type':'finish'}));s.close()
    with sqlite3.connect(directory/'study.sqlite3') as db:
        protocol=json.loads(db.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0]);protocol['version']='0.2.1'
        db.execute("UPDATE meta SET value=? WHERE key='config'",(json.dumps(protocol),))
        db.execute("UPDATE attempts SET started='2026-10-28T00:00:00+00:00',finished='2026-10-28T00:00:10+00:00'")
        original=db.execute('SELECT result FROM attempts').fetchone()[0]
        for column in ['elapsed_seconds','elapsed_source','app_version']:db.execute('ALTER TABLE attempts DROP COLUMN '+column)
    s=Study(directory,runtime_factory=Runtime)
    try:
        assert s.identity(s.login('participant',code))['participant_id']==pid
        assert s.config['version']=='0.2.1'
        assert s.db.execute('SELECT result FROM attempts').fetchone()[0]==original
        assert len(list(directory.glob('study-before-statistics-*.sqlite3')))==1
        row=s.export()['report']['rows'][0]
        assert row['elapsed_seconds']==10 and row['elapsed_source']=='legacy_wall_clock_estimate'
        assert s.export()['report']['views'][0]['overall']['estimated_elapsed_n']==1
    finally:s.close()
