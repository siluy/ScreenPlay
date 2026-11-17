"""Author native Enigma Lua/XML levels; no simulation or physics replacement."""
import json
from pathlib import Path
from collections import Counter
P=Path(__file__).parent
previous=json.loads((P/'tasks.json').read_text())
previous_levels={p.stem:p.read_bytes() for p in (P/'levels').glob('*.xml')}

def room(): return [list('#'*20) if y in (0,12) else list('#'+' '*18+'#') for y in range(13)]
def put(m,x,y,c): m[y][x]=c
def vwall(m,x,gaps):
    for y in range(1,12):
        if y not in gaps: put(m,x,y,'#')
def hwall(m,y,gaps):
    for x in range(1,19):
        if x not in gaps: put(m,x,y,'#')
def fill(m,x1,y1,x2,y2,c):
    for y in range(y1,y2+1):
        for x in range(x1,x2+1): put(m,x,y,c)
def stones(m,positions):
    for c,x,y in positions: put(m,x,y,c)
levels=[]
def add(ident,diff,m,mechanisms,why): levels.append((ident,diff,m,mechanisms,why))

m=room();vwall(m,10,[6]);stones(m,[('@',4,6),('O',2,3),('O',17,9),('D',10,6),('S',6,3)])
add('switch-gate','easy',m,['switch','door','pairing'],'One visible switch controls the only passage; broad safe rooms allow recovery.')
m=room();vwall(m,10,[6]);stones(m,[('@',4,6),('O',2,3),('O',17,9),('B',10,6)])
add('crate-passage','easy',m,['pushable box','clearance','pairing'],'A box blocks the passage and can be pushed into a spacious landing area.')
m=room();fill(m,7,1,12,11,'I');stones(m,[('@',3,6),('O',2,6),('O',17,6)])
add('ice-crossing','easy',m,['friction change','braking'],'One broad ice zone introduces momentum control without lethal borders.')
m=room();vwall(m,6,[2,3]);vwall(m,13,[9,10]);stones(m,[('@',3,6),('O',2,10),('O',17,2),('P',9,2),('P',16,10)])
add('winding-memory','medium',m,['maze navigation','color memory','return travel'],'Alternating corridor entrances require remembering colors across long detours.')
m=room();vwall(m,10,[6]);stones(m,[('@',3,6),('O',2,3),('O',17,9),('D',10,6),('K',7,5),('k',3,10)])
add('keyed-chamber','medium',m,['inventory key','lock','door'],'Access depends on collecting an item and using its matching lock before pairing.')
m=room();fill(m,7,1,12,11,'~');fill(m,7,5,12,7,' ');stones(m,[('@',3,6),('O',2,3),('O',17,9),('P',3,10),('P',16,2)])
add('water-causeway','medium',m,['water hazard','safe crossing','color memory'],'A finite-width bridge makes overshoot fatal while pairs require repeated crossings.')
m=room();vwall(m,7,[4]);vwall(m,13,[8]);stones(m,[('@',3,6),('O',2,10),('O',17,2),('D',7,4),('E',13,8),('S',3,2),('T',10,10)])
add('sequential-gates','medium',m,['switch dependency','two doors','route planning'],'The second control is accessible only after the first gate is opened.')
m=room();fill(m,7,1,12,11,'I');fill(m,1,8,6,10,'C');fill(m,13,2,18,4,'C');fill(m,9,4,10,8,'#');stones(m,[('@',3,6),('O',2,2),('O',17,10),('P',2,10),('P',17,2)])
add('friction-slalom','medium',m,['ice','sand','obstacle avoidance','memory'],'Changing traction and a central obstacle require braking and route correction in both directions.')
m=room();vwall(m,7,[4]);vwall(m,13,[8]);stones(m,[('@',3,6),('O',2,10),('O',17,2),('P',3,2),('P',16,10),('D',7,4),('E',13,8),('K',5,3),('k',2,8),('T',10,2)])
add('key-switch-cascade','hard',m,['inventory dependency','switch dependency','memory across chambers'],'An item unlocks a first region, which contains the second gate control; pairing spans all three regions.')
m=room();vwall(m,7,[4]);vwall(m,13,[8]);hwall(m,6,[8,9,10,11,12,14,15,16,17,18]);stones(m,[('@',3,3),('O',2,2),('O',17,10),('P',3,5),('P',16,2),('B',7,4),('B',13,8)])
# Keep the first chamber connected below its divider; lower left chamber is intentionally unused.
add('crate-labyrinth','hard',m,['multiple boxes','push clearance','maze','color memory'],'Two narrow openings need box displacement with enough clearance for returning to remembered stones.')
m=room();fill(m,6,1,13,11,'~');fill(m,6,5,13,7,'I');stones(m,[('@',3,6),('O',2,2),('O',17,10),('P',2,10),('P',17,2)])
add('icy-causeway','hard',m,['low friction','water hazard','return crossings'],'Momentum persists on a three-cell ice bridge with lethal sides; each return crossing needs controlled approach.')
m=room();vwall(m,7,[3]);vwall(m,13,[9]);stones(m,[('@',3,6),('O',2,2),('P',2,10),('Q',5,9),('O',10,10),('R',9,3),('P',16,2),('Q',17,10),('R',16,6),('D',7,3),('S',5,3),('E',13,9),('T',10,6)])
add('gated-memory','hard',m,['four-color memory','gated regions','navigation interference'],'Four pairs are interleaved across controlled chambers, increasing memory interference and revisitation cost.')
m=room();vwall(m,7,[4]);vwall(m,13,[8]);fill(m,8,5,12,7,'~');fill(m,9,5,11,7,' ');stones(m,[('@',3,6),('O',2,2),('O',17,10),('P',3,10),('P',17,2),('D',7,4),('E',13,8),('K',5,3),('k',2,8),('L',11,9),('l',10,2)])
add('keys-and-causeway','hard',m,['two key codes','hazard crossing','ordered exploration','memory'],'Two distinct keys and locks span a water-divided middle chamber; wrong approaches cost recovery or life.')

