"""原生平台 P4 · 交付文件清单（只读盘 + sha256）。

已知坑：shell 重定向会在脚本启动前创建 0 字节的 .out，枚举时它还是空的
（P1 / P2 / B / P3 都踩过）。这里一开始就按名排除自身输出，并加一条
no_unexpected_zero_bytes 防漏断言：排除表之外出现任何零字节文件直接报红。

用法：python make_filelist_p4.py
产出：文件清单.txt、data/filelist_p4.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "文件清单.txt"
REP = HERE / "data" / "filelist_p4.json"
EXCLUDE_REL = {
    "文件清单.txt",
    "data/filelist_p4.json",
    "logs/filelist_p4.out",
}
KEY_ARTIFACTS = (
    "原生平台P4-诊断说明.txt", "原生平台P4-验证记录.txt",
    "diag_native.py", "evaluate_candidates.py", "make_candidate_board.py",
    "make_native_plan.py", "run_micro2_tear.py", "analyze_native_tear.py",
    "analyze_micro2_tear.py", "make_landing.py", "probe_layout.py",
    "p4_math.py", "apply_native.py", "readback_native.py",
    "run_p4_probe.py", "run_all_checks_p4.py", "make_p4_boards.py",
    "check_history_gates_p4.py", "verify_native.py",
    "mutation_native.py", "make_filelist_p4.py",
    "tests/p4_native_probe.gd", "tests/p4_2d_readback.gd",
    "orig/pre-p4/card_motion.json",
    "orig/pre-p4/motion_input.json",
    "orig/pre-p4/motion_input_foe.json",
    "data/native_diagnosis.json", "data/candidate_scan.json",
    "data/hybrid_tracks.json", "data/native_plan.json",
    "data/full_tear_blender.json", "data/native_tear.json",
    "data/micro2_plan.json", "data/micro2_tear_blender.json",
    "data/micro2_tear.json", "data/landing_decision.json",
    "data/landing_tracks.json", "data/layout_probe.json",
    "data/baseline_p4.json", "data/apply_native.json",
    "data/readback_native.json", "data/p4_probe.json",
    "data/p4_boards.json", "data/all_checks_p4.json",
    "data/history_gates_p4_before.json",
    "data/history_gates_p4_after.json",
    "data/verify_native.json", "data/mutation_native.json",
    "data/mutation_native_dnr.json",
    "boards/P4-候选改法权衡.png", "boards/P4-全量撕裂权衡.png",
    "boards/P4-平台曲线对照.png", "boards/P4-连续帧条带.png",
    "boards/P4-上线前后对照.png",
)
BOARDS = (
    "P4-候选改法权衡.png", "P4-全量撕裂权衡.png",
    "P4-平台曲线对照.png", "P4-连续帧条带.png", "P4-上线前后对照.png",
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
        k: jload(HERE / "data" / f)
        for k, f in {
            "verify": "verify_native.json",
            "mutation": "mutation_native.json",
            "selftest": "mutation_native_dnr.json",
            "all_checks": "all_checks_p4.json",
            "boards": "p4_boards.json",
            "probe": "p4_probe.json",
            "tear": "native_tear.json",
            "micro2_tear": "micro2_tear.json",
            "readback": "readback_native.json",
            "apply": "apply_native.json",
            "decision": "landing_decision.json",
            "gates_before": "history_gates_p4_before.json",
            "gates_after": "history_gates_p4_after.json",
        }.items()
    }
    probe_rows = reports["probe"]["rows"]
    checks = {
        "all_sizes_positive": all(r["size"] > 0 for r in rows),
        "no_unexpected_zero_bytes": not zero,
        "key_artifacts_present": all((HERE / r).is_file()
                                     for r in KEY_ARTIFACTS),
        "five_boards_present": all(
            (HERE / "boards" / n).is_file() for n in BOARDS),
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
            == reports["mutation"]["cases"]
            and reports["mutation"]["clean_ok"] is True),
        "selftest_dnr_effective": (
            reports["selftest"]["selftest"] is True
            and reports["selftest"]["dnr"]
            == reports["selftest"]["cases"]
            and reports["selftest"]["caught"] == 0
            and reports["selftest"]["clean_ok"] is True),
        "all_checks_green": (
            reports["all_checks"]["result"] == "ALL GREEN"
            and reports["all_checks"]["total"]
            == len(reports["all_checks"]["checks"])
            and reports["all_checks"]["failed"] == []),
        "upstream_reports_ok": all(
            reports[k].get("ok") is True
            for k in ("boards", "probe", "tear", "micro2_tear",
                      "readback", "apply", "decision",
                      "gates_before", "gates_after")),
        "history_reports_restored": all(
            r.get("restored_sha_equal") is True
            for k in ("gates_before", "gates_after")
            for r in reports[k]["rows"]),
    }
    lines = [
        "《牌拳》P4 · 数据层 255 对原生平台 · 交付文件清单",
        f"文件数 {len(rows)} / 总字节 {total}",
        "排除：清单自身、data/filelist_p4.json、logs/filelist_p4.out"
        "（重定向竞态）、__pycache__ / *.pyc",
        "复算：python make_filelist_p4.py",
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
    print(f"FILELIST_P4_OK files={len(rows)} bytes={total}"
          if all(checks.values()) else "FILELIST_P4_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
