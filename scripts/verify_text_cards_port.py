"""Focused native-rule and recorded-GUI-state parity for all 30 new text tasks."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from screenplay.tasks import catalog
from screenplay_text.fifteen import build_request
from screenplay_text.freecell import FreeCellText,STACKS
from screenplay_text.endless import EndlessText


def audit():
    tasks=catalog();checks=[]
    for task,data in tasks.items():
        if data['package']=='pysolfc':
            env=FreeCellText(task)
            initial=env.state()
            for source,target,count in data['reference']['stack_moves']:
                before=env.state()
                env.step({'type':'move_cards','source':STACKS[source],'target':STACKS[target],'count':count})
                assert env.state()!=before,(task,source,target,count)
                assert sorted(c for pile in env.state() for c in pile)==list(range(52))
                if env.result:break
            assert env.result and env.result['success'],task
            checks.append({'task':task,'native_rule_witness_success':True,'decisions':env.decisions})
            sample=FreeCellText(task,max_decisions=1)
            sample.step({'type':'move_cards','source':'R1','target':'R1','count':1})
            assert sample.state()==initial and not sample.result['success']
        elif data['package']=='endless_sky':
            env=EndlessText(task)
            try:
                gui_path=ROOT/data['reference']['verified_run']/'private/latest_state.json'
                gui=json.loads(gui_path.read_text())
                target={name:count for name,count in gui['cargo'].items() if count}
                assert env._state['prices']==gui['prices'],task
                assert env._state['cargo_capacity']==gui['cargo_capacity'],task
                sequence=[{'type':'open_panel','panel':'trading'}]
                for name,count in env._state['cargo'].items():
                    sequence += [{'type':'sell','commodity':name}] * max(0,count-target.get(name,0))
                for name,count in target.items():
                    sequence += [{'type':'buy','commodity':name}] * max(0,count-env._state['cargo'].get(name,0))
                goalcrew=gui['crew']
                if goalcrew!=env._state['crew']:
                    sequence.append({'type':'open_panel','panel':'hiring'})
                    sequence += [{'type':'hire' if goalcrew>env._state['crew'] else 'fire'}]*abs(goalcrew-env._state['crew'])
                for action in sequence:
                    env.step(action)
                    if env.result:break
                assert env.result and env.result['success'],(task,env._state)
                # Multi-solution tasks can use a different legal basket from the GUI witness.
                initial_cash=int(data['parameters']['native_fixture'].splitlines()[0].split()[1])
                import shlex
                initial_cargo={}
                for line in data['parameters']['native_fixture'].splitlines():
                    parts=shlex.split(line)
                    if parts[0]=='cargo':initial_cargo[parts[1]]=int(parts[2])
                expected_cash=initial_cash+sum(env._state['prices'][name]*(initial_cargo.get(name,0)-env._state['cargo'][name]) for name in env._state['cargo'])
                assert env._state['cash']==expected_cash and env._state['outfits_kept'] and env._state['ship_kept'] and env._state['debt']==0
                checks.append({'task':task,'native_cpp_goal_success':True,'prices_match_recorded_gui':True,
                               'cash_matches_native_trade_ledger':True,'decisions':env.decisions})
            finally:env.close()
    assert len(checks)==30
    cards=FreeCellText('pysolfc-freecell-12');initial=cards.state()
    cards.step({'type':'move_cards','source':'T1','target':'R1','count':1});moved=cards.state();assert moved!=initial
    cards.step({'type':'undo'});assert cards.state()==initial
    cards.step({'type':'redo'});assert cards.state()==moved
    cards.step({'type':'restart'});assert cards.receipt['status']=='rejected' and cards.state()==moved
    port=EndlessText('endless-sky-manifest')
    try:
        assert 'Food: price' not in port.describe() and 'Crew including pilot:' not in port.describe()
        old=port.native_state();port.step({'type':'buy','commodity':'Food'});assert port.receipt['status']=='rejected' and port._state==old
        port.step({'type':'open_panel','panel':'trading'});assert 'Food: price' in port.describe()
        assert 'Crew including pilot:' not in port.describe()
        for _ in range(20):port.step({'type':'buy','commodity':'Food'})
        assert port._state['food']==20
        old=port._state['cash'];port.step({'type':'buy','commodity':'Food'});assert port._state['food']==20 and port._state['cash']==old
        port.step({'type':'open_panel','panel':'hiring'});assert 'Food: price' not in port.describe()
        for _ in range(8):port.step({'type':'hire'})
        assert port._state['crew']==6
        for _ in range(8):port.step({'type':'fire'})
        assert port._state['crew']==1
        old=port._state['processed_updates'];port.step({'type':'wait','duration_ms':34})
        assert port._state['processed_updates']==old+2
        body=json.dumps(build_request([],port.observe()))
        assert all(key not in body for key in ['native_fixture','goalCargo','outfits_kept','image_url'])
    finally:port.close()
    return {'at':datetime.now(timezone.utc).isoformat(),'passed':True,'tasks':30,'checks':checks,
            'edge_cases':['card conservation','illegal moves consume decisions','undo/redo','FreeCell restart unavailable',
                          'port panel-limited observations','unit trading and full cargo no-op','crew native upper/lower bounds','simulation update cost'],
            'model_requests_sent':0,'desktop_actions_sent':0,
            'scope':'FreeCell native legality/win predicates on data-only stacks; Endless Sky original C++ panel actions and goal bridge with rendering omitted. Not GUI dispatch or model performance.'}


if __name__=='__main__':
    result=audit();path=ROOT/'research/text-ablation/cards-port-native-parity.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['passed','tasks','model_requests_sent','desktop_actions_sent']}))
