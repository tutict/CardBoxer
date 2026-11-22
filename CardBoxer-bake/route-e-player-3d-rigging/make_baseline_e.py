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
GAME = BAKE.parent / "CardBoxer"
OUT = HERE / "baseline_e.json"

SINGLES = {
    "c_route_filelist": BAKE / "route-c-gltf-godot-probe" / "file-list.txt",
    "d_route_filelist": BAKE / "route-d-creative-review-captures" / "file-list.txt",
    "a_route_blend": BAKE / "route-a-asset-rework" / "foe-deformable-continuous-shell.blend",
    "v4b_glb": BAKE / "3d-model-probe-v4b" / "artifact_03.glb",
    "apose_joints": BAKE / "3d-attack-gifs" / "apose_joints.json",
    "puppet_mapping": BAKE / "3d-attack-gifs" / "puppet_mapping.json",
    "baked2": BAKE / "baked2.json",
    "c_build": BAKE / "route-c-real-3d-fix" / "c_build.py",
    "c2_build": BAKE / "route-c-deformation-v2" / "c2_build.py",
    "a_build": BAKE / "route-a-asset-rework" / "a_build.py",
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
