"""Private human-authored candidate commands; not successful-reference claims."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'artifacts/private-enigma-author-plans';out.mkdir(parents=True,exist_ok=True)
def nav(x,y,opened='',mode='lawn'):return {'navigate':[x+.5,y+.5],'opened':list(opened),'mode':mode}
def go(x,y,mode='lawn'):return {'goto':[x+.5,y+.5],'mode':mode,'tolerance':.10}
plans={
'switch-gate':[nav(2,3),nav(6,3),nav(17,9,'D')],
'crate-passage':[nav(2,3),nav(9,6),go(13,6),go(13,8),nav(17,9,'B')],
'ice-crossing':[nav(2,6),nav(17,6,mode='ice')],
'winding-memory':[nav(2,10),nav(17,2),nav(9,2),nav(16,10)],
'water-causeway':[nav(2,3),nav(17,9),nav(3,10),nav(16,2)],
'sequential-gates':[nav(2,10),nav(3,2),nav(10,10,'D'),nav(17,2,'DE')],
'friction-slalom':[nav(2,2),nav(17,10,mode='ice'),nav(2,10,mode='ice'),nav(17,2,mode='ice')],
'key-switch-cascade':[nav(2,10),nav(2,8),nav(5,3),nav(10,2,'D'),nav(17,2,'DE'),nav(3,2,'DE'),nav(16,10,'DE')],
'crate-labyrinth':[nav(2,2),nav(6,4),go(10,4),go(10,8),go(16,8),go(16,10),nav(17,10,'B'),nav(3,5,'B'),nav(16,2,'B')],
'icy-causeway':[nav(2,2),nav(5,6),go(14,6,'ice'),nav(17,10),nav(14,6),go(5,6,'ice'),nav(2,10),nav(5,6),go(14,6,'ice'),nav(17,2)],
'gated-memory':[nav(5,3),nav(10,6,'D'),nav(2,2,'DE'),nav(10,10,'DE'),nav(2,10,'DE'),nav(16,2,'DE'),nav(5,9,'DE'),nav(17,10,'DE'),nav(9,3,'DE'),nav(16,6,'DE')],
'keys-and-causeway':[nav(2,2),nav(2,8),nav(5,3),nav(10,2,'D'),nav(11,9,'D'),nav(17,10,'DE'),nav(3,10,'DE'),nav(17,2,'DE')],
}
for ident,commands in plans.items():
 (out/(ident+'.jsonl')).write_text(''.join(json.dumps(c)+'\n' for c in commands+[{'save_reference':True},{'close':True}]))
print('Prepared',len(plans),'candidate author routes; execution not implied')
