"""Sequential private author attempts; one Episode/process owns the desktop at a time."""
import subprocess,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
plans=ROOT/'artifacts/private-enigma-author-plans'
for name in sys.argv[1:]:
    output=ROOT/'runs/v1-acceptance'/('enigma-'+name+'-author-batch')
    with (plans/(name+'.jsonl')).open() as source,(plans/(name+'-batch.log')).open('w') as log:
        result=subprocess.run([sys.executable,'-u',str(ROOT/'scripts/author_singularity_enigma_gui.py'),'enigma-'+name,str(output)],stdin=source,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
    saved=output/'result.json'
    print(json.dumps({'task':name,'exit_code':result.returncode,'result':json.loads(saved.read_text()) if saved.exists() else {'success':False,'reason':'author attempt incomplete'}}),flush=True)
