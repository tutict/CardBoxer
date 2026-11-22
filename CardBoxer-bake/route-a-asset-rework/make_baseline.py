"""冻结 A 路线的输入 sha256 与「游戏源码零改动」基线。

只读源资产 / C 路线归档 / 可运行工程，写 baseline.json 到本工作区。
条目数由脚本现算，不写死数字。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")

INPUTS = [
    "baked2.json",
    "3d-attack-gifs/apose_joints.json",
    "3d-attack-gifs/puppet_mapping.json",
    "foe-blender-modeling-v1/foe-V1.blend",
    "foe-blender-modeling-v1/foe-front.png",
    "route-c-real-3d-fix/c_build.py",
    "route-c-deformation-v2/c2_build.py",
    "route-c-deformation-v2/c2_build.json",
    "route-c-deformation-v2/baseline.json",
    "route-c-deformation-v2/frames/jab07-B_x15.png",
    "route-c-deformation-v2/frames/cross11-B_x15.png",
    "route-c-deformation-v2/frames/wave18-B_x15.png",
]

GAME_PATTERNS = ("scripts/*.gd", "tests/*.gd", "data/*.json",
                 "scenes/*.tscn", "project.godot",
                 "assets/portraits/*.png", "assets/portraits/*.import")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    missing = []
    inputs = {}
    for rel in INPUTS:
        p = BAKE / rel
        if not p.is_file():
            missing.append(rel)
            continue
        inputs[rel] = {"bytes": p.stat().st_size, "sha256": sha256(p)}

    game = {}
    for pat in GAME_PATTERNS:
        for p in sorted(GAME.glob(pat)):
            if p.is_file():
                game[p.relative_to(GAME).as_posix()] = {
                    "bytes": p.stat().st_size, "sha256": sha256(p)}

    out = {"inputs": inputs, "game": game, "missing": missing}
    (HERE / "baseline.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BASELINE inputs={len(inputs)} game={len(game)} missing={missing}")
    print("BASELINE_OK" if not missing and game else "BASELINE_FAILED")
    return 0 if not missing and game else 1


if __name__ == "__main__":
    raise SystemExit(main())
