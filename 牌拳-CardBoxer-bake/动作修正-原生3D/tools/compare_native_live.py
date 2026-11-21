"""Exact fixed-input gameplay/event comparison across baseline, current off and on."""
import argparse
import json
from pathlib import Path


def compare(left: Path, right: Path) -> dict:
    differences = []
    settled_differences = []
    checked = 0
    for file in sorted(left.glob('*.json')):
        if file.name == 'summary.json': continue
        other = right / file.name
        if not other.exists():
            differences.append({'scenario': file.stem, 'error': 'missing right trace'}); continue
        l, r = json.loads(file.read_text(encoding='utf-8')), json.loads(other.read_text(encoding='utf-8'))
        checked += 1
        # Separate timing-sensitive exact replay from damage/order/result preservation.
        def settled(data):
            events = [{key: value for key, value in event.items() if key != 'tick'} for event in data['events']]
            final = data['gameplay'][-1]
            return {'events': events, 'hp': [final['player']['hp'], final['foe']['hp']],
                    'round_wins': final['round_wins'], 'tk_winner': final['tk_winner'], 'tk_damage': final['tk_damage'],
                    'reveal': final['reveal'], 'tk_rage': final['tk_rage'], 'tk_ex': final['tk_ex']}
        if settled(l) != settled(r):
            settled_differences.append({'scenario': file.stem, 'left': settled(l), 'right': settled(r)})
        for field in ('config', 'events', 'gameplay'):
            if l[field] != r[field]:
                detail = {'scenario': file.stem, 'field': field}
                if field == 'gameplay':
                    for tick, (lt, rt) in enumerate(zip(l[field], r[field])):
                        if lt != rt:
                            detail['tick'] = tick
                            detail['different_keys'] = [key for key in lt if lt[key] != rt.get(key)]
                            detail['left'] = {key: lt[key] for key in detail['different_keys']}
                            detail['right'] = {key: rt[key] for key in detail['different_keys']}
                            break
                    if len(l[field]) != len(r[field]): detail['lengths'] = [len(l[field]), len(r[field])]
                differences.append(detail)
    return {'left': str(left), 'right': str(right), 'checked': checked, 'equal': not differences and checked > 0,
            'differences': differences, 'settled_rules_equal': not settled_differences and checked > 0,
            'settled_rules_differences': settled_differences,
            'comparison_scope': 'Exact gameplay includes hands, timers and hitstop. Settled comparison checks ordered card/hit/super events excluding tick, HP, round wins, ranks, winner, damage, rage and EX.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('left', type=Path); parser.add_argument('right', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(); result = compare(args.left, args.right)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out: args.out.write_text(text, encoding='utf-8')
    print(text)
    raise SystemExit(0 if result['equal'] else 1)
