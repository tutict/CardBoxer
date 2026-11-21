"""P4 · 实机验收 · 交付文件清单（只读盘 + sha256）。

排除清单自身、输出 json、输出 .out（重定向竞态）、__pycache__ / *.pyc，
避免清单里出现 0 字节自引用。用法：python make_filelist_live_p4.py
产出：文件清单.txt、data/filelist_live_p4.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "文件清单.txt"
OUT_JSON = HERE / "data" / "filelist_live_p4.json"
EXCLUDE_REL = {
    "文件清单.txt",
    "data/filelist_live_p4.json",
    "logs/filelist_live_p4.out",
}
KEY_ARTIFACTS = [
    "实机验收P4-验证记录.txt",
    "实机验收P4-诊断说明.txt",
    "orig/双表来源与sha.txt",
    "tests/p4_live_probe.gd",
    "run_live_p4.py", "analyze_live_p4.py", "make_boards_p4.py",
    "run_all_checks_live_p4.py", "verify_live_p4.py",
    "mutation_live_p4.py", "make_filelist_live_p4.py",
    "data/live_p4.json", "data/live_p4_analysis.json",
    "data/boards_p4.json", "data/verify_live_p4.json",
    "data/mutation_live_p4.json", "data/mutation_live_p4_dnr.json",
    "data/all_checks_live_p4.json", "data/sha_baseline.json",
    "boards/P4实机-节奏时间线.png",
    "boards/P4实机-连续帧条带.png",
    "boards/P4实机-整帧关键帧.png",
]
BOARDS = [
    "boards/P4实机-节奏时间线.png",
    "boards/P4实机-连续帧条带.png",
    "boards/P4实机-整帧关键帧.png",
]


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def report_ok(rep: dict) -> bool:
    ck = rep.get("checks")
    return (isinstance(ck, dict) and bool(ck)
            and all(v is True for v in ck.values())
            and not rep.get("failed") and rep.get("ok") is True)


def main() -> int:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(HERE).as_posix()
        if rel in EXCLUDE_REL or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        rows.append({"rel": rel, "size": p.stat().st_size,
                     "sha16": sha(p)[:16]})
    total = sum(r["size"] for r in rows)
    zero = [r["rel"] for r in rows if r["size"] == 0]

    verify = load(HERE / "data" / "verify_live_p4.json")
    mut = load(HERE / "data" / "mutation_live_p4.json")
    dnr = load(HERE / "data" / "mutation_live_p4_dnr.json")
    allc = load(HERE / "data" / "all_checks_live_p4.json")
    upstream = [load(HERE / "data" / n) for n in (
        "live_p4.json", "live_p4_analysis.json", "boards_p4.json")]
    sv_count = len(list((HERE / "shots" / "three_d").glob("*.png")))

    checks = {
        "all_sizes_positive": all(r["size"] > 0 for r in rows),
        "no_unexpected_zero_bytes": not zero,
        "key_artifacts_present": all(
            (HERE / k).is_file() for k in KEY_ARTIFACTS),
        "three_boards_present": all(
            (HERE / k).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            for k in BOARDS),
        "sv_shots_present": sv_count >= 50,
        "verify_all_green": report_ok(verify)
        and verify.get("passed") == verify.get("total") == 60,
        "mutation_all_caught": (
            mut.get("cases") == mut.get("caught") == 33
            and mut.get("dnr") == mut.get("broken")
            == mut.get("missed") == 0
            and mut.get("restored") == mut.get("cases")
            and mut.get("clean_ok") is True and mut.get("ok") is True),
        "selftest_dnr_effective": (
            dnr.get("selftest") is True and dnr.get("dnr") == 1
            and dnr.get("caught") == 0 and dnr.get("clean_ok") is True
            and dnr.get("ok") is True),
        "all_checks_green": (
            allc.get("total") == 15 and allc.get("result") == "ALL GREEN"
            and not allc.get("failed")),
        "upstream_reports_ok": all(report_ok(r) for r in upstream),
    }
    ok = all(checks.values())
    OUT_JSON.write_text(json.dumps(
        {"files": len(rows), "bytes": total, "checks": checks,
         "zero": zero, "ok": ok, "rows": rows},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "《牌拳》P4 · 实机验收 · 交付文件清单",
        "文件数 %d / 总字节 %d" % (len(rows), total),
        "排除：清单自身、data/filelist_live_p4.json、"
        "logs/filelist_live_p4.out（重定向竞态）、__pycache__ / *.pyc",
        "复算：python make_filelist_live_p4.py",
        "-" * 78,
    ]
    for r in rows:
        lines.append("%10d  %s  %s" % (r["size"], r["sha16"], r["rel"]))
    lines.append("-" * 78)
    for k, v in checks.items():
        lines.append("CHECK %s %s" % (k, v))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("FILELIST_LIVE_P4_OK files=%d bytes=%d" % (len(rows), total))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