tasks=json.loads((P/'tasks.json').read_text());tasks={k:tasks[k] for k in ['enigma-oxyd-pair','enigma-oxyd-memory']}
death_rule='Marble death ends the episode even if native spare lives remain.'
for task in tasks.values():
    task['rules']=task['rules'].replace(death_rule, '').strip()+' '+death_rule
for key,why in [('enigma-oxyd-pair','A single pair in a safe open arena isolates native marble control.'),('enigma-oxyd-memory','Two colors introduce short-term memory in an otherwise safe open arena.')]:
    tasks[key]['parameters']['curriculum']={'difficulty':'easy','mechanisms':['marble inertia','oxyd pairing']+(['color memory'] if key.endswith('memory') else []),'difficulty_rationale':'Author estimate, pending human/model calibration: '+why}
base=(P/'levels/oxyd-pair.xml').read_text();head=base.split("ti[' ']")[0];tail=base.split(']]>')[1]
definitions="""ti[' '] = {'fl_lawn'}
ti['#'] = {'st_fake_oxyda'} .. ti[' ']
ti['@'] = {'#ac_marble'} .. ti[' ']
ti['I'] = {'fl_ice'}
ti['C'] = {'fl_sand'}
ti['~'] = {'fl_water'}
ti['B'] = {'st_box_wood'} .. ti[' ']
ti['D'] = {'st_door', name='gate_one', flavor='a'} .. ti[' ']
ti['E'] = {'st_door', name='gate_two', flavor='a'} .. ti[' ']
ti['S'] = {'st_switch', target='gate_one'} .. ti[' ']
ti['T'] = {'st_switch', target='gate_two'} .. ti[' ']
ti['K'] = {'st_key', code=1, target='gate_one'} .. ti[' ']
ti['L'] = {'st_key', code=2, target='gate_two'} .. ti[' ']
ti['k'] = {'it_key', code=1} .. ti[' ']
ti['l'] = {'it_key', code=2} .. ti[' ']
"""
for i,c in enumerate('OPQR'): definitions+=f"ti['{c}'] = {{'st_oxyd', flavor='b', oxydcolor={i}}} .. ti[' ']\n"
for ident,diff,m,mechanisms,why in levels:
    rows=[''.join(row) for row in m];assert all(len(row)==20 for row in rows)
    assert Counter(''.join(rows))['@']==1
    for c in 'OPQR': assert Counter(''.join(rows))[c] in (0,2)
    (P/'levels'/f'{ident}.xml').write_text(head.replace('oxyd-pair',ident)+definitions+'wo(ti, \' \', '+json.dumps(rows).replace('[','{').replace(']','}')+')\n]]>'+tail)
    tasks['enigma-'+ident]={'game':'Enigma','game_id':ident,'instruction':'Guide the black marble to open every matching pair of Oxyd stones in this level. Touch two stones of the same color consecutively; remember revealed colors. '+ ('Avoid water; losing the marble fails the task. ' if '~' in ''.join(rows) else '')+'Use the native objects and terrain shown in the level.', 'rules':tasks['enigma-oxyd-pair']['rules']+' Restarting or loading another level fails the task. All original item, door, box and terrain behavior is retained.', 'max_decisions':{'easy':180,'medium':260,'hard':360}[diff],'time_mode':'fixed_update_budget','undo_allowed':False,'parameters':{'max_updates':{'easy':30000,'medium':40000,'hard':50000}[diff],'update_ms':10,'curriculum':{'difficulty':diff,'mechanisms':mechanisms,'difficulty_rationale':'Author estimate, pending human/model calibration: '+why}}}
assert len(tasks)==15
assert Counter(t['parameters']['curriculum']['difficulty'] for t in tasks.values())=={'easy':5,'medium':5,'hard':5}
for ident, task in tasks.items():
    old=previous.get(ident,{})
    reference=old.get('reference')
    same_parameters={k:v for k,v in old.get('parameters',{}).items() if k!='curriculum'}=={k:v for k,v in task['parameters'].items() if k!='curriculum'}
    same_level=previous_levels.get(task['game_id'])==(P/'levels'/f"{task['game_id']}.xml").read_bytes()
    if reference and old.get('game_id')==task['game_id'] and same_parameters and same_level and len(reference.get('actions',[]))<=task['max_decisions']:
        task['reference']=reference
(P/'tasks.json').write_text(json.dumps(tasks,indent=2)+'\n')
