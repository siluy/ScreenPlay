"""Offline curriculum authoring using upstream PySolFC stack legality predicates.
Data-only native stack instances omit canvas construction, not rule methods.
This is legality/search evidence; desktop drag dispatch requires separate validation.
"""
from pathlib import Path
import sys,json,random,heapq,itertools
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cache/sources/pysolfc'))
from pysollib.stack import SuperMoveAC_RowStack,ReserveStack,SS_FoundationStack
from pysollib.acard import AbstractCard
from pysollib.game import Game
from pysollib.mfxutil import Struct

game=Game.__new__(Game); game.s=NS(rows=[],reserves=[],foundations=[])
cards=[AbstractCard(i,0,i//13,i%13,game) for i in range(52)]
for c in cards:c.face_up=1
game.cards=cards
for cls,count,group in [(SuperMoveAC_RowStack,8,game.s.rows),(ReserveStack,4,game.s.reserves),(SS_FoundationStack,4,game.s.foundations)]:
 for i in range(count):
  s=cls.__new__(cls); s.game=game;s.cards=[]
  cap=dict(suit=-1,color=-1,rank=-1,base_suit=-1,base_color=-1,base_rank=-1,dir=0,mod=8192,max_move=1,max_accept=1,max_cards=999999,min_move=1,min_accept=1,min_cards=0)
  if cls is SuperMoveAC_RowStack:cap.update(dir=-1,max_move=999999,max_accept=999999)
  if cls is ReserveStack:cap.update(max_cards=1)
  if cls is SS_FoundationStack:cap.update(suit=i,base_suit=i,base_rank=0,dir=1,max_cards=13)
  s.cap=Struct(**cap);group.append(s)
stacks=game.s.rows+game.s.reserves+game.s.foundations

def load(state):
 for s,ids in zip(stacks,state):s.cards=[cards[i] for i in ids]
def successors(state):
 load(state)
 # Immediate foundation moves first, but keep alternatives: premature foundation
 # placement can remove a useful alternating-color landing card.
 for i,s in enumerate(stacks[:12]):
  for n in range(1,len(s.cards)+1):
   moving=s.cards[-n:]
   if not s.canMoveCards(moving):continue
   empty_row=empty_res=False
   for j,t in enumerate(stacks):
    if j==i:continue
    if not t.cards and j<8:
     if empty_row or (i<8 and n==len(s.cards)):continue
     empty_row=True
    if not t.cards and 8<=j<12:
     if empty_res or i>=8:continue
     empty_res=True
    if t.acceptsCards(s,moving):
     out=list(state);out[i]=state[i][:-n];out[j]=state[j]+state[i][-n:]
     yield tuple(out),(i,j,n)
def solve(start,limit=25000):
 serial=itertools.count();q=[(0,next(serial),start)];parents={start:None};cost={start:0}
 while q and len(parents)<limit:
  _,_,state=heapq.heappop(q)
  if sum(map(len,state[12:]))==52:
   moves=[]
   while parents[state] is not None:
    old,m=parents[state];moves.append(m);state=old
   return moves[::-1],len(parents)
  for nxt,m in successors(state):
   g=cost[state]+1
   if g>=cost.get(nxt,10**9):continue
   cost[nxt]=g;parents[nxt]=(state,m)
   missing=52-sum(map(len,nxt[12:]));res=sum(map(len,nxt[8:12]))
   # Weighted search for an existence witness, not an optimal policy.
   score=g+missing*8+res*.3
   heapq.heappush(q,(score,next(serial),nxt))
 return None,len(parents)

def fixture(cutoffs,lengths,reserves,seed):
 pool=[s*13+r for s in range(4) for r in range(cutoffs[s],13)]
 assert sum(lengths)+reserves==len(pool)
 random.Random(seed).shuffle(pool);out=[]
 for n in lengths+[1]*reserves+[0]*(4-reserves):out.append(tuple(pool[:n]));pool=pool[n:]
 return tuple(out+[tuple(s*13+r for r in range(cutoffs[s])) for s in range(4)])

def xy(i,length,index=None):
 if i<8:return [round(100+i*93.6),180+23*(max(0,length-1) if index is None else index)]
 if i<12:return [round(55+(i-8)*93.6),85]
 return [round(525+(i-12)*93.6),85]

path=ROOT/'game_packages/pysolfc/tasks.json';tasks=json.loads(path.read_text());tasks={k:v for k,v in tasks.items() if k in ['pysolfc-freecell-12','pysolfc-freecell-16']}
# Distinct resource envelopes / dependency structures, with unequal suit fronts.
configs=[
 ('exposed-pairs','easy',[11]*4,[2,2,2,2,0,0,0,0],0,'Four short columns and four empty columns; identify suit-front ordering.'),
 ('reserve-release','easy',[11]*4,[1,1,1,1,0,0,0,0],4,'All free cells occupied but four empty columns permit immediate reserve release.'),
 ('split-fronts','easy',[10,11,12,9],[2,1,2,1,2,2,0,0],0,'Unequal foundation fronts require comparing ranks across suits with ample workspace.'),
 ('six-columns','easy',[10]*4,[2,2,2,2,2,2,0,0],0,'Six shallow columns distribute blockers; two empty columns provide recovery space.'),
 ('one-empty-column','medium',[8]*4,[3,3,3,3,3,3,2,0],0,'Only one initial empty column; blockers across seven columns compete for temporary storage.'),
 ('half-reserves','medium',[9]*4,[3,3,2,2,2,2,0,0],2,'Two occupied free cells reduce flexible storage while longer columns hide dependencies.'),
 ('unequal-fronts','medium',[7,9,10,10],[4,3,3,2,2,2,0,0],0,'Unequal suit fronts and deeper columns require maintaining several independent rank chains.'),
 ('eight-columns','medium',[9]*4,[2]*8,0,'No empty tableau column initially; free cells must create useful workspace.'),
 ('full-reserves','hard',[8]*4,[2]*8,4,'All columns and free cells occupied; progress requires legal alternating-color joins or available foundations.'),
 ('deep-blockers','hard',[7]*4,[5,4,4,3,2,2,2,2],0,'Deep columns bury low cards beneath multiple suits; workspace must preserve several future landing cards.'),
 ('asymmetric-pressure','hard',[6,8,10,10],[4,3,3,2,2,2,1,1],0,'Highly unequal suit fronts create long prerequisite chains with no initial empty column.'),
 ('three-reserves','hard',[7,8,9,9],[3,3,3,2,2,2,1,0],3,'One free cell and one empty column force careful workspace reuse across mixed-depth dependencies.'),
 ('closed-tableau','hard',[7,7,9,9],[3,3,3,3,2,2,2,2],0,'All eight columns occupied with mixed-depth dependencies; freeing columns and moving valid sequences interact.'),
]
report={}
for num,(slug,level,cut,lens,res,rationale) in enumerate(configs):
 for attempt in range(600):
  start=fixture(cut,lens,res,200+num*100+attempt);moves,visited=solve(start)
  if moves and (slug=='reserve-release' or any(j<12 for i,j,n in moves)):
   if level=='hard' and sum(j<12 for i,j,n in moves)<5:continue
   if slug=='full-reserves' and moves[0][1]>=12:continue
   break
 else:raise RuntimeError(slug)
 state=start;actions=[];transfers=0;sequences=0
 for i,j,n in moves:
  load(state);moving=stacks[i].cards[-n:]
  assert stacks[i].canMoveCards(moving) and stacks[j].acceptsCards(stacks[i],moving)
  origin=xy(i,len(state[i]),len(state[i])-n)
  # Native screenshot: tableau top y=142; exposed overlap is 23 px.
  # Grab inside the exposed strip for a multi-card sequence, not the card body.
  if i<8 and n>1:origin[1]=152+23*(len(state[i])-n)
  actions.append({'type':'drag','from':origin,'to':xy(j,len(state[j])),'duration_ms':400})
  out=list(state);out[i]=state[i][:-n];out[j]=state[j]+state[i][-n:];state=tuple(out)
  transfers+=j<12;sequences+=n>1
 load(state);assert game.isGameWon()
 params={'foundation_counts':cut,'rows':[[[v//13,v%13] for v in s] for s in start[:8]],'reserves':[[[v//13,v%13] for v in s] for s in start[8:12]],'curriculum':{'difficulty':level,'mechanisms':['suit foundation prerequisites','alternating-color tableau','temporary storage allocation']+(['sequence transfer'] if sequences else []),'difficulty_rationale':rationale+' Author estimate, pending empirical calibration.'}}
 ident='pysolfc-freecell-'+slug
 tasks[ident]={'game':'PySolFC FreeCell','game_id':slug,'instruction':f'Finish this FreeCell position: move all {52-sum(cut)} remaining cards onto the four suit foundations.','rules':tasks['pysolfc-freecell-12']['rules']+' A descending alternating-color sequence can move together when enough free cells and empty columns are available.','max_decisions':160 if level=='hard' else 120,'time_mode':'turn_based','undo_allowed':True,'parameters':params,'reference':{'viewport':[873,641],'provenance':'Offline search using native SuperMoveAC_RowStack, ReserveStack and SS_FoundationStack predicates. Native Game.isGameWon verified; GUI dispatch unverified.','actions':actions,'stack_moves':moves}}
 report[ident]={'difficulty':level,'native_rule_replay_success':True,'native_game_won':True,'reference_actions':len(moves),'tableau_or_reserve_transfers':transfers,'sequence_transfers':sequences,'search_states':visited,'fixture_seed':200+num*100+attempt,'gui_replay_verified':False}
 print(ident,report[ident],flush=True)
for ident,level in [('pysolfc-freecell-12','easy'),('pysolfc-freecell-16','medium')]:
 cutoff=tasks[ident]['parameters']['foundation_cards']
 ranks=[11,10,12] if cutoff==10 else [11,10,9,12]
 state=tuple([tuple(s*13+r for r in ranks) for s in range(4)]+[tuple() for _ in range(8)]+[tuple(s*13+r for r in range(cutoff)) for s in range(4)])
 moves=[]
 for suit in range(4):
  moves.append((suit,8,1));moves.extend([(suit,12+suit,1)]*(len(ranks)-1));moves.append((8,12+suit,1))
 for i,j,n in moves:
  load(state);moving=stacks[i].cards[-n:]
  assert stacks[i].canMoveCards(moving) and stacks[j].acceptsCards(stacks[i],moving)
  out=list(state);out[i]=state[i][:-n];out[j]=state[j]+state[i][-n:];state=tuple(out)
 load(state);assert game.isGameWon()
 tasks[ident]['reference']['stack_moves']=moves
 report[ident]={'difficulty':level,'native_rule_replay_success':True,'native_game_won':True,'reference_actions':len(moves),'tableau_or_reserve_transfers':4,'sequence_transfers':0,'gui_replay_verified':False}
 tasks[ident]['parameters']['curriculum']={'difficulty':level,'mechanisms':['king blocker','temporary reserve','suit foundation prerequisites'],'difficulty_rationale':'Four independent suit columns have a king blocker; the longer four-card columns require tracking an extra rank dependency.'+' Author estimate, pending empirical calibration.'}
for ident,t in tasks.items():
 p=t['parameters']; r=p.get('rows',[[0]* (13-p['foundation_cards'])]*4+[[]]*4) if 'rows' not in p else p['rows']; reserves=p.get('reserves',[[]]*4)
 t['parameters']['curriculum']['difficulty_rationale']+=f' Initial empty tableau columns: {sum(not x for x in r)}; empty free cells: {sum(not x for x in reserves)}; maximum column depth: {max(map(len,r))}.'
 report[ident]['evidence_scope']='Data-only native stack instances and native legality/win predicates; not full Tk engine movement or GUI dispatch.'
assert len(tasks)==15
path.write_text(json.dumps(tasks,indent=2)+'\n')
(ROOT/'game_packages/pysolfc/authoring-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
