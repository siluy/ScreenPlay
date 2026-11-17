"""Trusted scenario setup and predicates over original Singularity objects.

Fixtures are applied once before the first observation. No rule or price changes.
"""
from singularity.code import g, base, item


def apply_fixture(parameters):
    fixture = parameters.get('initial', {})
    if not fixture:
        return
    if 'cash' in fixture:
        g.pl.cash = int(fixture['cash'])
    for technology in fixture.get('technologies', []):
        g.pl.techs[technology].finish(is_player=False)
    if 'bases' in fixture:
        for location in g.pl.locations.values():
            location.bases.clear()
        for index, record in enumerate(fixture['bases']):
            obj = base.Base(record.get('name', 'Scenario base %d' % (index + 1)),
                            g.base_type[record['type']], built=True)
            g.pl.locations[record['location']].add_base(obj)
            for slot, equipment in record.get('items', {}).items():
                obj.items[slot] = item.Item(g.items[equipment['type']], base=obj,
                                            count=equipment.get('count', 1))
                obj.items[slot].finish(is_player=False)
            obj.recalc_cpu()
            obj.check_power()
    g.pl.recalc_cpu()


def goal_status(parameters):
    bases = list(g.all_bases())
    completed = [b for b in bases if b.done]
    technologies = [key for key, value in g.pl.techs.items() if value.done]
    checks = [t in technologies for t in parameters.get('technologies', [])]
    checks.append(len(completed) >= parameters.get('built_bases', 1))
    target = parameters.get('goal', {})
    if 'cash' in target:
        checks.append(g.pl.cash >= target['cash'])
    if 'cpu' in target:
        checks.append(g.pl.available_cpus[0] >= target['cpu'])
    if 'regions' in target:
        checks.append(len({b.location.id for b in completed}) >= target['regions'])
    for record in target.get('bases', []):
        matching = [b for b in completed if
                    ('type' not in record or b.spec.id == record['type']) and
                    ('location' not in record or b.location.id == record['location'])]
        for slot, equipment in record.get('items', {}).items():
            matching = [b for b in matching if b.items.get(slot) and b.items[slot].done
                        and b.items[slot].spec.id == equipment['type']
                        and b.items[slot].count >= equipment.get('count', 1)]
        checks.append(len(matching) >= record.get('count', 1))
    return all(checks), sum(checks) / len(checks)
