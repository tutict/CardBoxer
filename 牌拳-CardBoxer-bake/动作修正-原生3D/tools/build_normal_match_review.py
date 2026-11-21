"""Review the first two continuous exchanges at their recorded engine timing."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

TASK = Path(__file__).resolve().parent.parent


def build(name: str) -> None:
    source = TASK / 'shots' / name / 'match.json'
    capture = json.loads(source.read_text(encoding='utf-8'))
    rows = capture['rows']
    out = TASK / 'reports' / (name + '-review')
    out.mkdir(exist_ok=True)
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 15)
    crop = (270, 285, 1010, 547)
    times = [0.0, .10, .20, .35, .48, .56, .65, .80, 1.0, 1.12, 1.50, 1.85]
    all_frames, all_durations = [], []
    selected = []
    for turn in (1, 2):
        cycle = [r for r in rows if r['round'] == 1 and r['turn'] == turn
                 and r['phase'] == 'fight' and r['taikou'] == 'resolve']
        if not cycle:
            raise RuntimeError(f'No continuously captured exchange for turn {turn}')
        board = Image.new('RGB', (1440, 4 * 197), '#242932')
        for index, target in enumerate(times):
            row = min(cycle, key=lambda r: abs(r['exchange_time'] - target))
            with Image.open(row['file']) as im:
                tile = im.convert('RGB').crop(crop).resize((480, 170), Image.Resampling.LANCZOS)
            x, y = (index % 3) * 480, (index // 3) * 197
            board.paste(tile, (x, y + 27))
            label = f"turn {turn} | t={row['exchange_time']:.3f}s | frame {row['frame']}"
            ImageDraw.Draw(board).text((x + 8, y + 4), label, font=font, fill='white')
            selected.append({'turn': turn, 'target_time': target, 'row': row})
        board.save(out / f'turn-{turn}-flow.png')
        segment = [r for r in cycle if r['exchange_time'] <= 1.22]
        for index, row in enumerate(segment):
            with Image.open(row['file']) as im:
                frame = Image.new('RGB', (740, 290), '#242932')
                frame.paste(im.convert('RGB').crop(crop), (0, 28))
            ImageDraw.Draw(frame).text((10, 5), f"Natural V2 | normal spawn | turn {turn} | t={row['exchange_time']:.3f}s",
                                      font=font, fill='white')
            delta = segment[index + 1]['frame'] - row['frame'] if index + 1 < len(segment) else 3
            all_frames.append(frame)
            all_durations.append(max(10, round(delta / 60 * 100) * 10))
    all_frames[0].save(out / 'normal-spawn-flow.gif', save_all=True, append_images=all_frames[1:],
                       duration=all_durations, loop=0, disposal=2, optimize=False)
    with Image.open(rows[-1]['file']) as im:
        im.save(out / 'match-result.png')
    # All captured logical positions must stay at the unchanged normal spawn.
    positions_ok = all(r['positions'] == [[430.0, 520.0], [850.0, 520.0]] for r in rows)
    result = {
        'capture': str(source), 'frames': capture['frames'], 'shots': capture['shots'],
        'phase': capture['phase'], 'normal_logical_positions_unchanged': positions_ok,
        'review_source_motion_sha256': hashlib.sha256((TASK / 'project/data/combat_motion_3d.json').read_bytes()).hexdigest(),
        'selected': selected,
        'visual_acceptance': 'pending root inspection',
    }
    (out / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if capture['phase'] != 'match_over' or not positions_ok:
        raise RuntimeError('Full-match/normal-spawn acceptance failed')
    print(f"NORMAL_SPAWN_REVIEW: match_over, {capture['frames']} frames, {capture['shots']} shots, positions preserved")
    print(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='natural-v2-normal-match')
    args = parser.parse_args()
    if not args.name.replace('-', '').replace('_', '').isalnum():
        raise RuntimeError('Name must remain inside the task')
    build(args.name)
