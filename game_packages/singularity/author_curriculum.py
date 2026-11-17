"""Rebuild the authored curriculum from native scenario descriptions."""
import json
import configparser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
P = Path(__file__).parent
native = configparser.ConfigParser(interpolation=None)
native.read(ROOT / '.cache/sources/singularity/singularity/data/techs.dat')
def closure(names):
    result=[]
    def visit(name):
        for pre in native[name].get('pre_list', native[name].get('pre', '')).split('|'):
            if pre.strip(): visit(pre.strip())
        if name not in result: result.append(name)
    for name in names: visit(name)
    return result

def b(kind, loc='N AMERICA', items=None):
    result={'type':kind,'location':loc}
    if items: result['items']=items
    return result

def equip(kind,count=1): return {'type':kind,'count':count}
S=b('Server Access'); D=b('Datacenter'); U=b('Stolen Computer Time')
rows=[
('server-foothold','easy',[],5000,[U],[],2,{'bases':[b('Server Access')]},
 'Establish at least one completed Server Access base while retaining at least two completed bases in total.',
 ['base purchase','capacity expansion'],'One immediate affordable expansion; no research prerequisite.'),
('distributed-access','easy',[],5000,[S],[],2,{'regions':2},
 'Maintain completed bases in at least two different locations.',
 ['world map','geographic diversification'],'Requires recognizing location membership and selecting a new location.'),
('income-reserve','easy',[],2000,[S,b('Server Access','EUROPE')],['Stock Manipulation'],2,{'cash':2400},
 'Complete Stock Manipulation and grow cash to at least $2,400 while keeping at least two completed bases alive.',
 ['CPU allocation','jobs','cash flow'],'A short income allocation exercise with upkeep and a modest reserve target.'),
('storage-fitout','easy',['Personal Identification'],20000,[S,b('Storage Unit')],[],2,
 {'bases':[b('Storage Unit',items={'cpu':equip('Gaming PC')})]},
 'Install and finish at least one Gaming PC in a Storage Unit; keep at least two completed bases alive.',
 ['equipment','construction labor'],'Separates a completed empty building from completed usable equipment.'),
('datacenter-estate','medium',['Personal Identification'],6000,[S],[],3,
 {'bases':[{'type':'Datacenter','count':2}],'regions':2},
 'Own at least two completed Datacenters across an estate spanning at least two locations and three completed bases in total.',
 ['construction pipeline','upkeep','regional expansion'],'Multiple day-long projects and regional placement must all remain viable.'),
('covert-hygiene','medium',['Intrusion'],10000,[S,b('Server Access','EUROPE'),b('Server Access','ASIA')],['Stealth','Exploit Discovery/Repair','Database Manipulation'],1,{},
 'Complete Stealth, Exploit Discovery/Repair, and Database Manipulation while retaining a completed base.',
 ['prerequisite graph','research allocation','detection management'],'A branching prerequisite graph includes Personal Identification, which is not initially researched.'),
('powered-storage','medium',['Personal Identification'],30000,[S,b('Storage Unit')],[],2,
 {'bases':[b('Storage Unit',items={'cpu':equip('Gaming PC',3),'reactor':equip('Diesel Generator')})],'cash':1000},
 'Finish at least three Gaming PCs and a Diesel Generator in the same Storage Unit, retain two completed bases, and end with at least $1,000 cash.',
 ['batch equipment','reactor','reserve management'],'Coordinates equipment slots and construction while maintaining a cash floor.'),
('parallel-production','medium',['Personal Identification'],30000,[D],['Parallel Computation'],2,
 {'bases':[b('Storage Unit',items={'cpu':equip('Cluster')})]},
 'Research Parallel Computation and commission a Storage Unit with at least one completed Cluster, while keeping two completed bases.',
 ['technology unlock','equipment availability','build versus research'],'Research unlocks hardware for a new building; CPU time and construction must be sequenced.'),
('industrial-transition','hard',['Personal Identification','Microchip Design'],100000,[D,b('Storage Unit',items={'cpu':equip('Mainframe',8)})],['Corporate Identification'],3,
 {'bases':[{'type':'Large Warehouse'}],'cash':5000},
 'Research Corporate Identification, finish a Large Warehouse, retain three completed bases, and end with at least $5,000 cash.',
 ['branch convergence','capital planning','multi-day construction'],'Several research branches converge on an expensive facility; spending and time exposure interact.'),
('undersea-research','hard',['Personal Identification','Autonomous Vehicles'],3500000,[D,b('Storage Unit',items={'cpu':equip('Mainframe',4)})],['Heat Signature Reduction'],3,
 {'bases':[b('Undersea Lab','OCEAN',{'cpu':equip('Mainframe',2)})]},
 'Commission an Undersea Lab in OCEAN with at least two completed Mainframes, complete Heat Signature Reduction; retain at least three completed bases.',
 ['location safety','danger-tier research','infrastructure dependency'],'Danger-1 research requires powered ocean infrastructure; ordinary urban CPUs alone cannot complete it.'),
('balanced-expansion','hard',['Personal Identification'],18000,[D],['Advanced Personal Identification'],3,
 {'bases':[{'type':'Small Warehouse'}],'cash':4000,'regions':2},
 'Complete Advanced Personal Identification, establish a Small Warehouse, and keep three completed bases in at least two locations with at least $4,000 cash.',
 ['income versus research','limited capital','regional construction'],'Starting capital cannot cover the full goal and reserve, requiring deliberate income/research reallocation.'),
('regional-resilience','hard',['Personal Identification'],18000,[D],['Stealth'],4,
 {'regions':3,'bases':[{'type':'Storage Unit','count':2,'items':{'cpu':equip('Gaming PC',2)}}]},
 'Complete Stealth and maintain four completed bases across three locations, including two Storage Units each with at least two completed Gaming PCs.',
 ['distributed operations','per-base equipment','upkeep exposure'],'Several locations and separate equipment inventories must satisfy simultaneous conditions.'),
('hardware-frontier','hard',['Personal Identification','Microchip Design'],110000,[D,b('Storage Unit',items={'cpu':equip('Mainframe',8)})],['Advanced Microchip Design'],2,
 {'bases':[b('Storage Unit',items={'cpu':equip('Supercomputer')})],'cpu':300,'cash':5000},
 'Complete Advanced Microchip Design, finish at least one Supercomputer in a Storage Unit, and retain two completed bases, at least 300 active CPU, and $5,000 cash.',
 ['hardware replacement','construction downtime','active capacity','reserve constraint'],'Hardware replacement competes with research and labor; ownership alone is insufficient without active capacity.'),
]
previous=json.loads((P/'tasks.json').read_text())
tasks={k:previous[k] for k in ['singularity-intrusion','singularity-research-chain']}
tasks['singularity-research-chain']['instruction']='Research Intrusion and Personal Identification, and maintain at least two completed bases. Build enough computing capacity to finish within the simulation budget.'
for key,diff,mechanisms,why in [('singularity-intrusion','easy',['research allocation','simulation speed'],'A single research target from a minimal initial base.'),('singularity-research-chain','medium',['research dependency','capacity expansion','bounded clock'],'Capacity must grow before the second research finishes within a tighter update budget.')]:
    tasks[key]['parameters']['curriculum']={'difficulty':diff,'mechanisms':mechanisms,'difficulty_rationale':'Author estimate, pending human/model calibration: '+why}
