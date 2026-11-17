"""Private fixture-author recorder. NOT an agent policy or a score claim.

Only run while holding the team's desktop handoff. All game inputs use Episode's
validated low-level PyAutoGUI actions. Native marble coordinates inform private
author planning, never game-state writes. PNGs, actions, states and provenance are
saved by Episode. Commands: low-level action, {goto:[world_x,world_y]},
{touch:[stone_x,stone_y]}, {pulse:[dx,dy]}, {path:[[x,y],...]},
{replay:true}, {save_reference:true}, {close:true}. Controller options:
{goto:[x,y], mode:'ice', tolerance:.2, limit:24}; all are author-only commands.
"""
import json,sys,math,re,configparser
from collections import deque
from xml.etree import ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from screenplay.runner import Episode, write_json
from screenplay.tasks import load_task,catalog
from screenplay.replay import export_replay
name=sys.argv[1]
output=Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'runs/v1-acceptance'/f'{name}-author'
output.parent.mkdir(parents=True,exist_ok=True)
ep=Episode(load_task(name),output=output);actions=[];pointer=[400,292];velocity=[0.,0.]
(ep.directory/'agent_provenance.json').write_text(json.dumps(dict(type='fixture-author',autonomous_model=False,native_telemetry_used_for_author_planning=True,execution='Episode validated low-level PyAutoGUI')))

def available_research():
    done=set(ep.backend.state().get('researched',[]))
    data=configparser.ConfigParser(interpolation=None)
    data.read(ROOT/'.cache/sources/singularity/singularity/data/techs.dat')
    available=[]
    for name in data.sections():
        pre=[v.strip() for v in data[name].get('pre_list',data[name].get('pre','')).split('|') if v.strip()]
        eligible=any(v in done for v in pre[1:]) if pre[:1]==['OR'] else all(v in done for v in pre)
        if name not in done and eligible:available.append(name)
    return ['CPU Pool','Jobs']+sorted(available,key=str.casefold)

def research_rows():
    print(json.dumps({'private_author_research_list':list(enumerate(available_research()))}),flush=True)

def show():
    print(json.dumps(dict(run=str(ep.directory),frame=str(ep.directory/'frames'/f'{ep.observation_id:06d}.png'),state=ep.backend.state(),score=ep.last_score,ended=ep.ended)),flush=True)
def act(action,verbose=True):
    before=ep.backend.state()
    ep.act(dict(episode_id=ep.id,action_id=f'author-{len(actions)}',based_on_observation_id=ep.observation_id,action=action))
    actions.append(action)
    after=ep.backend.state()
    if 'marble' in before and 'marble' in after:
        dt=after['native_time']-before['native_time']
        if dt>0:
            for i in range(2):velocity[i]=(after['marble'][i]-before['marble'][i])/dt
    if action['type'] in ['mouse_move','click']:pointer[:]=[action['x'],action['y']]
    if action['type']=='drag':pointer[:]=action['to']
    if verbose:show()
def pulse(delta):
    dx,dy=[max(-250,min(250,round(v))) for v in delta]
    if not(40<=pointer[0]+dx<=760 and 50<=pointer[1]+dy<=570):
        act({'type':'drag','from':pointer[:],'to':[400,292],'button':'middle','duration_ms':100},False)
        if ep.ended:return
    act({'type':'mouse_move','x':pointer[0]+dx,'y':pointer[1]+dy},False)
def goto(target,mode='lawn',tolerance=.22,limit=24):
    assert ep.task.package=='enigma'
    for attempt in range(limit):
        if ep.ended:break
        p=ep.backend.state()['marble'];error=[target[i]-p[i] for i in range(2)];distance=math.hypot(*error)
        if distance<tolerance and (mode!='ice' or math.hypot(*velocity)<.45):break
        if mode=='ice':
            desired=[max(-3,min(3,e*2)) for e in error]
            lua=ET.fromstring((ep.private/'level.xml').read_text()).find('.//{*}luamain').text
            rows=json.loads('['+re.search(r'wo\(ti, [\'\"] [\'\"], \{(.*?)\}\)',lua,re.S).group(1)+']')
            floor=rows[int(p[1])][int(p[0])]
            impulse_gain=.056/15 if floor=='I' else .056
            pulse([(desired[i]-velocity[i])/impulse_gain for i in range(2)])
            delay=300
        else:
            # Empirical initial gain from the original oxyd-pair reference trace.
            # This controls the author pointer, never friction or marble physics.
            gain=40+20/math.sqrt(max(distance,.01))
            pulse([e*gain for e in error]);delay=1200
        if not ep.ended:act({'type':'wait','duration_ms':delay},False)
    show()
