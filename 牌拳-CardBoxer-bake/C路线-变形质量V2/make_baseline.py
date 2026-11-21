"""V2 只读基线：采集输入指纹与游戏源码 sha256，不写任何既有归档。

用途：证明本轮改的是工作区新文件，源 .blend / 动作表 / C 路线归档 /
可运行工程一字节未动。判据 V2-xx 会读这份基线逐项对账。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")

INPUTS = {
    "baked2.json": BAKE / "baked2.json",
    "apose_joints.json": BAKE / "3D攻击GIF" / "apose_joints.json",
    "puppet_mapping.json": BAKE / "3D攻击GIF" / "puppet_mapping.json",
    "对手怪V1.blend": BAKE / "对手怪Blender建模V1" / "对手怪V1.blend",
    "C路线/c_build.py": BAKE / "C路线-真3D修复" / "c_build.py",
    "C路线/c_build.json": BAKE / "C路线-真3D修复" / "c_build.json",
    "C路线/C路线-验证记录.txt": BAKE / "C路线-真3D修复" / "C路线-验证记录.txt",
}

GAME_FILES = [
    "scripts/arena.gd", "scripts/fighter.gd", "scripts/hud.gd",
    "scripts/fighter_skin.gd", "scripts/fx_layer.gd", "scripts/card_data.gd",
    "scripts/taikou_rage.gd", "scripts/battle_motion_p0.gd",
    "scripts/battle_rhythm.gd", "data/card_motion.json",
    "project.godot", "scenes/main.tscn",
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    inputs = {}
    missing = []
    for key, p in INPUTS.items():
        if not p.is_file():
            missing.append(key)
            continue
        inputs[key] = {"path": str(p.relative_to(BAKE)).replace("\\", "/"),
                       "bytes": p.stat().st_size, "sha256": sha256(p)}
    game = {}
    for rel in GAME_FILES:
        p = GAME / rel
        if not p.is_file():
            missing.append("GAME/" + rel)
            continue
        game[rel] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
    out = {"inputs": inputs, "game": game, "missing": missing}
    (HERE / "基线.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"INPUTS={len(inputs)} GAME={len(game)} MISSING={len(missing)}")
    if missing:
        print("MISSING_LIST", missing)
        return 1
    print("BASELINE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
