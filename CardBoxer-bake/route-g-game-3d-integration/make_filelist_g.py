"""生成 G 路线交付文件清单与新增脚本 diff。

自指纪律：清单 / diff / logs / __pycache__ / .godot / orig / baseline_project
一律排除，否则「清单写好后重跑」会把自己算进去，清单永远不稳定。
另排除 probe_project_g/.godot 这类引擎缓存目录（按目录名，不按路径列）。

用法：python make_filelist_g.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent / "CardBoxer"
LIST = HERE / "file-list.txt"
DIFF = HERE / "new-files.diff"
EXCLUDE_NAMES = {"file-list.txt", "new-files.diff"}
EXCLUDE_DIRS = {"logs", ".godot", "__pycache__", "orig", "baseline_project"}
EXCLUDE_PREFIX = ("logs/", "orig/", "baseline_project/")

# 本轮新增/改动的脚本与 GDScript，拼成可复算的 diff。
DIFF_SCRIPTS = [
    "make_baseline_g.py", "run_all_checks_g.py", "run_probe_subviewport.py",
    "install_assets_g.py", "make_baseline_project_g.py", "capture_g.py",
    "compare_g.py", "diag_ab.py", "run_static_ab_g.py",
    "run_three_d_probe.py", "compare_same_tree_g.py",
    "run_side_view_probe.py", "make_side_board.py",
    "run_side_stance_probe.py", "make_stance_board.py",
    "run_side_stance_scan.py", "make_stance_scan_board.py",
    "verify_g.py", "mutation_g.py", "selftest_did_not_run_g.py",
    "make_filelist_g.py", "crosscheck_filelist_g.py",
]
DIFF_GAME_GD = [
    "scripts/fighter_3d_layer.gd",
    "tests/three_d_probe.gd",
    "tests/side_view_probe.gd",
    "tests/side_stance_probe.gd",
]
DIFF_PROBE_GD = [
    "probe_project_g/project.godot",
    "probe_project_g/probes/probe_subviewport.gd",
]


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
        if str(rel).replace("\\", "/").startswith(EXCLUDE_PREFIX):
            continue
        out.append(p)
    return out


def main() -> int:
    rows = []
    for p in entries():
        rel = str(p.relative_to(HERE)).replace("\\", "/")
        rows.append(f"{rel}\t{p.stat().st_size}\t{sha256(p)}")
    header = [
        "# G 路线 · 游戏内 3D 接线与侧面战斗 · 交付文件清单",
        "# 格式: 相对路径<TAB>字节<TAB>sha256",
        "# 排除: 本清单 / new-files.diff / logs / orig / baseline_project /",
        "#       .godot / __pycache__",
        "",
    ]
    # 二进制写：write_text 在 Windows 下会转 CRLF，清单稳定性判据用
    # bytes 逐字节比对，两种换行口径不一致会永远假红。
    LIST.write_bytes(("\n".join(header + rows) + "\n").encode("utf-8"))

    parts = []
    for name in DIFF_SCRIPTS:
        p = HERE / name
        if p.is_file():
            parts.append(f"===== G/{name} =====\n"
                         + p.read_text(encoding="utf-8"))
    for rel in DIFF_GAME_GD:
        p = GAME / rel
        if p.is_file():
            parts.append(f"===== GAME/{rel} =====\n"
                         + p.read_text(encoding="utf-8"))
    for rel in DIFF_PROBE_GD:
        p = HERE / rel
        if p.is_file():
            parts.append(f"===== G/{rel} =====\n"
                         + p.read_text(encoding="utf-8"))
    DIFF.write_bytes(("\n\n".join(parts) + "\n").encode("utf-8"))

    # 稳定性：立刻按同一口径重算一遍，与刚写出的清单逐字节比。
    again = ("\n".join(header + [
        f"{str(p.relative_to(HERE)).replace(chr(92), '/')}\t"
        f"{p.stat().st_size}\t{sha256(p)}" for p in entries()
    ]) + "\n").encode("utf-8")
    stable = LIST.read_bytes() == again
    print(f"FILELIST_ENTRIES={len(rows)} DIFF_BYTES={DIFF.stat().st_size}")
    print(f"STABLE={stable}")
    print("FILELIST_STABLE_OK" if stable else "FILELIST_UNSTABLE")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
