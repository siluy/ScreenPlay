"""Private fixture-author desktop recorder (not an autonomous agent policy).
Start only while holding the team's exclusive desktop slot. JSON lines are low-level
protocol actions, or {"replay":true}, or {"close":true}. Successful sequences may be
saved via {"save_reference":true}; this never edits engine state or invokes semantic
engine commands. Every input passes Episode validation and PyAutoGUI.
"""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from gameworld.runner import Episode, write_json
from gameworld.tasks import load_task,catalog
from gameworld.replay import export_replay
name=sys.argv[1]
output=Path(sys.argv[2]) if len(sys.argv)>2 and not sys.argv[2].startswith('--') else ROOT/'runs/v1-acceptance'/f'{name}-author'
output.parent.mkdir(parents=True,exist_ok=True)
ep=Episode(load_task(name),output=output); actions=[]
(ep.directory/'agent_provenance.json').write_text(json.dumps(dict(type='fixture-author',autonomous_model=False)))
def show():
    print(json.dumps(dict(run=str(ep.directory),frame=str(ep.directory/'frames'/f'{ep.observation_id:06d}.png'),state=ep.backend.state(),score=ep.last_score,ended=ep.ended)),flush=True)
def act(action):
    response=ep.act(dict(episode_id=ep.id,action_id=f'author-{len(actions)}',based_on_observation_id=ep.observation_id,action=action))
    actions.append(action)
    show()
try:
    ep.start();show()
    lines=['{"replay":true}','{"save_reference":true}','{"close":true}'] if '--replay' in sys.argv else sys.stdin
    for line in lines:
        value=json.loads(line)
        if value.get('close'):break
        if value.get('save_reference'):
            if not ep.last_score['success']:raise RuntimeError('Cannot promote a failed trace')
            path=ROOT/'game_packages'/ep.task.package/'tasks.json'; data=json.loads(path.read_text())
            data[name]['reference']=dict(provenance='Fixture-author PyAutoGUI desktop replay; not an autonomous model rollout.',viewport=[ep.width,ep.height],actions=actions,verified_run=str(ep.directory.relative_to(ROOT)))
            write_json(path,data);print('reference saved',flush=True)
        elif value.get('actions'):
            for action in value['actions']:
                if ep.ended:break
                act(action)
        elif value.get('replay'):
            for action in catalog()[name]['reference']['actions']:
                if ep.ended:break
                act(action)
        else:act(value)
finally:
    ep.close()
    export_replay(ep.directory)
    summary=ROOT/'artifacts/v1-transport-desktop.json'
    rows=json.loads(summary.read_text()) if summary.exists() else []
    result=json.loads((ep.directory/'result.json').read_text()) if (ep.directory/'result.json').exists() else dict(success=False,stop_reason='author_closed_unfinished')
    rows.append(dict(task_id=name,directory=str(ep.directory.relative_to(ROOT)),result=result,verification_kind='fixture-author PyAutoGUI desktop'))
    summary.parent.mkdir(parents=True,exist_ok=True)
    summary.write_text(json.dumps(rows,indent=2)+'\n')
