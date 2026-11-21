"""World3D 接线修复 · 生成文件清单（相对路径 / 字节 / sha256）。

用法：python make_filelist.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "文件清单.txt"

KEY = [
    "World3D接线修复-验证记录.txt",
    "orig/pre-world3d/fighter_3d_layer.gd",
    "data/baseline.json",
    "data/world3d_min_pre.json",
    "data/world3d_min.json",
    "data/prepost.json",
    "data/shipped_check.json",
    "data/review_brightness.json",
    "data/all_checks_local.json",
    "data/legacy_guard_state.json",
    "data/verify_world3d_fix.json",
    "data/mutation_world3d_fix.json",
    "data/mutation_dnr_selftest.json",
    "boards/World3D修复-改前改后对照.png",
    "boards/World3D修复-角色亮度对照.png",
    "boards/World3D修复-对手变暗归因.png",
    "shots/shipped/sh-shipped-live.png",
    "shots/legacy/sh-legacy-live.png",
    "shots/no_tint/sh-shipped-live.png",
    "shots/default/display-live.png",
    "verify_world3d_fix.py",
    "mutation_world3d_fix.py",
    "双侧独立建模-验证记录.txt",
    "data/separate_models.json",
    "data/user_frame_origin.json",
    "data/mutation_separate_models.json",
    "data/mutation_separate_dnr_selftest.json",
    "boards/双侧独立建模-展示板.png",
    "boards/双侧独立建模-串扰对照.png",
    "shots/probe_user.png",
    "make_separate_models.py",
    "mutation_separate_models.py",
    "diag_user_frame.py",
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    files = sorted(p for p in HERE.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts
                   and p.name != OUT.name)
    rows = [{"rel": p.relative_to(HERE).as_posix(),
             "size": p.stat().st_size,
             "sha256": sha256(p)} for p in files]
    exists = {r["rel"] for r in rows}
    checks = {
        "no_pycache": all("__pycache__" not in r["rel"] for r in rows),
        "all_sha_nonempty": all(len(r["sha256"]) == 64 for r in rows),
        "all_sizes_positive": all(r["size"] > 0 for r in rows),
        "key_files_present": all(k in exists for k in KEY),
        "three_boards_present": sum(
            1 for r in rows if r["rel"].startswith("boards/")) >= 3,
        "five_boards_present": sum(
            1 for r in rows if r["rel"].startswith("boards/")) >= 5,
        "file_count_sane": len(rows) >= 40,
    }
    total = sum(r["size"] for r in rows)
    lines = [
        "《牌拳》World3D 接线修复 · 文件清单",
        "日期：2026-11-14",
        f"文件数：{len(rows)}    总字节：{total}",
        "",
        "格式：相对路径 | 字节 | sha256",
        "",
    ]
    lines += [f"{r['rel']} | {r['size']} | {r['sha256']}" for r in rows]
    # 只写清单本体，不额外落盘报告：清单排除自身后与目录逐项自洽。
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print(f"FILELIST_OK files={len(rows)} bytes={total}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
