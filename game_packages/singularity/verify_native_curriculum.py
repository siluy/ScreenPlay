"""Offline native-rule feasibility trajectories, NOT desktop-action validation.
Only setup uses finish(); all witness purchases/research use give_time/work_on.
"""
import sys, json, random, builtins, gettext, configparser
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
sys.path.insert(0,str(ROOT/'.cache/sources/singularity'));sys.path.insert(0,str(P/'native'))
from singularity.code import dirs,g,data,i18n,base,item
from screenplay_scenario import apply_fixture,goal_status
root=ROOT/'.cache/sources/singularity/singularity'
for name,rel in {'root':'','data':'data','i18n':'i18n','sounds':'data/sounds','music':'music'}.items():dirs.read_dirs[name]=[str(root/rel)]
scratch=Path('/tmp/screenplay-singularity-native-witness');scratch.mkdir(exist_ok=True)
for name in ['i18n','pref','saves','log']:dirs.write_dirs[name]=str(scratch)
builtins._=lambda x:x;builtins.ngettext=lambda a,b,n:a if n==1 else b
i18n.gettext_language=gettext.NullTranslations()
class Display:
    def show_message(self,*args,**kwargs):pass
    def set_speed(self,*args,**kwargs):pass
    def find_speed_button(self,*args,**kwargs):pass
    def show_story_section(self,*args,**kwargs):pass
g.map_screen=Display();data.reload_all()
config=configparser.ConfigParser(interpolation=None);config.read(root/'data/techs.dat')
records=[]
for ident,t in json.loads((P/'tasks.json').read_text()).items():
    random.seed(t['parameters']['seed']);g.new_game('very-easy',initial_speed=0);apply_fixture(t['parameters']);g.pl.intro_shown=True
    params=t['parameters'];trace=[];ticks=0
    def advance(until,label,limit=6000):
        global ticks
        n=0
        while not until():
            g.pl.give_time(14400);ticks+=1;n+=1
            if g.pl.lost_game():raise RuntimeError('lost native game during '+label)
            if n>limit:raise RuntimeError('no completion: '+label)
        trace.append({'action':label,'ticks':ticks,'cash':int(g.pl.cash),'cpu':list(g.pl.available_cpus),'native_day':g.pl.raw_day})
    def research(name):
        if g.pl.techs[name].done:return
        for pre in config[name].get('pre_list',config[name].get('pre','')).split('|'):
            if pre.strip():research(pre.strip())
        tech=g.pl.techs[name];assert tech.available()
        cap=g.pl.available_cpus[tech.danger];assert cap>0,('no safe CPUs',name)
        g.pl.set_allocated_cpu_for(name,max(1,cap))
        advance(lambda:tech.done,'research '+name)
    def construct(kind,loc):
        obj=base.Base('Witness '+kind,g.base_type[kind]);assert obj.available();assert g.pl.locations[loc].available()
        g.pl.locations[loc].add_base(obj)
        advance(lambda:obj.done,'build '+kind+' in '+loc)
        return obj
    def install(obj,slot,e):
        spec=g.items[e['type']];assert spec.available()
        if slot=='cpu':assert e.get('count',1)<=obj.spec.size
        new=item.Item(spec,base=obj,count=e.get('count',1));obj.items[slot]=new;obj.check_power();obj.recalc_cpu()
        advance(lambda:new.done,'install '+str(new.count)+' '+spec.id)
    try:
        assert not goal_status(params)[0],'already solved initial fixture'
        # Preserve a minimal earning source, and accelerate large research graphs using native affordable servers.
        if ident in ['singularity-intrusion','singularity-research-chain']:
            if ident.endswith('research-chain'):construct('Server Access','N AMERICA')
        if ident=='singularity-server-foothold':construct('Server Access','EUROPE')
        if ident=='singularity-distributed-access':construct('Server Access','EUROPE')
        if ident=='singularity-datacenter-estate':construct('Datacenter','N AMERICA');construct('Datacenter','EUROPE')
        if params['curriculum']['difficulty'] in ['medium','hard'] and ident not in ['singularity-research-chain','singularity-datacenter-estate','singularity-powered-storage','singularity-regional-resilience']:
            if not g.pl.techs['Personal Identification'].done:research('Personal Identification')
            for loc in ['N AMERICA','EUROPE','ASIA','AFRICA','AUSTRALIA','S AMERICA','N AMERICA','EUROPE']:
                construct('Datacenter',loc)
        if ident=='singularity-undersea-research':
            ocean=construct('Undersea Lab','OCEAN');install(ocean,'cpu',{'type':'Mainframe','count':8})
        for name in params.get('technologies',[]):research(name)
        for wanted in params.get('goal',{}).get('bases',[]):
            matches=[b for b in g.all_bases() if b.done and b.spec.id==wanted['type'] and ('location' not in wanted or b.location.id==wanted['location'])]
            while len(matches)<wanted.get('count',1):
                loc=wanted.get('location',['N AMERICA','EUROPE','ASIA'][len(matches)%3]);matches.append(construct(wanted['type'],loc))
            for obj in matches[:wanted.get('count',1)]:
                for slot,e in wanted.get('items',{}).items():
                    present=obj.items.get(slot)
                    if not(present and present.done and present.spec.id==e['type'] and present.count>=e.get('count',1)):install(obj,slot,e)
        while len([b for b in g.all_bases() if b.done])<params.get('built_bases',1):construct('Server Access','ASIA')
        while len({b.location.id for b in g.all_bases() if b.done})<params.get('goal',{}).get('regions',0):
            used={b.location.id for b in g.all_bases() if b.done};construct('Server Access',next(x for x in ['EUROPE','ASIA','AFRICA','AUSTRALIA'] if x not in used))
        advance(lambda:goal_status(params)[0],'final simultaneous goal',limit=2000)
        assert ticks + 6*t['max_decisions'] <= params['max_updates'], 'exceeds budget after reserving input overhead'
        records.append({'task_id':ident,'native_rule_witness':True,'simulation_ticks_14400s':ticks,'budget_updates':params['max_updates'],'reserved_input_updates':6*t['max_decisions'],'trace':trace,'desktop_verified':False})
    except Exception as e:records.append({'task_id':ident,'native_rule_witness':False,'error':str(e),'trace':trace,'desktop_verified':False})
(P/'native-feasibility.json').write_text(json.dumps(records,indent=2)+'\n')
for r in records:print(r['task_id'],r['native_rule_witness'],r.get('error',''),r.get('simulation_ticks_14400s',''))
