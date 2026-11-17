"""Private candidate GUI routes from recorded native widgets; not success claims."""
import json
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'artifacts/private-singularity-author-plans';P.mkdir(parents=True,exist_ok=True)
def c(x,y):return {'type':'click','x':x,'y':y}
base=[c(550,239),c(184,600),c(275,594),c(815,600),c(533,42),c(375,427)]
plans={'server-foothold':base,'distributed-access':base,'intrusion':[{'replay':True}],'research-chain':[{'replay':True}]}
plans['datacenter-estate']=[c(250,280),c(184,600),c(270,167),c(275,594),c(815,600),c(550,239),c(184,600),c(270,167),c(275,594),c(815,600),c(533,42),c(375,427)]
for name,actions in plans.items():(P/(name+'.jsonl')).write_text(''.join(json.dumps(x)+'\n' for x in actions+[{'save_reference':True},{'close':True}]))
