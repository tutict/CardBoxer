"""动作表现 P2 · 变异验证：证明 verify_p2.py 的 59 条判据有牙。

纪律：
  * 每组变异的 needle 必须在目标文件里恰好命中 1 次；0 次 / 多次记
    DID NOT RUN 并计入「未证明」，绝不静默算通过。
  * CAUGHT 的判据必须同时满足：verify 退出码非 0、报告可解析、ok=False、
    failed 非空、**errors 为空**（守卫靠崩栈变红不算证明）、
    且点名的具体判据出现在 failed 里。
  * 变异体必须语法 / 结构成立（这里都是改数值或 ASCII 标识，不改结构）。
  * 还原一律二进制写回 + sha256 证明；不靠退出码，不靠文本模式读写。
  * 跑期间不编辑 verify_p2.py 及它会读的任何文件；子进程禁写字节码。
  * --selftest-dnr 故意用匹配不到的锚点，验证 DNR 分支确实会判未证明。

用法：python mutation_p2.py [--only <子串>] [--selftest-dnr]
产出：data/mutation_p2.json、logs/mutation_p2.out（由外层重定向）
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
D = HERE / "data"
BOARDS = HERE / "boards"
LOGS = HERE / "logs"
ORIG = HERE / "orig" / "pre-p2"
VERIFY = HERE / "verify_p2.py"
VERIFY_OUT = D / "verify_p2.json"
OUT = D / "mutation_p2.json"
PY = sys.executable
LEG_BONES_CAP_OLD = b'"leg_cap_deg":3.0'


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str, dict | None]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        p = subprocess.run([PY, "-B", str(VERIFY)], env=env,
                           capture_output=True, timeout=120,
                           cwd=str(HERE))
        rc = p.returncode
        text = (p.stdout + b"\n--- STDERR ---\n"
                + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    try:
        rep = json.loads(VERIFY_OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rep = None
    return rc, text, rep


def g(rel: str) -> Path:
    return GAME / rel


def h(rel: str) -> Path:
    return HERE / rel


def cases() -> list[dict]:
    return [
        dict(name="M01_player_cap_9_to_3", path=g("data/motion_input.json"),
             needle=b'"leg_cap_deg":9.0', mutant=b'"leg_cap_deg":3.0',
             expect=("player_cap_is_9", "only_one_diff_path_player")),
        dict(name="M02_foe_cap_9_to_3", path=g("data/motion_input_foe.json"),
             needle=b'"leg_cap_deg":9.0', mutant=b'"leg_cap_deg":3.0',
             expect=("foe_cap_is_9", "only_one_diff_path_foe")),
        dict(name="M03_arm_gain_changed", path=g("data/motion_input.json"),
             needle=b'"f_upper":32.0', mutant=b'"f_upper":33.0',
             expect=("player_arm_gains_untouched",
                     "only_one_diff_path_player")),
        dict(name="M04_torso_cap_changed", path=g("data/motion_input.json"),
             needle=b'"torso_cap_deg":8.0', mutant=b'"torso_cap_deg":9.0',
             expect=("torso_caps_untouched", "only_one_diff_path_player")),
        dict(name="M05_jab_frames_14_to_13",
             path=g("data/motion_input.json"),
             needle=b'"jab":{"frames":14', mutant=b'"jab":{"frames":13',
             expect=("frames_284_both",)),
        dict(name="M06_backup_cap_3_to_4", path=ORIG / "motion_input.json",
             needle=LEG_BONES_CAP_OLD, mutant=b'"leg_cap_deg":4.0',
             expect=("backup_bytewise_matches_baseline_player",)),
        dict(name="M07_baseline_sha_corrupted", path=D / "baseline_p2.json",
             needle=b"8646e80356d5a665e9535843241129405136dd3a7f31d836320b47f08fd74b98",
             mutant=b"0646e80356d5a665e9535843241129405136dd3a7f31d836320b47f08fd74b98",
             expect=("backup_bytewise_matches_baseline_player",
                     "other_12_watched_files_unchanged")),
        dict(name="M08_apply_check_flipped", path=D / "apply_p2.json",
             needle=b'"data/motion_input.json::only_mapping_leg_cap_changed": true',
             mutant=b'"data/motion_input.json::only_mapping_leg_cap_changed": false',
             expect=("apply_report_all_checks_true",)),
        dict(name="M09_anchor_raised", path=D / "full_tear.json",
             needle=b'"anchor_p999_m": 0.09365',
             mutant=b'"anchor_p999_m": 0.20000',
             expect=("anchor_pinned_at_0_09365",)),
        dict(name="M10_full_poses_852_to_851",
             path=D / "full_tear_blender.json",
             needle=b'"poses_evaluated": 852',
             mutant=b'"poses_evaluated": 851',
             expect=("full_852_poses_evaluated",)),
        dict(name="M11_plan_284_to_283", path=D / "full_plan.json",
             needle=b'"frame_count": 284', mutant=b'"frame_count": 283',
             expect=("full_plan_284_frame_pairs",)),
        dict(name="M12_shipped_readback_to_3",
             path=D / "p2_shipped_probe.json",
             needle=b'"mapping_cap_player": 9.0',
             mutant=b'"mapping_cap_player": 3.0',
             expect=("shipped_cap_readback_9_both_sides",)),
        dict(name="M13_shipped_diff_to_zero",
             path=D / "p2_shipped_probe.json",
             needle=b'"shipped_vs_rolled_back:jab01:player": 22468',
             mutant=b'"shipped_vs_rolled_back:jab01:player": 0',
             expect=("shipped_action_frames_all_changed_both_sides",)),
        dict(name="M14_all_checks_result_failed",
             path=D / "all_checks_p2.json",
             needle=b'"result": "ALL GREEN"',
             mutant=b'"result": "FAILED"',
             expect=("all_checks_p2_15_15",)),
        dict(name="M15_p1_log_summary_faked",
             path=LOGS / "p1_verify_after_p2.out",
             needle=b"MOTION_P1_VERIFY 50/52 FAILED",
             mutant=b"MOTION_P1_VERIFY 52/52 ALL GREEN",
             expect=("p1_guard_other_50_still_green",)),
        dict(name="M16_probe_gd_changed",
             path=g("tests/p2_shipped_probe.gd"),
             needle=b"const BASE_CAP := 3.0",
             mutant=b"const BASE_CAP := 4.0",
             expect=("shipped_probe_script_in_game_bytewise",)),
        dict(name="M17_board_png_signature_broken",
             path=BOARDS / "P2-before-after-player-comparison.png",
             needle=b"\x89PNG\r\n\x1a\n",
             mutant=b"\x89PNG\r\n\x1a\x00",
             expect=("five_boards_valid_png_signature",)),
        dict(name="M18_rig_driver_source_changed",
             path=g("scripts/rig_driver.gd"),
             needle=b"leg_cap_deg", mutant=b"leg_cap_dex",
             expect=("other_12_watched_files_unchanged",
                     "three_core_scripts_sha_unchanged")),
        dict(name="M19_amp_monotonic_broken",
             path=D / "amplitude_p2_probe.json",
             needle=b'"3": 2.25', mutant=b'"3": 99.25',
             expect=("amp_probe_four_caps_monotonic",)),
    ]


def main() -> int:
    global OUT
    selftest = "--selftest-dnr" in sys.argv
    # selftest 单独落盘，避免覆盖正式变异报告
    OUT = D / ("mutation_p2_dnr.json" if selftest
               else "mutation_p2.json")
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if selftest:
        cs = [dict(name="SELFTEST_DNR", path=D / "full_tear.json",
                   needle=b"NEVER_MATCH_P2_ANCHOR_XYZ", mutant=b"X",
                   expect=("anchor_pinned_at_0_09365",))]
    else:
        cs = cases()
        if only:
            # 大小写不敏感子串；要精确请给足够长的前缀
            cs = [c for c in cs if only.lower() in c["name"].lower()]

    originals: dict[Path, bytes] = {}
    for c in cs:
        p = Path(c["path"])
        if p not in originals:
            if not p.is_file():
                print("MISSING", p)
                return 1
            originals[p] = p.read_bytes()

    rows = []
    for c in cs:
        p = Path(c["path"])
        b = originals[p]
        n = b.count(c["needle"])
        if n != 1:
            rows.append({"name": c["name"], "status": "DID NOT RUN",
                         "needle_count": n, "path": str(p),
                         "restored": sha(p.read_bytes()) == sha(b)})
            print("DNR", c["name"], "needle_count", n)
            continue
        try:
            p.write_bytes(b.replace(c["needle"], c["mutant"], 1))
            rc, text, rep = run_verify()
        finally:
            p.write_bytes(b)  # 无条件二进制还原
        restored = sha(p.read_bytes()) == sha(b)
        failed = rep.get("failed", []) if isinstance(rep, dict) else []
        errors = rep.get("errors", {}) if isinstance(rep, dict) else {}
        hit = [e for e in c["expect"] if e in failed]
        caught = (rc != 0 and isinstance(rep, dict)
                  and rep.get("ok") is False
                  and len(failed) >= 1
                  and not errors
                  and bool(hit))
        status = "CAUGHT" if caught else "MISSED"
        rows.append({"name": c["name"], "status": status,
                     "path": str(p), "rc": rc, "restored": restored,
                     "expect_any": list(c["expect"]), "expect_hit": hit,
                     "failed": failed, "errors": errors,
                     "verify_tail": text.strip().splitlines()[-3:]})
        print(status, c["name"], "rc", rc, "restore", restored,
              "hit", hit, "errors", errors)

    # 全部目标文件必须逐字节回到变异前
    restore_all = {str(p): sha(p.read_bytes()) == sha(b)
                   for p, b in originals.items()}
    # clean re-run 必须全绿（也把 verify_p2.json 刷回绿色）
    crc, ctext, crep = run_verify()
    clean_green = (crc == 0 and isinstance(crep, dict)
                   and crep.get("ok") is True
                   and crep.get("failed") == []
                   and crep.get("errors") == {}
                   and "ALL GREEN" in ctext)
    proven = (all(r["status"] == "CAUGHT" for r in rows)
              and all(restore_all.values()) and clean_green)
    if selftest:
        # 按设计必须失败：DNR 不能被算成已证明
        proven = False
    report = {
        "cases": len(rows),
        "caught": sum(1 for r in rows if r["status"] == "CAUGHT"),
        "dnr": sum(1 for r in rows if r["status"] == "DID NOT RUN"),
        "missed": sum(1 for r in rows if r["status"] == "MISSED"),
        "restored": sum(1 for r in rows if r.get("restored")),
        "files_restored": restore_all,
        "clean_green": clean_green,
        "clean_verify": crep.get("passed") if isinstance(crep, dict) else None,
        "clean_verify_total": crep.get("total") if isinstance(crep, dict)
        else None,
        "selftest_dnr": selftest,
        "rows": rows, "ok": proven,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"MUTATION_P2 {report['caught']}/{report['cases']} CAUGHT / "
          f"DNR {report['dnr']} / MISSED {report['missed']} / "
          f"RESTORE {report['restored']}/{report['cases']} / "
          f"clean {report['clean_verify']}/{report['clean_verify_total']} "
          f"{'ALL GREEN' if clean_green else 'FAILED'}")
    if selftest:
        print("SELFTEST_DNR_EFFECTIVE" if report["dnr"] == 1
              and not proven else "SELFTEST_DNR_INEFFECTIVE")
        print("MUTATION_P2_FAILED (by design)")
        return 1
    print("MUTATION_P2_OK" if proven else "MUTATION_P2_FAILED")
    return 0 if proven else 1


if __name__ == "__main__":
    raise SystemExit(main())
