"""Two independent static-reference interface checks; no feedback action choice."""
import json
from pathlib import Path
from screenplay.experiments import run_one
from screenplay.runner import write_json
ROOT=Path(__file__).resolve().parents[1]
for task in ['enigma-keys-and-causeway','singularity-undersea-research']:
    report=run_one(task,reference=True,output=ROOT/'runs/v1-acceptance'/(task+'-replay'))
    path=ROOT/'artifacts/v1-singularity-enigma-desktop.json'
    rows=json.loads(path.read_text())
    rows.append({'task_id':task,'directory':str(Path(report['directory']).relative_to(ROOT)),
                 'result':report['result'],'verification_kind':'static_reference_replay',
                 'expected_success':True,'passed':bool(report['result']['success']),
                 'native_telemetry_for_author_planning':False})
    write_json(path,rows)
    print(json.dumps(report),flush=True)
