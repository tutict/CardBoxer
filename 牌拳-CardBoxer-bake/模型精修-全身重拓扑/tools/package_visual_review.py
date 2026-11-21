"""Build review boards and timed GIFs only from recorded real rendered images."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

TASK = Path(__file__).resolve().parent.parent
OUT = TASK / "reports/visual-review"
FONT = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
SMALL = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)
BG = "#272c33"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def tile(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        picture = ImageOps.contain(source.convert("RGBA"), size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, BG)
    canvas.paste(picture, ((size[0] - picture.width) // 2, (size[1] - picture.height) // 2), picture)
    return canvas


def compare(role: str, feature: str, files: list[tuple[str, Path]], size=(500, 460)) -> Path:
    board = Image.new("RGB", (size[0] * len(files), size[1] + 35), BG)
    draw = ImageDraw.Draw(board)
    for index, (label, path) in enumerate(files):
        board.paste(tile(path, size), (index * size[0], 35))
        draw.text((index * size[0] + 12, 8), label, fill="white", font=FONT)
    path = OUT / (role + "-" + feature + ".png")
    board.save(path)
    return path


def authoring_boards() -> list[str]:
    files = []
    for role in ("player", "foe"):
        source = TASK / "authoring" / role
        files.append(str(compare(role, "full-and-wire", [("Original", source / "source-full.png"),
                    ("Refined", source / "candidate-full.png"), ("Editable wire", source / "candidate-wireframe.png")], (430, 490))))
        feature = "face" if role == "player" else "armor"
        files.append(str(compare(role, feature, [("Original", source / ("source-" + feature + ".png")),
                    ("Refined", source / ("candidate-" + feature + ".png"))], (760, 532))))
        files.append(str(compare(role, "hands", [("Original", source / "source-hands.png"),
                    ("Refined", source / "candidate-hands.png"), ("New finger loops", source / "candidate-hand-wireframe.png")], (500, 400))))
    return files


def motion_boards(name: str) -> list[str]:
    capture = read(TASK / "shots" / name / "manifest.json")
    if not capture.get("completed") or capture.get("display_server") == "headless":
        raise RuntimeError("Motion evidence was not rendered to completion")
    files = []
    for role in ("player", "foe"):
        for facing in (1, -1):
            for page in range(4):
                clips = capture["clips"][page * 5:(page + 1) * 5]
                if not clips:
                    continue
                rows = [[r for r in capture["rows"] if r["role"] == role and r["relative_facing"] == facing
                         and r["clip"] == clip] for clip in clips]
                columns = max(len(row) for row in rows)
                board = Image.new("RGB", (columns * 180, len(rows) * 220 + 32), BG)
                draw = ImageDraw.Draw(board)
                draw.text((10, 6), f"{role} | relative facing {facing} | phase/fractional render samples", fill="white", font=FONT)
                for row_index, (clip, entries) in enumerate(zip(clips, rows)):
                    for col, entry in enumerate(sorted(entries, key=lambda r: r["frame"])):
                        x, y = col * 180, row_index * 220 + 32
                        board.paste(tile(Path(entry["path"]), (180, 190)), (x, y + 30))
                        label = f"{clip} f{entry['frame']:.1f} g{entry['hand_grip'][0]:.2f}"
                        draw.text((x + 5, y + 7), label, fill="white", font=SMALL)
                path = OUT / f"motions-{role}-facing{facing}-page{page + 1}.png"
                board.save(path)
                files.append(str(path))
    return files


def match_preview(name: str) -> dict:
    capture_path = TASK / "shots" / name / "match.json"
    capture = read(capture_path)
    if capture.get("phase") != "match_over":
        raise RuntimeError("Normal match did not complete")
    if not all(row["positions"] == [[430.0, 520.0], [850.0, 520.0]] for row in capture["rows"]):
        raise RuntimeError("Normal logical spawn/position contract changed")
    frames, durations, selected = [], [], []
    for turn in (1, 2):
        cycle = [row for row in capture["rows"] if row["round"] == 1 and row["turn"] == turn
                 and row["phase"] == "fight" and row["taikou"] == "resolve" and row["exchange_time"] <= 1.22]
        if len(cycle) < 5:
            raise RuntimeError("Continuous normal-spawn exchange evidence missing")
        for index, row in enumerate(cycle):
            with Image.open(row["file"]) as source:
                picture = source.convert("RGB").crop((270, 285, 1010, 547))
            frame = Image.new("RGB", (740, 290), BG)
            frame.paste(picture, (0, 28))
            ImageDraw.Draw(frame).text((10, 5), f"Refined models | normal match | turn {turn} | t={row['exchange_time']:.3f}s", font=FONT, fill="white")
            delta = cycle[index + 1]["frame"] - row["frame"] if index + 1 < len(cycle) else 3
            frames.append(frame)
            durations.append(max(10, round(delta / 60 * 100) * 10))
            selected.append({"frame": row["frame"], "time": row["exchange_time"], "source": row["file"]})
    for filename, multiplier in (("normal-match.gif", 1), ("normal-match-slow.gif", 2)):
        frames[0].save(OUT / filename, save_all=True, append_images=frames[1:],
                       duration=[d * multiplier for d in durations], loop=0, disposal=2, optimize=False)
    frames[0].save(OUT / "normal-match-cover.png")
    with Image.open(capture["rows"][-1]["file"]) as source:
        source.save(OUT / "completed-match.png")
    return {"capture": str(capture_path), "phase": capture["phase"], "engine_frames": capture["frames"],
            "capture_shots": capture["shots"], "normal_positions_exact": True,
            "gif_frames": len(frames), "normal_duration_ms": sum(durations), "slow_multiplier": 2,
            "source_fps": 60, "gif_quantization_ms": 10, "selected": selected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motion", required=True)
    parser.add_argument("--match", required=True)
    args = parser.parse_args()
    for value in (args.motion, args.match):
        if not value.replace("-", "").replace("_", "").isalnum():
            raise RuntimeError("Capture name must stay inside the task")
    OUT.mkdir(parents=True, exist_ok=True)
    boards = authoring_boards() + motion_boards(args.motion)
    match = match_preview(args.match)
    sources = {str(path.relative_to(TASK)): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in (TASK / "project/assets/3d/player-rigged.glb", TASK / "project/assets/3d/foe-rigged.glb",
                            TASK / "project/data/model_profile_3d.json", TASK / "project/data/combat_motion_3d.json")}
    payload = {"boards": boards, "match": match, "source_sha256": sources,
               "visual_acceptance": "pending independent/root inspection; boards are evidence, not automatic approval"}
    (OUT / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VISUAL_REVIEW_PACKAGE: {len(boards)} real-image boards, normal+2x slow match GIF")


if __name__ == "__main__":
    main()
