"""E 路线开工前冻结输入指纹，供 verify_e.py 判「全程零污染」。

冻结：可运行游戏工程逐文件 sha256、C/D 路线已交付文件清单整体 sha256、
A 路线可变形 .blend、玩家 V4b GLB、以及复用的动作表/标定/映射/链路脚本。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
OUT = HERE / "baseline_e.json"

SINGLES = {
    "c_route_filelist": BAKE / "C路线-glTF-Godot探针" / "文件清单.txt",
    "d_route_filelist": BAKE / "D路线-CreativeReview与引擎截帧" / "文件清单.txt",
    "a_route_blend": BAKE / "A路线-资产重做" / "对手怪-可变形连续壳.blend",
    "v4b_glb": BAKE / "3D模型探针V4b" / "artifact_03.glb",
    "apose_joints": BAKE / "3D攻击GIF" / "apose_joints.json",
    "puppet_mapping": BAKE / "3D攻击GIF" / "puppet_mapping.json",
    "baked2": BAKE / "baked2.json",
    "c_build": BAKE / "C路线-真3D修复" / "c_build.py",
    "c2_build": BAKE / "C路线-变形质量V2" / "c2_build.py",
    "a_build": BAKE / "A路线-资产重做" / "a_build.py",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    game: dict[str, dict] = {}
    for p in sorted(GAME.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(GAME).as_posix()
        if rel.startswith(".godot/"):
            continue
        game[rel] = {"bytes": p.stat().st_size, "sha256": sha256(p)}

    singles = {}
    for key, p in SINGLES.items():
        assert p.is_file(), f"missing {key}: {p}"
        blob = p.read_bytes()
        item = {"path": str(p), "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest()}
        if key.endswith("filelist"):
            item["entries"] = sum(
                1 for line in blob.decode("utf-8").splitlines()
                if line.startswith("WORK/"))
        singles[key] = item

    out = {"game": game, "game_root": str(GAME), "singles": singles}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"GAME_FILES={len(game)} SINGLES={len(singles)} "
          f"C_ENTRIES={singles['c_route_filelist']['entries']} "
          f"D_ENTRIES={singles['d_route_filelist']['entries']} "
          f"V4B_GLB={singles['v4b_glb']['bytes']} BASELINE_E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
