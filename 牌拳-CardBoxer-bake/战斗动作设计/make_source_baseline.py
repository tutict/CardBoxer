"""采集游戏源码 sha256 基线，供 verify_spec.py 证明「本轮没改源码」。

基线来自文件而非硬编码在判据里，源码正常演进时重新跑本脚本即可，
判据不会因为写死的哈希而误报。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "牌拳-CardBoxer"
OUT = HERE / "源码基线.json"

FILES = [
    "scripts/arena.gd",
    "scripts/fighter.gd",
    "scripts/card_data.gd",
    "scripts/card_motion.gd",
    "scripts/taikou_rules.gd",
    "scripts/taikou_rage.gd",
    "data/card_motion.json",
]

rows = {}
for rel in FILES:
    p = GAME / rel
    assert p.is_file(), f"missing {p}"
    b = p.read_bytes()
    rows[rel] = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}

OUT.write_text(json.dumps({"game_dir": str(GAME), "files": rows},
                          ensure_ascii=False, indent=2), encoding="utf-8")
print(f"BASELINE_OK game={GAME.name} files={len(rows)}")
