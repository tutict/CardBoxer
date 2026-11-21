"""备份优化前的游戏源码树到 orig/pre-engine-opt/，并写逐字节指纹。

只备份文本源码（.gd / .tscn / project.godot）；background/*.png 不改，
但把它的 sha256 一起记进 背景贴图指纹.json，供「贴图不透明」判据复核。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
BACKUP = BAKE / "orig" / "pre-engine-opt"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in GAME.rglob("*")
                   if p.is_file() and p.suffix in (".gd", ".tscn")
                   and ".godot" not in p.relative_to(GAME).parts)
    files.append(GAME / "project.godot")
    files = sorted(set(files), key=lambda p: p.relative_to(GAME).as_posix())

    manifest = {}
    ok = True
    for p in files:
        rel = p.relative_to(GAME).as_posix()
        b = p.read_bytes()
        name = rel.replace("/", "__")
        (BACKUP / name).write_bytes(b)
        same = (BACKUP / name).read_bytes() == b
        ok = ok and same
        manifest[rel] = {"backup_file": name, "sha256": sha(b),
                         "bytes": len(b), "copy_ok": same}
    (HERE / "备份指纹.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    png = GAME / "background" / "arena.png"
    (HERE / "背景贴图指纹.json").write_text(json.dumps({
        "rel": "background/arena.png", "sha256": sha(png.read_bytes()),
        "bytes": png.stat().st_size,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("BACKUP_OK files=%d copy_ok=%s" % (len(manifest), ok)
          if ok else "BACKUP_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
