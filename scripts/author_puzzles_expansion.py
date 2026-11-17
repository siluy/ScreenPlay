"""Offline authoring: native solver only supplies private reference, never agent input."""
import json, math, random, re, subprocess
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'game_packages/tatham/tasks.json'
tasks=json.loads(p.read_text())
engine=ROOT/'build/tatham/bin/screenplay-engine'
def run(t, commands):
 return subprocess.run([str(engine),t['game'],t['game_id']],input=commands,text=True,capture_output=True,check=True).stdout
def field(s,k):
 return re.search(r'^'+k+r'\s*:\d+:(.*)$',s,re.M)[1]
for ident,w,h,steps,seed in [('fifteen-2x3',2,3,6,91),('fifteen-4x3',4,3,20,92),('fifteen-4x4',4,4,38,93)]:
 b=list(range(1,w*h))+[0]; gap=w*h-1; prev=None; undo=[]; rng=random.Random(seed)
 for _ in range(steps):
  options=[i for i in range(w*h) if abs(i%w-gap%w)+abs(i//w-gap//w)==1 and i!=prev]
  target=rng.choice(options); undo.append(gap); b[target],b[gap]=b[gap],b[target]; prev,gap=gap,target
 desc=','.join(map(str,b)); t=dict(tasks['fifteen-01']); t.update(game_id=f'{w}x{h}:{desc}',expected_desc=desc,reference={'actions':[{'type':'click','x':48+(i%w)*48,'y':48+(i//w)*48} for i in reversed(undo)]}); tasks[ident]=t
for ident,base,gid in [('net-barriers','net-3x3','4x3b0.7#51'),('net-wrapping','net-5x5','5x5w#52'),('untangle-20','untangle-15','20#53')]:
 t=dict(tasks[base]); t.update(game_id=gid); t.pop('expected_desc',None); tasks[ident]=t
 if 'wrapping' in ident: t['rules']+=' Wires can connect across opposite board edges on this wrapping board.'
 if 'barriers' in ident: t['rules']+=' Marked barriers block connections between adjacent cells.'
levels={'easy':['fifteen-01','net-3x3','untangle-6','fifteen-2x3','net-barriers'],'medium':['fifteen-12','net-5x5','untangle-10','fifteen-4x3','net-wrapping'],'hard':['fifteen-24','net-7x7','untangle-15','fifteen-4x4','untangle-20']}
def distance_small(desc,w,h):
 start=tuple(map(int,desc.split(',')));goal=tuple(list(range(1,w*h))+[0])
 q=deque([(goal,0)]);seen={goal}
 while q:
  b,d=q.popleft()
  if b==start:return d
  gap=b.index(0)
  # Native Fifteen permits an entire aligned run to slide in one click.
  for target in range(w*h):
   if target==gap or (target//w!=gap//w and target%w!=gap%w):continue
   step=(1 if target>gap else -1)*(w if target%w==gap%w else 1)
   new=list(b)
   for pos in range(gap,target,step):new[pos]=new[pos+step]
   new[target]=0;new=tuple(new)
   if new not in seen:seen.add(new);q.append((new,d+1))
report={}
for level, ids in levels.items():
 for ident in ids:
  t=tasks[ident]; out=run(t,'solve\nsave\n'); t['expected_desc']=field(out,'DESC')
  size=list(map(int,re.search(r'SIZE (\d+) (\d+)',out).groups()))
  actions=t.get('reference',{}).get('actions') if t['game']=='Fifteen' else []
  if t['game']=='Net':
   for op,x,y in re.findall(r'([ACF])(\d+),(\d+)',field(out,'SOLVE')):
    for _ in range(2 if op=='F' else 1): actions.append({'type':'click','x':32+32*int(x),'y':32+32*int(y),'button':'right' if op=='C' else 'left'})
  if t['game']=='Untangle':
   n=int(t['game_id'].split('#')[0]); width=size[0]
   for idx,x,y,d in re.findall(r'P(\d+):(\d+),(\d+)/(\d+)',field(out,'SOLVE')):
    i=int(idx); angle=i*2*math.pi/n; radius=(width*3)//7
    origin=[int(width/2+radius*math.sin(angle)+.5),int(width/2-radius*math.cos(angle)+.5)]
    actions.append({'type':'drag','from':origin,'to':[int(x)*64//int(d),int(y)*64//int(d)],'duration_ms':400})
  if t['game']=='Untangle':
   pending=actions[:]; actions=[]
   while pending:
    choice=next((a for a in pending if all(a is b or math.dist(a['to'],b['from'])>14 for b in pending)),None)
    assert choice is not None, 'Need temporary staging for circular target dependency'
    actions.append(choice); pending.remove(choice)
  commands=[]
  for a in actions:
   if a['type']=='click': commands.append(f"input {a['x']} {a['y']} {514 if a.get('button')=='right' else 512}")
   else:
    x,y=a['from']; tx,ty=a['to']; commands.extend([f'input {x} {y} 512',f'input {tx} {ty} 515',f'input {tx} {ty} 518'])
  verified=run(t,'\n'.join(commands)+'\nstatus\n').strip().endswith('STATUS 1')
  assert verified,(ident,run(t,'\n'.join(commands)+'\nsave\n'))
  mechanics={'Fifteen':['gap routing','ordered tile placement'],'Net':['local connectivity','global network consistency'],'Untangle':['edge crossing detection','planar spatial rearrangement']}[t['game']]
  if ident=='net-wrapping': mechanics+=['toroidal boundary connections']
  if ident=='net-barriers': mechanics+=['fixed edge barriers']
  if t['game']=='Fifteen':
   w,h=map(int,t['game_id'].split(':')[0].split('x'));board=list(map(int,t['expected_desc'].split(',')))
   misplaced=sum(v!=i+1 for i,v in enumerate(board) if v)
   manhattan=sum(abs(i//w-(v-1)//w)+abs(i%w-(v-1)%w) for i,v in enumerate(board) if v)
   optimum=distance_small(t['expected_desc'],w,h) if w*h<=9 else None
   rationale=f'{w} by {h} layout; {misplaced} misplaced tiles and total tile Manhattan distance {manhattan}. '+(f'Exact shortest native multi-tile-click solution: {optimum} moves. ' if optimum is not None else 'Exact optimum not computed. ')+('Narrow two-column geometry constrains routes around settled tiles.' if w==2 else 'Gap routing must restore row and column ordering without displacing already settled tiles.')
  elif t['game']=='Net':
   dims=t['game_id'].split('#')[0];rationale=f'Board parameters {dims}; '+('fixed barriers eliminate otherwise plausible joins on the rectangular board.' if ident=='net-barriers' else 'opposite edges join, so local edge termination heuristics no longer apply and long-range consistency matters.' if ident=='net-wrapping' else f'{int(dims.split("x")[0])**2} tiles require reciprocal local joins and one connected global network; larger boards contain more interacting branches.')
  else:
   n=int(t['game_id'].split('#')[0]);edges=t['expected_desc'].split(',');degrees=[0]*n
   for e in edges:
    a,b=map(int,e.split('-'));degrees[a]+=1;degrees[b]+=1
   rationale=f'{n} nodes, {len(edges)} edges, maximum node degree {max(degrees)}; moving high-degree nodes changes several crossing relationships simultaneously. Spatial working-memory load grows with the number of edges that must remain uncrossed.'

  t['parameters']={'curriculum':{'difficulty':level,'mechanisms':mechanics,'difficulty_rationale':rationale+' Author estimate; not empirically calibrated.'}}
  t['reference']={'provenance':'Offline native solution translated to ordinary mouse actions; replayed in native midend without solve. Not an agent rollout.','viewport':size,'actions':actions}
  report[ident]={'difficulty':level,'native_replay_success':verified,'reference_actions':len(actions),'viewport':size}
assert len(tasks)==15
p.write_text(json.dumps(tasks,indent=2)+'\n')
(ROOT/'game_packages/tatham/authoring-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
