"""冻结改动后的游戏源码指纹，作为 verify_redraw.py 的 V01/V20 基准。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
FILES = [
    "scripts/arena.gd", "scripts/hud.gd", "scripts/fighter.gd",
    "scripts/fx_layer.gd", "project.godot",
    "tests/redraw_gate_check.gd", "tests/redraw_probe.gd",
    "tests/redraw_perf_probe.gd", "tests/key_bench.gd",
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    out = {}
    for rel in FILES:
        p = GAME / rel
        if not p.is_file():
            print("MISSING", rel)
            return 2
        b = p.read_bytes()
        out[rel] = {"sha256": sha(b), "bytes": len(b)}
    (HERE / "当前源码指纹.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CURRENT_SNAPSHOT files=%d arena=%s" % (len(out), out["scripts/arena.gd"]["sha256"][:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
