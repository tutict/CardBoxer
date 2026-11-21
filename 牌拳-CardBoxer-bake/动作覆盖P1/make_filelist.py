"""动作覆盖 P1 · 生成文件清单（相对路径 / 字节 / sha256）。

清单排除自身与 __pycache__，逐文件记录，便于跨轮核对是否被改动。
用法：python make_filelist.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "文件清单.txt"
# 本脚本的 stdout 常被重定向到 logs/filelist.out；shell 在 Python 启动前
# 就创建了它，枚举时是 0 字节，会被 all_sizes_positive 误判成空产物。
# 它是清单自身的输出日志，不是证据文件，按名排除（并单独断言已排除）。
SELF_LOG = "logs/filelist.out"

KEY = [
    "动作覆盖P1-验证记录.txt",
    "orig/pre-p1/arena.gd",
    "orig/pre-p1/fighter_3d_layer.gd",
    "orig/pre-p1/motion_input.json",
    "orig/pre-p1/motion_input_foe.json",
    "data/baseline.json",
    "data/amplitude_scan.json",
    "data/build_motion_p1.json",
    "data/motion_p1_probe.json",
    "data/all_checks_local.json",
    "data/verify_motion_p1.json",
    "data/mutation_motion_p1.json",
    "data/mutation_dnr_selftest.json",
    "boards/动作覆盖-六态视口对照.png",
    "boards/动作覆盖-战斗帧对照.png",
    "shots/p1/mp1-player_win-sv-player.png",
    "shots/p1/mp1-legacy_player_win-sv-player.png",
    "shots/p1/mp1-draw-sv-foe.png",
    "shots/default/display-live.png",
    "tests/motion_p1_probe.gd",
    "make_baseline.py",
    "scan_amplitude.py",
    "build_motion_p1.py",
    "run_motion_p1_probe.py",
    "make_motion_board.py",
    "run_all_checks_p1.py",
    "verify_motion_p1.py",
    "mutation_motion_p1.py",
    "logs/arena.diff",
    "logs/layer.diff",
    "logs/all_checks_p1.out",
    "logs/verify.out",
    "logs/mutation.out",
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
                   and p.name != OUT.name
                   and p.relative_to(HERE).as_posix() != SELF_LOG)
    rows = [{"rel": p.relative_to(HERE).as_posix(),
             "size": p.stat().st_size,
             "sha256": sha256(p)} for p in files]
    exists = {r["rel"] for r in rows}
    raw = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*")
           if p.is_file() and "__pycache__" not in p.parts}
    checks = {
        "no_pycache": all("__pycache__" not in r["rel"] for r in rows),
        "all_sha_nonempty": all(len(r["sha256"]) == 64 for r in rows),
        "all_sizes_positive": all(r["size"] > 0 for r in rows),
        "key_files_present": all(k in exists for k in KEY),
        "two_boards_present": sum(
            1 for r in rows if r["rel"].startswith("boards/")) == 2,
        "p1_shots_present": sum(
            1 for r in rows
            if r["rel"].startswith("shots/p1/")) == 18,
        "fifteen_check_logs": sum(
            1 for r in rows
            if r["rel"].startswith("logs/checks/mp1_")) == 15,
        "file_count_sane": len(rows) >= 50,
        # 只排除清单自身与自引用日志，别把证据文件一起漏掉
        "enumeration_complete": exists == raw - {OUT.name, SELF_LOG},
    }
    total = sum(r["size"] for r in rows)
    lines = [
        "《牌拳》角色动作优化 · P1 补 3D 动作覆盖 · 文件清单",
        "日期：2026-11-14",
        f"文件数：{len(rows)}    总字节：{total}",
        "",
        "格式：相对路径 | 字节 | sha256",
        "",
    ]
    lines += [f"{r['rel']} | {r['size']} | {r['sha256']}" for r in rows]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    for k, v in checks.items():
        if not v:
            print("FAIL", k)
    ok = all(checks.values())
    print(f"{'FILELIST_OK' if ok else 'FILELIST_FAILED'} "
          f"files={len(rows)} bytes={total}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
