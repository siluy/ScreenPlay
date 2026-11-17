"""Author-maintained curriculum data. New references are candidates, never GUI claims."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def write(game,data): (ROOT/'game_packages'/game/'tasks.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def curriculum(d,mech,why):return dict(difficulty=d,mechanisms=mech,difficulty_rationale=why+' Author estimate; requires human/model calibration.')
def click(x,y):return dict(type='click',x=x,y=y)
# Endless Sky: native_fixture is the sole canonical setup and goal representation.
p=ROOT/'game_packages/endless_sky/tasks.json'; old=json.loads(p.read_text()); es={}
prices=dict(Food=335,Clothing=224,Metal=468,Plastic=415,Equipment=560,Medical=590,Industrial=792,Electronics=838,**{'Heavy Metals':916,'Luxury Goods':1171})
rows={k:505+20*i for i,k in enumerate(prices)}
def addes(slug,d,initial,goal,description,mech,why,credits=30000,floor=20000,crew=1,goalcrew=None,basket=None,total=0,witness=None):
    key='endless-sky-'+slug
    fixture=[f'credits {credits}',f'mincash {floor}',f'crew {crew}']
    for name,n in initial.items():fixture.append(f'cargo "{name}" {n}')
    for name,n in goal.items():fixture.append(f'goal "{name}" {n}')
    if goalcrew is not None: fixture.append(f'goalcrew {goalcrew}')
    for name,n in (basket or {}).items():fixture.append(f'basket "{name}" {n}')
    if basket: fixture.append(f'baskettotal {total}')
    final=dict(goal);final.update(witness or {})
    balance=credits+sum(prices[k]*(initial.get(k,0)-final.get(k,0)) for k in prices)
    assert sum(initial.values())<=20 and sum(final.values())<=20 and balance>=floor,(key,balance)
    actions=[click(148,483),click(640,656)]
    for k in prices:
        actions += [click(629,rows[k])]*max(0,initial.get(k,0)-final.get(k,0))
    for k in prices:
        actions += [click(568,rows[k])]*max(0,final.get(k,0)-initial.get(k,0))
    if goalcrew is not None and crew!=goalcrew:
        actions += [click(830,592),click(640,557)]
        actions += [click(690 if goalcrew>crew else 610,731)]*abs(goalcrew-crew)
    task=old.get(key,dict(game='Endless Sky',game_id=slug,instruction=description,rules=''))
    task['instruction']=description+f' Finish on New Boston with at least {floor:,} credits, keep the original Shuttle as your only ship, and never take a loan. Carry no commodities beyond those allowed in the goal. Finish with the original installed outfits unchanged.'
    if goalcrew is not None:task['instruction']+=f' Finish with exactly {goalcrew} total crew (including the pilot).'
    task.update(max_decisions=100 if slug in ('manifest','rebalance') else 160,time_mode='fixed_update_budget',undo_allowed=False)
    task['rules']='Use native Trading and Hire Crew panels. Trading moves one ton per unmodified click. The Shuttle has 20 tons of cargo capacity; sales free space and provide credits. The simulator advances only during authorized actions; thinking time is frozen. Cargo, final credits, crew when specified, original-ship identity, planet and any loan are checked. Starting stock and crew are fixture endowments, not trade income.'
    task['parameters']=dict(max_updates=15000,update_ms=17,native_fixture='\n'.join(fixture)+'\n',curriculum=curriculum(d,mech,why))
    if key not in ('endless-sky-manifest','endless-sky-rebalance') and not task.get('reference',{}).get('verified_run'): task['reference']=dict(provenance='Source-derived candidate; NOT desktop replay validated. Crew panel/help coordinates require GUI confirmation.',viewport=[1100,752],actions=actions)
    task['reference']['feasibility']=dict(witness_cargo=final,expected_final_credits_at_pinned_base_prices=balance,price_source='pinned data/map systems.txt: system Rutilicus; live prices must be confirmed by GUI replay',gui_verified=True if task.get('reference',{}).get('verified_run') else ('legacy reference only' if key in ('endless-sky-manifest','endless-sky-rebalance') else False))
    es[key]=task
addes('manifest','easy',{},dict(Food=8,Metal=4),'Buy exactly 8 tons of Food and 4 tons of Metal.',['two_category_purchase'],'Independent purchases, spare capacity and generous cash allow correction.')
addes('rebalance','easy',dict(Clothing=4),dict(Food=2,Metal=3),'Sell the initial 4 Clothing; finish with exactly 2 Food and 3 Metal.',['sell_then_buy'],'One unwanted cargo category with ample cash and space.')
addes('clear-hold','easy',dict(Clothing=5,Metal=3),{},'Liquidate all starting commodities (5 Clothing and 3 Metal), leaving an empty hold.',['liquidation'],'Recognize sale direction and empty-hold completion; no allocation choices.',floor=32000)
addes('hire-relief','easy',{}, {},'Hire one extra crew member for the empty Shuttle.',['crew_management'],'Single native hiring operation; no cargo or credit dependency.',goalcrew=2)
addes('medical-kit','easy',{},dict(Medical=4),'Prepare exactly 4 tons of Medical supplies in the empty hold.',['commodity_selection'],'Identify a less familiar commodity row, without scarce resources.')
addes('full-hold-exchange','medium',dict(Clothing=20),dict(Food=10,Metal=10),'Replace the full hold of 20 Clothing with exactly 10 Food and 10 Metal.',['capacity_release','replacement_manifest'],'A full hold blocks purchases until sales release capacity.')
addes('retain-equipment','medium',dict(Equipment=6,Clothing=8,Metal=4),dict(Equipment=6,Medical=6),'Finish with exactly 6 Equipment and 6 Medical; initial cargo is 6 Equipment, 8 Clothing and 4 Metal.',['selective_liquidation','retained_inventory'],'Must distinguish stock to retain from stock to sell before buying replacements.')
addes('reduce-payroll','medium',dict(Food=6),dict(Food=6,Metal=4),'Reduce the crew of 4 to the pilot alone and add 4 Metal while retaining 6 Food.',['crew_management','retained_inventory'],'Two different native panels and an exact retained-cargo constraint.',crew=4,goalcrew=1)
addes('economy-basket','medium',{}, {},'Buy a total of exactly 12 tons drawn only from Food and Clothing, with at least 4 tons of each. Starting cash is 23,500 credits.',['allocation_choice','cash_constraint'],'Several cargo allocations satisfy volume; price differences and the reserve constrain choices.',credits=23500,basket=dict(Food=4,Clothing=4),total=12,witness=dict(Food=4,Clothing=8))
addes('fund-medical','medium',{'Luxury Goods':8},dict(Medical=10),'Starting with 8 Luxury Goods and only 1,000 credits, sell that stock to fund exactly 10 Medical.',['sale_finances_purchase','cash_constraint'],'Purchase depends on converting endowed stock to spendable cash first.',credits=1000,floor=4000)
addes('relief-choice','hard',{'Luxury Goods':10,'Metal':10},dict(Metal=4), 'From a full hold of 10 Luxury Goods and 10 Metal, retain exactly 4 Metal and load exactly 16 additional tons drawn only from Food and Medical, with at least 6 of each. Starting cash is 1,000.',['capacity_release','sale_finances_purchase','allocation_choice','retained_inventory'],'Couples sales, reserved stock, full-hold allocation and a cash reserve; feasible substitutions have different costs.',credits=1000,floor=8000,basket=dict(Food=6,Medical=6),total=16,witness=dict(Food=10,Medical=6))
addes('crew-and-full-manifest','hard',dict(Clothing=20),dict(Medical=8,Equipment=8,Food=4),'Starting with 20 Clothing, 16,000 credits and a crew of 4, prepare exactly 8 Medical, 8 Equipment and 4 Food and reduce total crew to 2.',['capacity_release','three_category_manifest','crew_management','cash_constraint'],'Three-category full-capacity replacement plus staffing requires preserving both resource and panel state.',credits=16000,floor=9900,crew=4,goalcrew=2)
addes('industrial-allocation','hard',dict(Food=10,Clothing=10),{},'Starting with 20,000 credits and a full hold (10 Food, 10 Clothing), replace all cargo with exactly 20 tons drawn only from Equipment, Industrial and Electronics, at least 4 of each.',['three_way_allocation','capacity_release','cash_constraint'],'A full hold and three minimums make allocation interdependent; expensive mixes violate the cash reserve.',credits=20000,floor=11900,basket=dict(Equipment=4,Industrial=4,Electronics=4),total=20,witness=dict(Equipment=12,Industrial=4,Electronics=4))
addes('premium-swap','hard',{'Heavy Metals':8,'Medical':6,'Food':6}, {'Medical':6,'Electronics':6,'Luxury Goods':8},'Starting with 8 Heavy Metals, 6 Medical and 6 Food, retain exactly 6 Medical and replace the rest with exactly 6 Electronics and 8 Luxury Goods. Starting cash is 15,000.',['selective_liquidation','capacity_release','high_value_purchase','cash_constraint'],'Retained medical stock consumes capacity while high-value replacements consume most available trade proceeds.',credits=15000,floor=9900)
addes('staffed-relief-basket','hard',{'Luxury Goods':12,'Clothing':8},dict(Equipment=4),'Starting with 12 Luxury Goods, 8 Clothing, 500 credits and the pilot alone, prepare exactly 4 Equipment plus 16 tons drawn only from Food and Medical, at least 6 of each; hire two extra crew.',['sale_finances_purchase','allocation_choice','capacity_release','crew_management'],'Cash must first be released; allocation, exact retained-free manifest and staffing span independent panels.',credits=500,floor=7000,goalcrew=3,basket=dict(Food=6,Medical=6),total=16,witness=dict(Food=10,Medical=6))
assert len(es)==15;write('endless_sky',es)
# OpenTTD
p=ROOT/'game_packages/openttd/tasks.json';old=json.loads(p.read_text());ot={}
def addot(slug,d,desc,mech,why,gaps=(),orders=('west','east'),central=False,detour=False,full=False,stopped=False,depot=False,floor=45000,exact=False):
    key='openttd-'+slug; fixture=dict(gaps=list(gaps),orders=list(orders),central=central,detour=detour,full_load=full)
    goal=dict(central=central,normal_loading=full,stopped=stopped,depot=depot)
    if exact or full:goal['orders']=['west','central','east'] if central else ['west','east']
    task=old.get(key,dict(game='OpenTTD',game_id=slug))
    task['instruction']=desc+' Make the same Inspection Bus actually stop at West Stop and East Stop'+(' and Central Stop' if central else '')+'. Repair every marked road section.'
    if exact or full:task['instruction']+=' Finish with exactly this repeating explicit (user-defined) station-order list: '+('West Stop, Central Stop, East Stop.' if central else 'West Stop, East Stop.')
    if full:task['instruction']+=' Set all station orders to load if available (no full-load orders).'
    if depot:task['instruction']+=' After completing all required visits, return the bus to its depot and stop it inside.'
    elif stopped:task['instruction']+=' After completing all required visits, stop the bus.'
    task['instruction']+=f' Keep at least GBP {floor:,} cash throughout, never borrow, and preserve the original bus and all required stops.'
    task['rules']='Use the original road-building, vehicle and order windows. These are inspection visits, not passenger-delivery contracts. The bus begins stopped in its depot; stops have no guaranteed passenger supply. Use wait to advance time; simulation is frozen while thinking. Road repairs are marked. Do not load, restart or switch game. Native station visits, marked road connections, specified order settings and final bus state are checked. Automatically generated implicit service entries are recorded separately and do not count as user-defined explicit orders.'
    task.update(max_decisions=(120 if slug=='dispatch' else 200) if slug in ('dispatch','road-gap-1','road-gap-2') else (280 if d=='hard' else 220),time_mode='controlled_updates',undo_allowed=False)
    task['parameters']=dict(seed=20260914,max_updates=12000 if slug in ('dispatch','road-gap-1','road-gap-2') else 20000,cash_floor=floor,fixture=fixture,goal=goal,curriculum=curriculum(d,mech,why))
    if key not in old:task['reference']=dict(provenance='Author solution intent; needs desktop coordinate capture and replay. No successful GUI replay claimed.',viewport=[1024,672],actions=[],solution_intent=desc,verification_status='pending_gui_reference')
    ot[key]=task
addot('dispatch','easy','The complete route already has both orders; dispatch the bus.',['dispatch'],'One operational control with no repair or planning prerequisite.')
addot('road-gap-1','easy','Restore the one marked gap in the straight road and dispatch the bus.',['road_repair','dispatch'],'Single visible infrastructure defect; route orders are already correct.',gaps=[24])
addot('road-gap-2','easy','Restore the adjacent marked road gaps and dispatch the bus.',['road_repair','dispatch'],'One contiguous construction gesture repairs the defect; no branch or schedule reasoning.',gaps=[23,24])
addot('missing-east-order','easy','The road is complete but only West Stop is ordered. Add East Stop to the schedule and dispatch.',['order_editing','dispatch'],'One missing order on a complete two-stop network.',orders=['west'],exact=True)
addot('inspection-stop','easy','Run the already configured complete route, then halt the bus after both visits.',['dispatch','final_state_control'],'An observation-dependent final stop, with generous time and no infrastructure uncertainty.',stopped=True)
addot('full-load-deadlock','medium','The West order incorrectly demands a full load at an empty inspection stop. Correct the loading policy and dispatch.',['order_policy','deadlock_recovery'],'Must diagnose the difference between running and progressing; waiting alone cannot resolve full load.',full=True)
addot('central-extension','medium','Central Stop exists between West and East but is omitted from the order list. Add it between the other stops.',['order_insertion','three_stop_service'],'Driving through a stop does not prove service; insertion position and actual visits matter.',central=True,exact=True)
addot('detour-repair','medium','The road follows a U-shaped southern detour; repair its marked north-south gap and dispatch.',['bent_network','road_orientation'],'Two road orientations and a detour replace the straight-line gesture.',detour=True)
addot('inspection-return','medium','Run the complete two-stop route and bring the bus back to its depot after inspection.',['dispatch','depot_routing','final_state_control'],'Return-to-depot interrupts the service loop; it must follow both actual visits.',stopped=True,depot=True)
addot('repair-and-schedule','medium','A road gap and a missing East Stop order both prevent completion. Repair the road and complete the schedule.',['road_repair','order_editing'],'Independent physical and schedule defects require both repairs before service can succeed.',gaps=[24],orders=['west'],exact=True)
addot('detour-central-return','hard','Central Stop lies on the southern detour, the detour has a marked gap, and Central is omitted from the orders. Restore and complete this three-stop inspection.',['bent_network','order_insertion','depot_routing'],'Physical repair, schedule order and three visit evidence all precede safe depot return.',detour=True,central=True,exact=True,stopped=True,depot=True)
addot('deadlock-repair-return','hard','Repair the marked road gap and remove West Stop’s full-load demand before conducting inspection.',['road_repair','deadlock_recovery','depot_routing'],'A visible infrastructure defect masks an independent schedule deadlock; return too early loses the required visit.',gaps=[24],full=True,stopped=True,depot=True)
addot('reorder-three-stop','hard','The complete three-stop road has an initial East, West order list; Central is missing. Rebuild the repeating list as West, Central, East and halt after all three visits.',['order_reordering','order_insertion','three_stop_service','final_state_control'],'Editing an existing wrong order list needs selection, deletion/insertion and exact final order validation.',orders=['east','west'],central=True,exact=True,stopped=True)
addot('detour-budget','hard','On the southern detour, repair its marked gap and correct the West full-load order, then complete inspection under a tight cash reserve.',['bent_network','deadlock_recovery','cash_constraint'],'Two failure mechanisms combine with reduced construction recovery room; gratuitous rebuilding can breach reserve.',detour=True,full=True,floor=49000)
addot('three-stop-recovery','hard','The straight road has a marked gap; the initial East, West schedule omits Central and West demands full load. Repair infrastructure and reconstruct a normal-loading West, Central, East service.',['road_repair','order_reordering','deadlock_recovery','three_stop_service'],'Three independent defects must be separated; success requires both exact order policy and observed three-stop service.',gaps=[23],orders=['east','west'],central=True,full=True,exact=True)
assert len(ot)==15;write('openttd',ot)
print('Authored 15 Endless Sky and 15 OpenTTD tasks, each with 5 easy / 5 medium / 5 hard.')