def singularity_modal():
    # Fixed native popup pixels observed in recorded frames; author-only vision.
    from PIL import Image
    im=Image.open(ep.directory/'frames'/f'{ep.observation_id:06d}.png').convert('RGB')
    if im.getpixel((260,250)) != (0,0,123):return 0
    return 2 if im.getpixel((300,420))[0]>100 else 1

def pause_map():
    if ep.ended:return
    kind=singularity_modal()
    if kind:act({'type':'click','x':625 if kind==2 else 500,'y':427},False)
    if not ep.ended:act({'type':'click','x':393,'y':42},False)

def research(name):
    assert ep.task.package=='singularity'
    if ep.ended or name in ep.backend.state()['researched']:return
    pause_map()
    act({'type':'click','x':260,'y':77},False)
    names=available_research();index=names.index(name)
    scroll=max(0,index-8)
    for _ in range(scroll):act({'type':'click','x':552,'y':470},False)
    row=index-scroll;y=round(129+row*384/9)
    act({'type':'drag','from':[60,y],'to':[530,y],'duration_ms':600},False)
    if ep.backend.state()['cpu_usage'].get(name,0)<=0:raise RuntimeError('Research slider did not allocate '+name)
    act({'type':'click','x':500,'y':512},False)
    act({'type':'click','x':533,'y':42},False)
    for _ in range(80):
        if ep.ended or name in ep.backend.state()['researched']:break
        kind=singularity_modal()
        if kind:
            act({'type':'click','x':375 if kind==2 else 500,'y':427},False)
            if kind==1 and not ep.ended:act({'type':'click','x':533,'y':42},False)
        else:act({'type':'wait','duration_ms':500},False)
    if not ep.ended and name not in ep.backend.state()['researched']:raise RuntimeError('Author research wait limit '+name)
    pause_map();show()

LOCATIONS={'N AMERICA':(250,280),'EUROPE':(550,239),'ASIA':(770,280),'AFRICA':(550,359),'S AMERICA':(330,429),'AUSTRALIA':(850,444),'OCEAN':(550,500)}
def advance_until(predicate,limit=100):
    if ep.ended:return
    act({'type':'click','x':533,'y':42},False)
    for _ in range(limit):
        if ep.ended or predicate(ep.backend.state()):break
        kind=singularity_modal()
        if kind:
            act({'type':'click','x':375 if kind==2 else 500,'y':427},False)
            if kind==1 and not ep.ended:act({'type':'click','x':533,'y':42},False)
        else:act({'type':'wait','duration_ms':300},False)
    if not ep.ended and not predicate(ep.backend.state()):raise RuntimeError('Author advancement limit')
    pause_map();show()

def build_base(kind,location,count=1):
    assert ep.task.package=='singularity'
    if ep.ended:return
    before=sum(b['done'] and b['type']==kind and b['location']==location for b in ep.backend.state()['bases'])
    pause_map();x,y=LOCATIONS[location];act({'type':'click','x':x,'y':y},False)
    defs=configparser.ConfigParser(interpolation=None);defs.read(ROOT/'.cache/sources/singularity/singularity/data/bases.dat')
    done=set(ep.backend.state()['researched']);region='OCEAN' if location=='OCEAN' else 'URBAN';choices=[]
    for name in defs.sections():
        d=defs[name];pre=[v.strip() for v in d.get('pre_list',d.get('pre','')).split('|') if v.strip()]
        allowed=[v.strip() for v in d.get('allowed_list',d.get('allowed','')).split('|')]
        if all(v in done for v in pre) and region in allowed:choices.append(name)
    choices.sort(key=lambda name:tuple(int(v.strip()) for v in defs[name]['cost_list'].split('|')),reverse=True)
    index=choices.index(kind)
    for _ in range(count):
        act({'type':'click','x':184,'y':600},False)
        act({'type':'click','x':270,'y':round(145+index*22)},False)
        act({'type':'click','x':275,'y':594},False)
    act({'type':'click','x':815,'y':600},False)
    advance_until(lambda state:sum(b['done'] and b['type']==kind and b['location']==location for b in state['bases'])>=before+count)

