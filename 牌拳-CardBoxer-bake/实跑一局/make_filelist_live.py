"""B 路线 · 交付文件清单（只读盘 + sha256）。

已知坑：shell 重定向会在脚本启动前创建 0 字节的 .out，枚举时它还是空的
（P1 / P2 都踩过）。这里一开始就按名排除自身输出，并加一条
no_unexpected_zero_bytes 防漏断言：排除表之外出现任何零字节文件直接报红，
而不是把「零字节」静默算进清单。

用法：python make_filelist_live.py
产出：文件清单.txt、data/filelist_live.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "文件清单.txt"
REP = HERE / "data" / "filelist_live.json"
EXCLUDE_REL = {
    "文件清单.txt",                 # 清单自身
    "data/filelist_live.json",      # 机器可读报告自身
    "logs/filelist_live.out",       # 本次命令重定向创建，枚举时还是 0 字节
}
KEY_ARTIFACTS = (
    "实跑一局-验证记录.txt",
    "run_live_match.py", "analyze_live.py", "make_live_board.py",
    "make_transition_strip.py", "run_all_checks_live.py",
    "make_baseline_live.py", "verify_live.py", "mutation_live.py",
    "tests/live_match_probe.gd",
    "orig/live_match_probe-evidence.gd",
    "data/live_match.json", "data/live_analysis.json",
    "data/live_boards.json", "data/transition_strip.json",
    "data/all_checks_live.json", "data/baseline_live.json",
    "data/verify_live.json", "data/mutation_live.json",
    "boards/实跑一局-节奏时间线.png",
    "boards/实跑一局-整帧关键帧.png",
    "boards/实跑一局-连续帧复核.png",
    "boards/实跑一局-玩家动作.gif",
    "boards/实跑一局-对手动作.gif",
)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jload(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main() -> int:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(HERE).as_posix()
        if rel in EXCLUDE_REL or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        rows.append({"rel": rel, "size": p.stat().st_size,
                     "sha256": sha(p)})
    total = sum(r["size"] for r in rows)
    zero = [r["rel"] for r in rows if r["size"] == 0]
    reports = {
        "verify_live": jload(HERE / "data" / "verify_live.json"),
        "mutation_live": jload(HERE / "data" / "mutation_live.json"),
        "all_checks_live": jload(HERE / "data" / "all_checks_live.json"),
        "live_match": jload(HERE / "data" / "live_match.json"),
        "live_analysis": jload(HERE / "data" / "live_analysis.json"),
    }
    checks = {
        "all_sizes_positive": all(r["size"] > 0 for r in rows),
        "no_unexpected_zero_bytes": not zero,
        "key_artifacts_present": all((HERE / r).is_file()
                                     for r in KEY_ARTIFACTS),
        "shots_present": all(
            len(list((HERE / "shots" / t).glob("*.png"))) >= 100
            for t in ("cap9", "cap3")),
        "five_boards_present": all(
            (HERE / "boards" / n).is_file()
            for n in ("实跑一局-节奏时间线.png",
                      "实跑一局-整帧关键帧.png",
                      "实跑一局-连续帧复核.png",
                      "实跑一局-玩家动作.gif",
                      "实跑一局-对手动作.gif")),
        # 不写死数量：数字由各自报告自洽给出，重跑后增减不会变成清单债
        "verify_all_green": (
            reports["verify_live"]["ok"] is True
            and reports["verify_live"]["total"] > 0
            and reports["verify_live"]["passed"]
            == reports["verify_live"]["total"]),
        "mutation_all_caught": (
            reports["mutation_live"]["ok"] is True
            and reports["mutation_live"]["cases"] > 0
            and reports["mutation_live"]["caught"]
            == reports["mutation_live"]["cases"]
            and reports["mutation_live"]["dnr"] == 0
            and reports["mutation_live"]["missed"] == 0
            and reports["mutation_live"]["restored"]
            == reports["mutation_live"]["cases"]),
        "all_checks_green": (
            reports["all_checks_live"]["result"] == "ALL GREEN"
            and reports["all_checks_live"]["total"]
            == len(reports["all_checks_live"]["checks"])
            and reports["all_checks_live"]["failed"] == []),
        "upstream_reports_ok": (
            reports["live_match"]["ok"] is True
            and reports["live_analysis"]["ok"] is True),
    }
    lines = [
        "《牌拳》B 路线 · 游戏里实跑一局 · 交付文件清单",
        f"文件数 {len(rows)} / 总字节 {total}",
        "排除：清单自身、data/filelist_live.json、logs/filelist_live.out"
        "（重定向竞态）、__pycache__ / *.pyc",
        "复算：python make_filelist_live.py",
        "-" * 78,
    ]
    for r in rows:
        lines.append(f"{r['size']:>10}  {r['sha256'][:16]}  {r['rel']}")
    lines.append("-" * 78)
    for k, v in checks.items():
        lines.append(f"{'OK  ' if v else 'FAIL'} {k}")
    if zero:
        lines.append("UNEXPECTED_ZERO_BYTES " + ", ".join(zero))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REP.write_text(json.dumps({"files": rows, "count": len(rows),
                               "bytes": total, "zero_bytes": zero,
                               "checks": checks,
                               "ok": all(checks.values())},
                              ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print(f"FILELIST_LIVE_OK files={len(rows)} bytes={total}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
