"""把 -bake 制备的 8 张 PNG 装进可运行工程，逐文件 sha256 对账。

只复制 PNG，不手抄 .import（uid / ctex 哈希由 Godot 编辑器生成）。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
SRC = HERE / "assets"
DST = GAME / "assets" / "portraits"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads((HERE / "assets_manifest.json").read_text(encoding="utf-8"))
    rows = manifest["outputs"]
    if not manifest["checks_all_pass"]:
        raise RuntimeError("assets_manifest checks not all pass, refusing to install")
    DST.mkdir(parents=True, exist_ok=True)
    result = []
    for row in rows:
        src = SRC / row["file"]
        dst = DST / row["file"]
        shutil.copyfile(src, dst)
        result.append({
            "file": row["file"],
            "src_sha256": sha256(src),
            "dst_sha256": sha256(dst),
            "manifest_sha256": row["sha256"],
            "identical": sha256(src) == sha256(dst) == row["sha256"],
            "bytes": dst.stat().st_size,
        })
    # 引擎侧守卫读的精简清单（不含 Pillow 专有字段），放进 res:// 后
    # 由 tests/portrait_wiring_check.gd 独立复算 PNG sha256 与尺寸。
    compact = {
        "files": {
            r["file"]: {
                "size": next(o["size"] for o in rows if o["file"] == r["file"]),
                "sha256": r["manifest_sha256"],
            }
            for r in result
        }
    }
    (DST / "manifest.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (HERE / "install_assets.json").write_text(
        json.dumps({"dst": str(DST), "files": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    bad = [r["file"] for r in result if not r["identical"]]
    print(f"INSTALLED={len(result)}")
    print(f"MISMATCH={len(bad)} {bad}")
    print("INSTALL_OK" if not bad else "INSTALL_FAILED")


if __name__ == "__main__":
    main()