def equip_first(location,model,count=1,slot='cpu'):
    # Caller selects a location whose first native-sorted base is the intended base.
    assert ep.task.package=='singularity'
    if ep.ended:return
    pause_map();x,y=LOCATIONS[location];act({'type':'click','x':x,'y':y},False)
    act({'type':'click','x':184,'y':547},False)
    selected_base=next(b for b in ep.backend.state()['bases'] if b['location']==location)
    selected_name=selected_base['name']
    old_item=selected_base['items'].get(slot)
    act({'type':'click','x':555,'y':225 if slot=='cpu' else 281},False)
    defs=configparser.ConfigParser(interpolation=None);defs.read(ROOT/'.cache/sources/singularity/singularity/data/items.dat')
    done=set(ep.backend.state()['researched']);choices=[]
    for name in defs.sections():
        d=defs[name];pre=[v.strip() for v in d.get('pre_list',d.get('pre','')).split('|') if v.strip()]
        if d.get('type')==slot and all(v in done for v in pre):choices.append(name)
    choices.sort(key=lambda name:tuple(int(v.strip()) for v in defs[name]['cost_list'].split('|')),reverse=True)
    act({'type':'click','x':270,'y':round(145+choices.index(model)*22)},False)
    for _ in range(count-1):act({'type':'key_press','key':'right'},False)
    act({'type':'click','x':275,'y':594},False)
    # Replacement confirmation is a native Yes/No dialog with the same outline.
    if slot=='cpu' and old_item:act({'type':'click','x':388,'y':594},False)
    pending=next(b for b in ep.backend.state()['bases'] if b['location']==location and b['name']==selected_name)['items'].get(slot,{})
    if pending.get('type')!=model:raise RuntimeError('Author equipment confirmation failed: '+model)
    act({'type':'click','x':500,'y':607},False)
    act({'type':'click','x':815,'y':600},False)
    advance_until(lambda state:any(b['location']==location and b['name']==selected_name and b['done'] and b['items'].get(slot,{}).get('type')==model and b['items'][slot]['done'] and b['items'][slot]['count']>=count for b in state['bases']))

def navigate(target,opened=(),mode='lawn'):
    # Private fixture-author geometry only; executed moves still go through act().
    lua=ET.fromstring((ep.private/'level.xml').read_text()).find('.//{*}luamain').text
    rows=json.loads('['+re.search(r'wo\(ti, [\'\"] [\'\"], \{(.*?)\}\)',lua,re.S).group(1)+']')
    cells={(x,y):c for y,row in enumerate(rows) for x,c in enumerate(row)}
    targetcell=(int(target[0]),int(target[1]));point=ep.backend.state()['marble'];start=(int(point[0]),int(point[1]))
    solid=set('#~OPQRSTKLBDE')-set(opened)
    touching=cells[targetcell] in 'OPQRSTKL'
    destinations={(targetcell[0]+dx,targetcell[1]+dy) for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]} if touching else {targetcell}
    queue=deque([start]);parent={start:None};end=None
    while queue:
        cur=queue.popleft()
        if cur in destinations:end=cur;break
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            pos=(cur[0]+dx,cur[1]+dy)
            if pos not in parent and cells.get(pos,'#') not in solid:parent[pos]=cur;queue.append(pos)
    if end is None:raise ValueError('No route in private author map; supply opened gate symbols after verifying controls')
    path=[]
    while end is not None:path.append(end);end=parent[end]
    path.reverse();waypoints=[]
    # Snap to the current cell center before corner routing; otherwise a diagonal
    # cut can brush a nearby key-switch and close an already-open native door.
    goto([start[0]+.5,start[1]+.5],mode=mode,tolerance=.08,limit=8)
    if ep.ended:return
    for i in range(1,len(path)):
        if i==len(path)-1 or (path[i][0]-path[i-1][0],path[i][1]-path[i-1][1])!=(path[i+1][0]-path[i][0],path[i+1][1]-path[i][1]):waypoints.append([path[i][0]+.5,path[i][1]+.5])
    for waypoint in waypoints:
        if ep.ended:return
        goto(waypoint,mode=mode,tolerance=.08,limit=12)
    if touching and not ep.ended:touch(target)

