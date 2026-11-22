"""生成 I 路线交付文件清单与新增脚本 / 源码 diff。

自指纪律（G 路线踩过）：清单 / diff / logs / orig / .godot /
__pycache__ 一律排除，否则「清单写好后重跑」会把自己算进去。
脚本名单动态扫 *.py，不写死，避免新增脚本漏进 diff。
用法：python make_filelist_i.py
"""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 真实工程在 桌面/学习资料/CardBoxer，与本归档目录是兄弟关系；
# 写成 HERE.parent / "CardBoxer" 会指向 bake 内的不存在的子目录。
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
LIST = HERE / "file-list.txt"
DIFF = HERE / "new-files.diff"
EXCLUDE_NAMES = {"file-list.txt", "new-files.diff"}
EXCLUDE_DIRS = {"logs", ".godot", "__pycache__", "orig"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def entries() -> list[Path]:
    out = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.name in EXCLUDE_NAMES:
            continue
        rel = p.relative_to(HERE)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        out.append(p)
    return out


def main() -> int:
    scripts = sorted(HERE.glob("*.py"))
    tests = sorted((HERE / "tests").glob("*.gd"))
    assert len(scripts) >= 15, f"too few scripts: {len(scripts)}"
    assert len(tests) >= 3, f"too few probe scripts: {len(tests)}"

    rows = []
    for p in entries():
        rel = str(p.relative_to(HERE)).replace("\\", "/")
        rows.append(f"{rel}\t{p.stat().st_size}\t{sha256(p)}")
    header = [
        "# I 路线 · 视觉区分度 · 交付文件清单",
        "# 格式: 相对路径<TAB>字节<TAB>sha256",
        "# 排除: 本清单 / new-files.diff / logs / orig / .godot / __pycache__",
        "",
    ]
    LIST.write_bytes(("\n".join(header + rows) + "\n").encode("utf-8"))

    parts = []
    for p in scripts:
        parts.append(f"===== I/{p.name} =====\n"
                     + p.read_text(encoding="utf-8"))
    for p in tests:
        parts.append(f"===== I/tests/{p.name} =====\n"
                     + p.read_text(encoding="utf-8"))
    spec = HERE / "data" / "visual_diff_spec.json"
    parts.append("===== I/data/visual_diff_spec.json =====\n"
                 + spec.read_text(encoding="utf-8"))
    old = (HERE / "orig" / "pre-visual" / "scripts"
           / "fighter_3d_layer.gd").read_text(
               encoding="utf-8").splitlines()
    new = (GAME / "scripts" / "fighter_3d_layer.gd").read_text(
        encoding="utf-8").splitlines()
    parts.append("===== unified diff: H -> I "
                 "scripts/fighter_3d_layer.gd =====\n"
                 + "\n".join(difflib.unified_diff(
                     old, new,
                     fromfile="H/scripts/fighter_3d_layer.gd",
                     tofile="I/scripts/fighter_3d_layer.gd",
                     lineterm="")))
    DIFF.write_bytes(("\n\n".join(parts) + "\n").encode("utf-8"))

    again = ("\n".join(header + [
        f"{str(p.relative_to(HERE)).replace(chr(92), '/')}\t"
        f"{p.stat().st_size}\t{sha256(p)}" for p in entries()
    ]) + "\n").encode("utf-8")
    stable = LIST.read_bytes() == again
    # 生成者自检：diff 必须真的写出且非空，不能让「清单绿了但 diff 没生成」
    # 混过收口（上一轮 GAME 路径写错就是这样静默过去的）。
    assert DIFF.is_file() and DIFF.stat().st_size > 10000, \
        f"new-files.diff missing or too small: {DIFF}"
    assert (GAME / "scripts" / "fighter_3d_layer.gd").is_file()
    print(f"FILELIST_ENTRIES={len(rows)} DIFF_BYTES={DIFF.stat().st_size} "
          f"SCRIPTS={len(scripts)} TESTS={len(tests)}")
    print(f"STABLE={stable}")
    print("FILELIST_STABLE_OK" if stable else "FILELIST_UNSTABLE")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
