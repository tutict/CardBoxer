"""square-wave-plateau P3 · 交付文件清单（只读盘 + sha256）。

已知坑：shell 重定向会在脚本启动前创建 0 字节的 .out，枚举时它还是空的
（P1 / P2 / B 都踩过）。这里一开始就按名排除自身输出，并加一条
no_unexpected_zero_bytes 防漏断言：排除表之外出现任何零字节文件直接报红，
而不是把「零字节」静默算进清单。验收数字全部从各报告自洽读取，不写死。

用法：python make_filelist_p3.py
产出：文件清单.txt、data/filelist_p3.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "file-list.txt"
REP = HERE / "data" / "filelist_p3.json"
EXCLUDE_REL = {
    "file-list.txt",
    "data/filelist_p3.json",
    "logs/filelist_p3.out",
}
KEY_ARTIFACTS = (
    "square-wave-plateau-diagnostics.txt", "square-wave-plateau-validation-record.txt",
    "diag_plateau.py", "make_plateau_plan.py",
    "analyze_plateau_tear.py", "apply_p3.py", "p3_math.py",
    "run_p3_probe.py", "make_p3_boards.py",
    "run_all_checks_p3.py", "check_history_gates.py",
    "verify_plateau.py", "mutation_plateau.py",
    "tests/p3_plateau_probe.gd",
    "orig/pre-p3/rig_driver.gd",
    "orig/pre-p3/motion_input.json",
    "orig/pre-p3/motion_input_foe.json",
    "data/plateau_diagnosis.json", "data/plateau_plan.json",
    "data/full_tear_blender.json", "data/plateau_tear.json",
    "data/baseline_p3.json", "data/apply_p3.json",
    "data/p3_probe.json", "data/p3_boards.json",
    "data/all_checks_p3.json", "data/history_gates_p3.json",
    "data/verify_plateau.json", "data/mutation_plateau.json",
    "boards/P3-timeline-square-wave.png", "boards/P3-frame-sequence-strip.png",
    "boards/P3-before-after-comparison.png", "boards/P3-full-284-frames-tearing-tradeoff.png",
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
        "verify": jload(HERE / "data" / "verify_plateau.json"),
        "mutation": jload(HERE / "data" / "mutation_plateau.json"),
        "all_checks": jload(HERE / "data" / "all_checks_p3.json"),
        "boards": jload(HERE / "data" / "p3_boards.json"),
        "probe": jload(HERE / "data" / "p3_probe.json"),
        "tear": jload(HERE / "data" / "plateau_tear.json"),
        "gates": jload(HERE / "data" / "history_gates_p3.json"),
    }
    probe_rows = reports["probe"]["rows"]
    checks = {
        "all_sizes_positive": all(r["size"] > 0 for r in rows),
        "no_unexpected_zero_bytes": not zero,
        "key_artifacts_present": all((HERE / r).is_file()
                                     for r in KEY_ARTIFACTS),
        "four_boards_present": all(
            (HERE / "boards" / n).is_file() for n in (
                "P3-timeline-square-wave.png", "P3-frame-sequence-strip.png",
                "P3-before-after-comparison.png", "P3-full-284-frames-tearing-tradeoff.png")),
        "sv_shots_present": all(
            Path(r[f"{side}_sv"]).is_file()
            for r in probe_rows for side in ("player", "foe")),
        "verify_all_green": (
            reports["verify"]["ok"] is True
            and reports["verify"]["total"] > 0
            and reports["verify"]["passed"]
            == reports["verify"]["total"]
            and reports["verify"]["failed"] == []
            and reports["verify"]["errors"] == {}),
        "mutation_all_caught": (
            reports["mutation"]["ok"] is True
            and reports["mutation"]["cases"] > 0
            and reports["mutation"]["caught"]
            == reports["mutation"]["cases"]
            and reports["mutation"]["dnr"] == 0
            and reports["mutation"]["missed"] == 0
            and reports["mutation"]["restored"]
            == reports["mutation"]["cases"]),
        "all_checks_green": (
            reports["all_checks"]["result"] == "ALL GREEN"
            and reports["all_checks"]["total"]
            == len(reports["all_checks"]["checks"])
            and reports["all_checks"]["failed"] == []),
        "upstream_reports_ok": all(
            reports[k].get("ok") is True
            for k in ("boards", "probe", "tear", "gates")),
        "history_reports_restored": all(
            r.get("restored_sha_equal") is True
            for r in reports["gates"]["rows"]),
    }
    lines = [
        "《牌拳》P3 · square-wave-plateau · 交付文件清单",
        f"文件数 {len(rows)} / 总字节 {total}",
        "排除：清单自身、data/filelist_p3.json、logs/filelist_p3.out"
        "（重定向竞态）、__pycache__ / *.pyc",
        "复算：python make_filelist_p3.py",
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
    print(f"FILELIST_P3_OK files={len(rows)} bytes={total}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