def touch(target):
    p=ep.backend.state()['marble'];d=[target[i]-p[i] for i in range(2)];length=math.hypot(*d)
    if length>1.15:
        approach=[target[i]-d[i]/length*1.05 for i in range(2)]
        goto(approach,tolerance=.16,limit=16)
    if ep.ended:return
    p=ep.backend.state()['marble'];d=[target[i]-p[i] for i in range(2)];length=math.hypot(*d)
    pulse([v/max(length,.001)*65 for v in d])
    if not ep.ended:act({'type':'wait','duration_ms':450},False)
    show()
try:
    ep.start();show()
    for line in sys.stdin:
        value=json.loads(line)
        if value.get('close'):break
        if value.get('save_reference'):
            if not ep.last_score['success']:raise RuntimeError('Cannot promote an unsuccessful trace')
            path=ROOT/'game_packages'/ep.task.package/'tasks.json';data=json.loads(path.read_text())
            data[name]['reference']=dict(provenance='fixture-author: real Episode/PyAutoGUI desktop; private native telemetry informed author planning, not an autonomous-model score',viewport=[ep.width,ep.height],actions=actions,verified_run=str(ep.directory.relative_to(ROOT)))
            write_json(path,data);print('reference saved',flush=True)
        elif value.get('research_rows'):research_rows()
        elif 'research' in value:research(value['research'])
        elif 'build_base' in value:build_base(value['build_base'],value.get('location','N AMERICA'),value.get('count',1))
        elif 'equip' in value:equip_first(value.get('location','N AMERICA'),value['equip'],value.get('count',1),value.get('slot','cpu'))
        elif 'earn' in value:advance_until(lambda state:state['cash']>=value['earn'])
        elif value.get('replay'):
            for action in catalog()[name]['reference']['actions']:
                if ep.ended:break
                act(action)
        elif 'navigate' in value:navigate(value['navigate'],value.get('opened',[]),value.get('mode','lawn'))
        elif 'goto' in value:goto(value['goto'],value.get('mode','lawn'),value.get('tolerance',.22),value.get('limit',24))
        elif 'path' in value:
            for target in value['path']:
                if ep.ended:break
                goto(target,value.get('mode','lawn'),value.get('tolerance',.22),value.get('limit',24))
        elif 'touch' in value:touch(value['touch'])
        elif 'pulse' in value:pulse(value['pulse']);show()
        else:act(value)
finally:
    ep.close()
    export_replay(ep.directory)
    summary=ROOT/'artifacts/v1-singularity-enigma-desktop.json'
    rows=json.loads(summary.read_text()) if summary.exists() else []
    result=json.loads((ep.directory/'result.json').read_text()) if (ep.directory/'result.json').exists() else dict(success=False,stop_reason='author_closed_unfinished')
    rows.append(dict(task_id=name,directory=str(ep.directory.relative_to(ROOT)),result=result,verification_kind='fixture-author PyAutoGUI desktop',attempt_role='successful_witness' if result.get('success') else 'exploratory_attempt',native_telemetry_for_author_planning=True))
    summary.parent.mkdir(parents=True,exist_ok=True);summary.write_text(json.dumps(rows,indent=2)+'\n')
