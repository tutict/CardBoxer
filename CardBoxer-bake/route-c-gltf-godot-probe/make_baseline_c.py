"""冻结 C 路线的输入 sha256 与「可运行游戏工程零改动」基线。

输入含 A 路线交付的 .blend 与其验收产物；游戏工程按全量文件扫，
只排除引擎缓存 .godot/（每次开编辑器都会重写，不是源码）。
条目数由脚本现算，不写死数字。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
A_ROUTE = BAKE / "route-a-asset-rework"

INPUTS = [
    "route-a-asset-rework/foe-deformable-continuous-shell.blend",
    "route-a-asset-rework/a_build.json",
    "route-a-asset-rework/metrics_a.json",
    "route-a-asset-rework/verify_a.py",
    "route-a-asset-rework/verify_a_result.json",
    "route-a-asset-rework/baseline.json",
    "route-a-asset-rework/A-route-asset-rework-validation-record.txt",
    "baked2.json",
    "3d-attack-gifs/apose_joints.json",
    "3d-attack-gifs/puppet_mapping.json",
]


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
    for p in sorted(GAME.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(GAME).as_posix()
        if rel.startswith(".godot/") or rel.endswith(".tmp"):
            continue
        game[rel] = {"bytes": p.stat().st_size, "sha256": sha256(p)}

    out = {"inputs": inputs, "game": game, "missing": missing}
    (HERE / "baseline.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BASELINE_C inputs={len(inputs)} game={len(game)} missing={missing}")
    print("BASELINE_C_OK" if not missing and game else "BASELINE_C_FAILED")
    return 0 if not missing and game else 1


if __name__ == "__main__":
    raise SystemExit(main())
