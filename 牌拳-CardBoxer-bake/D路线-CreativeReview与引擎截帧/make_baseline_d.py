"""D 路线开工前冻结三处输入指纹，供 verify_d.py 判「全程零污染」。

1. 可运行游戏工程（排除 .godot/ 引擎缓存）逐文件 sha256；
2. C 路线刚交付的文件清单整体 sha256 与条目数（清单会随文件改动而失配）；
3. 源 GLB 的 sha256。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
C_ROUTE = BAKE / "C路线-glTF-Godot探针"
OUT = HERE / "baseline_d.json"


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

    clist = C_ROUTE / "文件清单.txt"
    cblob = clist.read_bytes()
    ctext = cblob.decode("utf-8")
    centries = sum(1 for line in ctext.splitlines()
                   if line.startswith("WORK/"))
    glb = C_ROUTE / "foe-full.glb"

    out = {
        "game": game,
        "game_root": str(GAME),
        "c_route_filelist": {
            "sha256": hashlib.sha256(cblob).hexdigest(),
            "entries": centries,
            "path": str(clist),
        },
        "source_glb": {
            "bytes": glb.stat().st_size,
            "sha256": sha256(glb),
            "path": str(glb),
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"GAME_FILES={len(game)} C_LIST_ENTRIES={centries} "
          f"GLB_BYTES={out['source_glb']['bytes']} BASELINE_D_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
