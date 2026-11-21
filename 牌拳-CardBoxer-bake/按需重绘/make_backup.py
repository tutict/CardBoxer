"""按需重绘：改源码前把 4 个脚本 + project.godot 逐字节备份并留指纹。

跑法（本轮开工第一步，只跑一次）：
    python make_backup.py
输出：baseline/、orig/pre-redraw/、源码基线.json
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
FILES = [
    "scripts/arena.gd",
    "scripts/hud.gd",
    "scripts/fighter.gd",
    "scripts/fx_layer.gd",
    "project.godot",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    out: dict[str, dict] = {}
    for rel in FILES:
        src = GAME / rel
        if not src.is_file():
            print("MISSING", src)
            return 2
        data = src.read_bytes()
        out[rel] = {
            "sha256": sha(data),
            "bytes": len(data),
            "crlf": data.count(b"\r\n"),
            "lf_only": data.count(b"\n") - data.count(b"\r\n"),
        }
        for dest_root in (HERE / "baseline", BAKE / "orig" / "pre-redraw"):
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if sha(dest.read_bytes()) != sha(data):
                print("COPY_MISMATCH", dest)
                return 3
        print("BACKUP OK %-28s %d B  sha=%s" % (rel, len(data), out[rel]["sha256"][:16]))
    (HERE / "源码基线.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BASELINE_FILES=%d" % len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
