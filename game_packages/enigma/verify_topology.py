"""Abstract cell-space feasibility only; does NOT certify native marble physics.
XML is parsed, mechanisms match upstream definitions, and a box-push/reachability
search finds a final connected region adjacent to every Oxyd stone.
"""
import json,re
from collections import deque
from pathlib import Path
from xml.etree import ElementTree as ET
P=Path(__file__).parent
D=[(1,0),(-1,0),(0,1),(0,-1)]
results=[]
for path in sorted((P/'levels').glob('*.xml')):
    tree=ET.fromstring(path.read_text());lua=tree.find('.//{*}luamain').text
    rows=json.loads('['+re.search(r'wo\(ti, [\'\"] [\'\"], \{(.*?)\}\)',lua,re.S).group(1)+']')
    cells={(x,y):c for y,row in enumerate(rows) for x,c in enumerate(row)}
    start=next(p for p,c in cells.items() if c=='@');initial=tuple(sorted(p for p,c in cells.items() if c=='B'))
    oxyd={p for p,c in cells.items() if c in 'OPQR'}
    def flood(at,boxes):
        reached={at};gates=set();keys=set();touched=set()
        while True:
            before=(len(reached),len(gates),len(keys));queue=deque(reached)
            while queue:
                x,y=queue.popleft()
                c=cells[x,y]
                if c in 'kl':keys.add(c)
                for dx,dy in D:
                    p=x+dx,y+dy;c=cells.get(p,'#')
                    if c in 'OPQR':touched.add(p)
                    if c in 'ST':gates.add('D' if c=='S' else 'E')
                    if c in 'KL' and ('k' if c=='K' else 'l') in keys:gates.add('D' if c=='K' else 'E')
                    if p in boxes or c in '#~OPQRSTKL' or c in 'DE' and c not in gates:continue
                    if p not in reached:reached.add(p);queue.append(p)
            if before==(len(reached),len(gates),len(keys)):break
        return reached,touched,gates
    queue=deque([(start,initial,[])]);seen=set();answer=None
    while queue:
        at,boxes,pushes=queue.popleft();reach,touched,gates=flood(at,boxes)
        signature=(min(reach),boxes)
        if signature in seen:continue
        seen.add(signature)
        if touched==oxyd:answer=(pushes,len(reach),sorted(gates));break
        for x,y in boxes:
            for dx,dy in D:
                behind=(x-dx,y-dy);ahead=(x+dx,y+dy)
                if behind not in reach or ahead in boxes:continue
                c=cells.get(ahead,'#')
                if c in '#~OPQRSTKL' or c in 'DE' and c not in gates:continue
                moved=tuple(sorted((set(boxes)-{(x,y)})|{ahead}))
                queue.append(((x,y),moved,pushes+[[[x,y],list(ahead)]]))
    assert answer is not None,path.name
    results.append({'level':path.stem,'xml_well_formed':True,'abstract_accessible_all_oxyd':True,'box_push_witness':answer[0],'reachable_cells_after_controls':answer[1],'open_gates':answer[2],'search_states':len(seen),'native_desktop_verified':False,'scope':'Cell reachability and box clearance; excludes continuous physics, collisions at speed, inventory UI and native object dispatch.'})
(P/'topology-feasibility.json').write_text(json.dumps(results,indent=2)+'\n')
print('15 XML levels parsed; abstract paths and box clearance verified:',len(results))
