"""Build labeled pose boards and continuous GIFs from real Godot viewport images.

python native_qa_images.py --capture shots/capture --out reports/boards
Image statistics detect missing renderer output; they do not certify skin quality.
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw


def composited(path: Path, scale: float = 0.64) -> Image.Image:
    image = Image.open(path).convert('RGBA')
    backdrop = Image.new('RGBA', image.size, '#242932')
    backdrop.alpha_composite(image)
    return backdrop.convert('RGB').resize((round(image.width * scale), round(image.height * scale)))


def capture_boards(source: Path, dest: Path) -> dict:
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    if 'error' in manifest:
        raise RuntimeError(manifest['error'])
    groups = defaultdict(list)
    stats = []
    for row in manifest['rows']:
        path = Path(row['path'])
        rgba = np.asarray(Image.open(path).convert('RGBA'))
        alpha = rgba[..., 3] > 8
        stats.append({'path': str(path), 'visible_pixels': int(alpha.sum()),
                      'rgb_std': float(rgba[..., :3][alpha].std()) if alpha.any() else 0.0,
                      'border_pixels': {'left': int(alpha[:, 0].sum()), 'right': int(alpha[:, -1].sum()),
                                        'top': int(alpha[0].sum()), 'bottom': int(alpha[-1].sum())}})
        groups[(row['clip'], row.get('relative_facing', 1))].append(row)
    boards, gifs = [], []
    for (clip, facing), rows in groups.items():
        selected = sorted({r['frame'] for r in rows if r.get('authored_key') or
                           abs(r['frame'] - r['contact_frame']) <= 1 or r['frame'] in (0, max(x['frame'] for x in rows))})
        # One complete phase board with both roles in matching columns.
        columns = min(len(selected), 10)
        tile_w, tile_h = 276, 370
        lines = (len(selected) + columns - 1) // columns
        board = Image.new('RGB', (tile_w * columns, 30 + tile_h * 2 * lines), '#13171e')
        draw = ImageDraw.Draw(board)
        draw.text((10, 8), f'{clip} | relative facing {facing} | imported GLBs / native rest-relative rotations', fill='white')
        lookup = {(r['role'], r['frame']): r for r in rows}
        for i, frame in enumerate(selected):
            x, band = (i % columns) * tile_w, (i // columns) * tile_h * 2
            for role_index, role in enumerate(('player', 'foe')):
                row = lookup[(role, frame)]
                y = 30 + band + role_index * tile_h
                image = composited(Path(row['path']))
                board.paste(image, (x, y + 25))
                tag = ' CONTACT' if frame == row['contact_frame'] else ''
                tag += ' KEY' if row['authored_key'] else ''
                draw.text((x + 5, y + 7), f'{role} f={frame:g}{tag}', fill='#dde3ed')
        board_path = dest / f'{clip}-facing{facing}-board.png'
        board.save(board_path)
        boards.append(str(board_path))
        frames = []
        integer_frames = sorted({r['frame'] for r in rows if r['frame'].is_integer()})
        for frame in integer_frames:
            left = composited(Path(lookup[('player', frame)]['path']), 0.64)
            right = composited(Path(lookup[('foe', frame)]['path']), 0.64)
            animation = Image.new('RGB', (left.width + right.width, left.height + 25), '#242932')
            animation.paste(left, (0, 25)); animation.paste(right, (left.width, 25))
            ImageDraw.Draw(animation).text((7, 7), f'{clip} | player + foe | frame {frame:g}', fill='white')
            frames.append(animation)
        gif_path = dest / f'{clip}-facing{facing}.gif'
        if frames:
            # GIF timing is centiseconds. Alternate 10/20 ms to average 60fps,
            # instead of letting a constant 17 ms silently truncate to 10 ms.
            durations = [max(10, round((i + 1) * 100 / 60) * 10 - round(i * 100 / 60) * 10) for i in range(len(frames))]
            frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=durations, loop=0)
            frames[0].save(dest / f'{clip}-facing{facing}-slow.gif', save_all=True, append_images=frames[1:], duration=50, loop=0)
            gifs.append(str(gif_path))
    return {'renderer': manifest.get('renderer'), 'completed': manifest.get('completed'),
            'boards': boards, 'gifs': gifs, 'image_count': len(stats),
            'empty_or_tiny_images': [s for s in stats if s['visible_pixels'] < 100], 'image_statistics': stats,
            'images_touching_viewport_border': [s for s in stats if any(s['border_pixels'].values())],
            'limitations': 'Rendered image presence only. Human review needed for seams, cloth, foot support, clipping and motion intent.'}


def live_boards(source: Path, dest: Path) -> dict:
    boards, gifs = [], []
    for file in source.glob('*.json'):
        if file.name == 'summary.json':
            continue
        scenario = json.loads(file.read_text(encoding='utf-8'))
        images = scenario.get('images', [])
        if not images:
            continue
        frames = []
        for row in images:
            capture = row['capture']
            if 'player' not in capture or 'foe' not in capture:
                continue
            left = composited(Path(capture['player']['path']), .64)
            right = composited(Path(capture['foe']['path']), .64)
            frame = Image.new('RGB', (left.width + right.width, left.height + 28), '#242932')
            frame.paste(left, (0, 28)); frame.paste(right, (left.width, 28))
            visual = scenario['visuals'][row['tick']]['visuals']
            label = f"{file.stem} | tick {row['tick']}"
            for role in ('player', 'foe'):
                if role in visual:
                    label += f" | {role} {visual[role].get('clip_id')}:{visual[role].get('frame', 0):.1f}"
            ImageDraw.Draw(frame).text((5, 7), label, fill='white')
            frames.append(frame)
        if frames:
            gif_path = dest / (file.stem + '.gif')
            stride = images[1]['tick'] - images[0]['tick'] if len(images) > 1 else 1
            durations = [max(10, round((i + 1) * 100 * stride / 60) * 10 - round(i * 100 * stride / 60) * 10) for i in range(len(frames))]
            frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=durations, loop=0)
            gifs.append(str(gif_path))
            indices = np.linspace(0, len(frames) - 1, min(10, len(frames)), dtype=int)
            board = Image.new('RGB', (frames[0].width * len(indices), frames[0].height), '#242932')
            for col, index in enumerate(indices): board.paste(frames[index], (col * frames[0].width, 0))
            path = dest / (file.stem + '-board.png'); board.save(path); boards.append(str(path))
    return {'gifs': gifs, 'boards': boards, 'limitations': 'Only recorded production samples shown; human review required.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--live', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    result = capture_boards(args.capture, args.out) if args.capture else live_boards(args.live, args.out)
    (args.out / 'image-review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in ('image_statistics', 'images_touching_viewport_border')}, indent=2))
