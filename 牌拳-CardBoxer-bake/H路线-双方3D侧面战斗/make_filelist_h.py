"""生成 H 路线交付文件清单与新增脚本 diff。

自指纪律（G 路线踩过）：清单 / diff / logs / orig / .godot /
__pycache__ 一律排除，否则「清单写好后重跑」会把自己算进去。
用法：python make_filelist_h.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent / "牌拳-CardBoxer"
LIST = HERE / "文件清单.txt"
DIFF = HERE / "new-files.diff"
EXCLUDE_NAMES = {"文件清单.txt", "new-files.diff"}
EXCLUDE_DIRS = {"logs", ".godot", "__pycache__", "orig"}
EXCLUDE_PREFIX = ("logs/", "orig/")

DIFF_SCRIPTS = [
    "make_baseline_h.py", "probe_blends_h.py", "diag_rest_h.py",
    "diag_motion_h.py", "make_foe_motion_h.py", "build_foe_rigged_h.py",
    "inspect_foe_glb_h.py", "install_assets_h.py", "patch_game_h.py",
    "diag_glb_pair_h.py", "diag_roi_h.py", "make_zoom_h.py",
    "diag_cross_h.py", "run_isolate_h.py", "run_two_side_probe.py",
    "run_vp_diag_h.py", "make_isolate_zoom_h.py", "diag_identity_h.py",
    "run_all_checks_h.py", "run_static_ab_h.py", "verify_h.py",
    "mutation_h.py", "selftest_did_not_run_h.py",
    "make_filelist_h.py", "crosscheck_filelist_h.py",
]
DIFF_TESTS = ["tests/two_side_probe.gd", "tests/vp_diag_probe.gd"]
DIFF_GAME_GD = ["scripts/arena.gd", "scripts/fighter_3d_layer.gd",
                "scripts/fighter.gd"]


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
        "# H 路线 · 双方 3D 侧面战斗 · 交付文件清单",
        "# 格式: 相对路径<TAB>字节<TAB>sha256",
        "# 排除: 本清单 / new-files.diff / logs / orig / .godot / __pycache__",
        "",
    ]
    LIST.write_bytes(("\n".join(header + rows) + "\n").encode("utf-8"))

    parts = []
    for name in DIFF_SCRIPTS:
        p = HERE / name
        if p.is_file():
            parts.append(f"===== H/{name} =====\n"
                         + p.read_text(encoding="utf-8"))
    for rel in DIFF_TESTS:
        p = HERE / rel
        if p.is_file():
            parts.append(f"===== H/{rel} =====\n"
                         + p.read_text(encoding="utf-8"))
    for rel in DIFF_GAME_GD:
        p = GAME / rel
        if p.is_file():
            parts.append(f"===== GAME/{rel} =====\n"
                         + p.read_text(encoding="utf-8"))
    DIFF.write_bytes(("\n\n".join(parts) + "\n").encode("utf-8"))

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
