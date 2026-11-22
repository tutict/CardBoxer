"""Validate timing properties in recorded real-state-machine native samples.

No rendered-image skin assertions: this checks runtime clip/frame and snapshot evidence.
"""
import argparse
import json
from pathlib import Path


def check(source: Path, motion_file: Path) -> dict:
    motion = json.loads(motion_file.read_text(encoding='utf-8'))
    failures, checks, scenarios = [], [], 0
    def expect(ok, name, label, detail=None):
        record = {'scenario': name, 'check': label, 'pass': bool(ok)}
        if detail is not None: record['detail'] = detail
        checks.append(record)
        if not ok: failures.append(record)
    for file in sorted(source.glob('*.json')):
        if file.name == 'summary.json': continue
        data = json.loads(file.read_text(encoding='utf-8'))
        if not data.get('use_3d'): continue
        scenarios += 1
        rows = {r['tick']: r for r in data['visuals'] if not r.get('reset')}
        config = data['config']
        actor = config.get('actor', 'player')
        victim = 'foe' if actor == 'player' else 'player'
        taikou = config.get('mode') == 'taikou'
        for event in data['events']:
            if event['kind'] != 'hit' or event['dodged']: continue
            row = rows[event['tick']]
            role = 'player' if event['player_attacker'] else 'foe'
            target = 'foe' if role == 'player' else 'player'
            snapshots = row.get('snapshots', {})
            card = snapshots.get(role, {}).get('card_id', '')
            # In the delayed-wave scenarios the projectile hit belongs to an older
            # action. The currently playing jab must not be mistaken for its source.
            if taikou or card in ('', 'wave') or '-wave-new-action' in file.stem or '-late-wave-fatal' in file.stem: continue
            visual = row['visuals'].get(role, {})
            contact = motion['roles'][role]['clips'][card]['contact_frame']
            expect(visual.get('clip_id') == card and abs(visual.get('frame', -99) - contact) < 1e-5,
                   file.stem, 'melee hit samples the native contact endpoint',
                   {'tick': event['tick'], 'card': card, 'frame': visual.get('frame'), 'contact': contact})
        if '-wave-new-action' in file.stem or '-late-wave-fatal' in file.stem:
            hits = [e for e in data['events'] if e['kind'] == 'hit']
            cards = [e for e in data['events'] if e['kind'] == 'card']
            expect(bool(hits) and len(cards) >= 2 and cards[1]['tick'] < hits[0]['tick'], file.stem,
                   'wave collides after a newer attacker action begins')
            if hits:
                visual = rows[hits[0]['tick']]['visuals'][actor]
                expect(visual['clip_id'] != 'wave', file.stem, 'late collision does not rewind actor to old wave release')
                expect(visual['clip_id'] == 'jab', file.stem, 'late wave collision preserves currently playing new jab')
        if config.get('fatal'):
            ko_rows = [r for r in rows.values() if r['visuals'].get(victim, {}).get('clip_id') == 'ko']
            expect(bool(ko_rows), file.stem, 'fatal victim renders KO')
            if ko_rows:
                expect(abs(ko_rows[-1]['visuals'][victim]['frame'] - 27) < 1e-5, file.stem,
                       'terminal KO reaches final native frame 27')
                full = [r for r in ko_rows if r['visuals'][victim]['frame'] >= 26.999]
                expect(len(full) >= 2, file.stem, 'final KO frame holds across multiple production ticks')
            reset = [r for r in data['visuals'] if r.get('reset')]
            expect(bool(reset) and all(reset[-1]['visuals'].get(role, {}).get('clip_id') != 'ko'
                                      for role in ('player', 'foe')), file.stem, 'round reset clears stale KO')
        if taikou and config.get('winner') in ('player', 'enemy'):
            winning = 'player' if config['winner'] == 'player' else 'foe'
            contact_rows = []
            for row in rows.values():
                visual = row['visuals'].get(winning, {})
                clip = motion['roles'][winning]['clips'].get(visual.get('clip_id'), {})
                contact = clip.get('contact_frame', -1)
                if contact >= 0 and abs(visual.get('frame', -99) - contact) < 1e-5:
                    contact_rows.append(row)
            expect(len(contact_rows) >= 10, file.stem, 'taikou contact is visibly held, not a one-frame skip',
                   {'contact_tick_count': len(contact_rows)})
    return {'source': str(source.resolve()), 'scenario_count': scenarios, 'checks': checks, 'failures': failures,
            'passed': bool(checks) and not failures,
            'limitations': 'Runtime pose/clip timing evidence only; rendered skins need human inspection.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path); parser.add_argument('motion', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); result = check(args.source, args.motion)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'checks'}, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
