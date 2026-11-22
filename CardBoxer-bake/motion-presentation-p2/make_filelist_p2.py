"""生成 P2 证据区交付文件清单（相对路径 / size / sha256）。

排除清单自身与本脚本刚要写的 data/filelist_p2.json —— 否则会出现
「自己统计自己时 size=0」的自引用竞态（P1 收口轮踩过）。
同样排除 __pycache__ / *.pyc 等运行副产物。

用法：python make_filelist_p2.py
产出：文件清单.txt、data/filelist_p2.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "file-list.txt"
REP = HERE / "data" / "filelist_p2.json"
# logs/filelist_p2.out 是外层 shell 重定向先创建的输出文件，枚举时
# 仍是 0 字节 —— 与 P1 收口轮完全相同的自引用竞态，按名排除。
EXCLUDE_REL = {"file-list.txt", "data/filelist_p2.json",
               "logs/filelist_p2.out"}
KEY_ARTIFACTS = (
    "motion-presentation-p2-diagnostics.txt",
    "motion-presentation-p2-validation-record.txt",
    "diag_p2.py", "apply_p2_mapping.py", "verify_p2.py",
    "mutation_p2.py", "run_p2_shipped_probe.py",
    "run_all_checks_p2.py", "make_shipped_board.py",
    "analyze_full_tear.py", "run_amplitude_p2_probe.py",
    "data/full_tear.json", "data/p2_shipped_probe.json",
    "data/verify_p2.json", "data/mutation_p2.json",
    "data/mutation_p2_dnr.json", "data/all_checks_p2.json",
    "boards/P2-before-after-player-comparison.png",
    "boards/P2-before-after-foe-comparison.png",
    "boards/P2-real-glb-gain-tearing-tradeoff.png",
)
BOARDS_EXPECTED = 5


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    all_files = [p for p in sorted(HERE.rglob("*")) if p.is_file()]
    # 排除名单不能拿来掩盖真实的空文件：把枚举时全部的 0 字节路径
    # 单独记录下来，只允许本次输出自身是空的。
    zero_all = [p.relative_to(HERE).as_posix() for p in all_files
                if p.stat().st_size == 0]
    rows = []
    for p in all_files:
        rel = p.relative_to(HERE).as_posix()
        if rel in EXCLUDE_REL or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        rows.append({"rel": rel, "size": p.stat().st_size,
                     "sha256": sha(p)})
    total = sum(r["size"] for r in rows)
    checks = {
        "all_sizes_positive": all(r["size"] > 0 for r in rows),
        "zero_size_paths_only_self_output": set(zero_all)
        <= {"logs/filelist_p2.out"},
        "all_sha_len_64": all(len(r["sha256"]) == 64 for r in rows),
        "key_artifacts_present": all(
            (HERE / k).is_file() for k in KEY_ARTIFACTS),
        "five_boards_count": len(list(
            (HERE / "boards").glob("*.png"))) == BOARDS_EXPECTED,
        "min_file_count": len(rows) >= 40,
        "verify_report_green": (lambda: (
            json.loads((HERE / "data" / "verify_p2.json").read_text(
                encoding="utf-8"))["ok"] is True))(),
        "mutation_report_green": (lambda: (
            json.loads((HERE / "data" / "mutation_p2.json").read_text(
                encoding="utf-8"))["ok"] is True))(),
        "dnr_selftest_effective": (lambda: (
            json.loads((HERE / "data" / "mutation_p2_dnr.json").read_text(
                encoding="utf-8"))["dnr"] == 1))(),
    }
    lines = [
        "《牌拳》动作表现 P2 · 交付文件清单",
        f"文件数 {len(rows)} / 总字节 {total}",
        "排除：清单自身、data/filelist_p2.json、logs/filelist_p2.out、"
        "__pycache__ / *.pyc",
        f"枚举时 0 字节路径（只允许本次输出自身）："
        f"{zero_all if zero_all else '无'}",
        "-" * 78,
    ]
    for r in rows:
        lines.append(f"{r['rel']:<62s} {r['size']:>10d}  "
                     f"{r['sha256']}")
    lines.append("-" * 78)
    for k, v in checks.items():
        lines.append(f"CHECK {k} {v}")
    lines.append("FILELIST_P2_OK" if all(checks.values())
                 else "FILELIST_P2_FAILED")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REP.write_text(json.dumps({"files": rows, "count": len(rows),
                               "bytes": total,
                               "zero_size_paths": zero_all,
                               "checks": checks,
                               "ok": all(checks.values())},
                              ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"FILELIST_P2 files={len(rows)} bytes={total}")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("FILELIST_P2_OK" if all(checks.values())
          else "FILELIST_P2_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
