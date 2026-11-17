"""Sequential private author attempts; one Episode/process owns the desktop at a time."""
import subprocess,sys,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
plans=ROOT/'artifacts/private-singularity-author-plans'
suffix=os.environ.get('SINGULARITY_AUTHOR_SUFFIX','-author-batch')
for name in sys.argv[1:]:
    output=ROOT/'runs/v1-acceptance'/('singularity-'+name+suffix)
    with (plans/(name+'.jsonl')).open() as source,(plans/(name+suffix+'.log')).open('w') as log:
        result=subprocess.run([sys.executable,'-u',str(ROOT/'scripts/author_singularity_enigma_gui.py'),'singularity-'+name,str(output)],stdin=source,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
    saved=output/'result.json'
    print(json.dumps({'task':name,'exit_code':result.returncode,'result':json.loads(saved.read_text()) if saved.exists() else {'success':False,'reason':'author attempt incomplete'}}),flush=True)