for ident,diff,tech,cash,bases,wanted,total,goal,instruction,mechanisms,why in rows:
    for record in goal.get('bases', []):
        if record.get('location') != 'OCEAN': record.pop('location', None)
    starting=closure(tech)
    start=f'Start: ${cash:,} cash; completed bases: '+ '; '.join(x['type']+' in '+x['location']+(' with '+', '.join(str(v['count'])+' '+v['type'] for v in x.get('items',{}).values()) if x.get('items') else '') for x in bases)+'.'
    start+=' The original very-easy start includes Socioanalytics and Advanced Socioanalytics. Additional researched technologies: '+(', '.join(starting) if starting else 'none')+'.'
    params={'seed':20260914,'initial':{'cash':cash,'technologies':starting,'bases':bases},'technologies':wanted,'built_bases':total,'goal':goal,'update_ms':33,'max_updates': {'easy':2400,'medium':4800,'hard':9000}[diff],
    'curriculum':{'difficulty':diff,'mechanisms':mechanisms,'difficulty_rationale':'Author estimate, pending human/model calibration: '+why}}
    tasks['singularity-'+ident]={'game':'Endgame: Singularity','game_id':ident,'instruction':instruction+' '+start,'rules':tasks['singularity-intrusion']['rules']+' Starting fixtures are native completed assets and research; all subsequent costs, upkeep, prerequisites, discovery and construction use original rules. All goal conditions must hold simultaneously.', 'max_decisions':{'easy':100,'medium':160,'hard':240}[diff],'time_mode':'fixed_update_budget','undo_allowed':False,'parameters':params}
assert len(tasks)==15
for ident, task in tasks.items():
    old=previous.get(ident, {})
    def scenario(value):
        return (value.get('game_id'), {k:v for k,v in value.get('parameters',{}).items() if k!='curriculum'})
    reference=old.get('reference')
    if reference and scenario(old)==scenario(task) and len(reference.get('actions',[]))<=task['max_decisions']:
        task['reference']=reference
(P/'tasks.json').write_text(json.dumps(tasks,indent=2)+'\n')
