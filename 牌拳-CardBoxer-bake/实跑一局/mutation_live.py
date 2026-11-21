"""B 路线「实跑一局」· 变异验证：证明 verify_live.py 的 68 条判据有牙。

纪律（与 动作表现P2/mutation_p2.py 同款）：
  * 每组 needle 必须在目标文件里恰好命中 1 次；0 次 / 多次记
    DID NOT RUN 并计入「未证明」，绝不静默算通过。
  * CAUGHT 必须同时满足：verify 退出码非 0、报告可解析、ok=False、
    failed 非空、errors 为空（守卫靠崩栈变红不算证明），
    且点名的具体判据出现在 failed 里。
  * 变异体结构成立：JSON 仍可解析、GDScript 只改/插一行文本、PNG/GIF
    只改文件头字节。
  * 还原一律二进制写回 + sha256 证明；不靠退出码，不靠文本模式读写。
  * 子进程禁写字节码（PYTHONDONTWRITEBYTECODE=1）；
    clean re-run 必须全绿并把 verify_live.json 刷回绿色。
  * --selftest-dnr 故意用匹配不到的锚点，验证 DNR 分支确实会判未证明。

用法：python mutation_live.py [--only <子串>] [--selftest-dnr]
产出：data/mutation_live.json（selftest 写 mutation_live_dnr.json）
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
D = HERE / "data"
BOARDS = HERE / "boards"
LOGS = HERE / "logs"
ORIG = HERE / "orig"
TESTS = HERE / "tests"
VERIFY = HERE / "verify_live.py"
VERIFY_OUT = D / "verify_live.json"
PY = sys.executable


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str, dict | None]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        p = subprocess.run([PY, "-B", str(VERIFY)], env=env,
                           capture_output=True, timeout=180,
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


def cases() -> list[dict]:
    return [
        # ── A 落盘真值 ────────────────────────────────────────
        dict(name="M01_player_cap_9_to_3",
             path=g("data/motion_input.json"),
             needle=b'"leg_cap_deg":9.0', mutant=b'"leg_cap_deg":3.0',
             expect=("shipped_cap_still_9_both",)),
        dict(name="M02_foe_cap_9_to_3",
             path=g("data/motion_input_foe.json"),
             needle=b'"leg_cap_deg":9.0', mutant=b'"leg_cap_deg":3.0',
             expect=("shipped_cap_still_9_both",)),
        dict(name="M03_game_probe_out_of_sync",
             path=g("tests/live_match_probe.gd"),
             needle="2026-11-15 注释订正".encode("utf-8"),
             mutant="2026-11-16 注释订正".encode("utf-8"),
             expect=("game_probe_matches_source_bytewise",)),
        dict(name="M04_evidence_probe_code_line_changed",
             path=ORIG / "live_match_probe-evidence.gd",
             needle=b"\troot.add_child(d)",
             mutant=b"\troot.add_child(d)\n\tvar mutated := 1",
             expect=("comment_fix_changed_only_comment_lines",)),
        dict(name="M05_baseline_check_flipped",
             path=D / "baseline_live.json",
             needle=b'"all_14_watched_exist": true',
             mutant=b'"all_14_watched_exist": false',
             expect=("baseline_live_report_all_checks_true",)),

        # ── B 探针纪律（真跑而不是冻结/注入） ─────────────────
        dict(name="M06_probe_frame_post_draw_removed",
             path=TESTS / "live_match_probe.gd",
             needle=b"\t\t\t\tawait RenderingServer.frame_post_draw",
             mutant=b"\t\t\t\tawait get_tree().process_frame",
             expect=("probe_waits_frame_post_draw",
                     "comment_fix_changed_only_comment_lines")),
        dict(name="M07_probe_pauses_scene_tree",
             path=TESTS / "live_match_probe.gd",
             needle=b"\troot.add_child(d)",
             mutant=b"\troot.add_child(d)\n\tpaused = true",
             expect=("probe_never_pauses_arena",)),
        dict(name="M08_probe_writes_game_clock",
             path=TESTS / "live_match_probe.gd",
             needle=b"\tfunc _state() -> Dictionary:",
             mutant=(b"\tfunc _state() -> Dictionary:\n"
                     b"\t\tarena.tk_phase_time = 0.0"),
             expect=("probe_never_advances_game_clock",)),
        dict(name="M09_probe_stops_reading_driver_state",
             path=TESTS / "live_match_probe.gd",
             needle=b"last_delta_deg", mutant=b"last_delta_dex",
             expect=("probe_reads_real_driver_state",)),
        dict(name="M10_probe_comment_lies_again",
             path=TESTS / "live_match_probe.gd",
             needle="截图必须 await RenderingServer.frame_post_draw".encode(
                 "utf-8"),
             mutant="不 await frame_post_draw".encode("utf-8"),
             expect=("probe_comment_matches_code",)),

        # ── C 上游报告与真跑条件 ──────────────────────────────
        dict(name="M11_cap9_readback_faked",
             path=D / "live_match.json",
             needle=b'"cap_readback": 9.0',
             mutant=b'"cap_readback": 3.0',
             expect=("cap9_cap_readback_matches_case",)),
        dict(name="M12_cap9_override_hidden",
             path=D / "live_match.json",
             needle=b'"cap_override": -1.0',
             mutant=b'"cap_override": 9.0',
             expect=("cap9_uses_shipped_mapping_without_override",)),
        dict(name="M13_delta_mismatch_hidden",
             path=D / "live_match.json",
             needle=b'"delta_mismatches": []',
             mutant=b'"delta_mismatches": [1]',
             expect=("all_rows_delta_match_python_formula",)),
        dict(name="M14_all_checks_result_faked",
             path=D / "all_checks_live.json",
             needle=b'"result": "ALL GREEN"',
             mutant=b'"result": "FAILED"',
             expect=("all_checks_live_15_15",)),
        dict(name="M15_boards_check_flipped",
             path=D / "live_boards.json",
             needle=b'"player_gif_frames": true',
             mutant=b'"player_gif_frames": false',
             expect=("live_boards_report_all_checks_true",)),
        dict(name="M16_strip_panel_count_dropped",
             path=D / "transition_strip.json",
             needle=b'"present_panels": 42',
             mutant=b'"present_panels": 41',
             expect=("transition_strip_42_panels_three_groups",)),
        dict(name="M17_first_solo_fingerprint_erased",
             path=LOGS / "live_cap9.out",
             needle=b"FP cap9 ", mutant=b"FP xxxxx ",
             expect=("first_solo_run_fingerprint_logged",)),

        # ── D 节奏 / 四态 / 同源 A/B 数值 ─────────────────────
        dict(name="M18_draw_react_state_flipped",
             path=D / "live_analysis.json",
             needle=b'"draw_both_react": true',
             mutant=b'"draw_both_react": false',
             expect=("four_motion_states_match_analysis",)),
        dict(name="M19_phase_tolerance_widened",
             path=D / "live_analysis.json",
             needle=b'"phase_tol_s": 0.25',
             mutant=b'"phase_tol_s": 0.50',
             expect=("phase_spec_pinned",)),
        dict(name="M20_phase_violation_injected",
             path=D / "live_analysis.json",
             needle=b'"phase_duration_violations": []',
             mutant=b'"phase_duration_violations": [["cap9","1","resolve",9.0,1.9]]',
             expect=("no_phase_duration_violations",)),
        dict(name="M21_intra_jump_number_tampered",
             path=D / "live_analysis.json",
             needle=b'"intra_max_deg": 10.5535',
             mutant=b'"intra_max_deg": 99.0000',
             expect=("jump_numeric_fields_match_recomputation",)),
        dict(name="M22_peak_mean_number_tampered",
             path=D / "live_analysis.json",
             needle=b'"peak_mean_deg": 3.1209',
             mutant=b'"peak_mean_deg": 9.9000',
             expect=("peak_stats_match_recomputation",)),
        dict(name="M23_threshold_promoted_to_gate",
             path=D / "live_analysis.json",
             needle="不做放行线".encode("utf-8"),
             mutant="作为放行线".encode("utf-8"),
             expect=("jump_threshold_is_not_a_release_gate",)),
        dict(name="M24_reproducibility_na_reversed",
             path=D / "live_analysis.json",
             needle=b'"framewise_pixel_ab_applicable": false',
             mutant=b'"framewise_pixel_ab_applicable": true',
             expect=("reproducibility_na_pointed_not_folded_into_gate",)),
        dict(name="M25_homologous_source_swapped_to_cap3",
             path=D / "live_analysis.json",
             needle=b"cap9 live run", mutant=b"cap3 live run",
             expect=("homologous_frame_source_is_cap9_live_run",)),
        dict(name="M26_intro_exclusion_renamed",
             path=D / "live_analysis.json",
             needle=b"turn 1 discard", mutant=b"turn 2 discard",
             expect=("turn1_discard_exclusion_recorded",)),

        # ── E 截图通道与交付物 ────────────────────────────────
        dict(name="M27_keyframe_source_path_broken",
             path=D / "live_boards.json",
             needle=b"lm-0000-live.png", mutant=b"lm-XXXX-live.png",
             expect=("keyframes_board_sources_all_present",)),
        dict(name="M28_timeline_png_signature_broken",
             path=BOARDS / "实跑一局-节奏时间线.png",
             needle=b"\x89PNG\r\n\x1a\n",
             mutant=b"\x89PNG\r\n\x1a\x00",
             expect=("three_png_boards_valid_signature",)),
        dict(name="M29_player_gif_signature_broken",
             path=BOARDS / "实跑一局-玩家动作.gif",
             needle=b"GIF89a", mutant=b"GIF89b",
             expect=("two_gifs_valid_signature_and_88_frames",)),
        dict(name="M30_live_shot_png_signature_broken",
             path=HERE / "shots" / "cap9" / "lm-0000-live.png",
             needle=b"\x89PNG\r\n\x1a\n",
             mutant=b"\x89PNG\r\n\x1a\x00",
             expect=("cap9_all_shot_png_signatures_valid",)),
    ]


def main() -> int:
    selftest = "--selftest-dnr" in sys.argv
    out = D / ("mutation_live_dnr.json" if selftest
               else "mutation_live.json")
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if selftest:
        cs = [dict(name="SELFTEST_DNR", path=D / "live_analysis.json",
                   needle=b"NEVER_MATCH_LIVE_ANCHOR_XYZ", mutant=b"X",
                   expect=("phase_spec_pinned",))]
    else:
        cs = cases()
        if only:
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

    restore_all = {str(p): sha(p.read_bytes()) == sha(b)
                   for p, b in originals.items()}
    crc, ctext, crep = run_verify()
    clean_green = (crc == 0 and isinstance(crep, dict)
                   and crep.get("ok") is True
                   and crep.get("failed") == []
                   and crep.get("errors") == {}
                   and "ALL GREEN" in ctext)
    proven = (all(r["status"] == "CAUGHT" for r in rows)
              and all(restore_all.values()) and clean_green)
    if selftest:
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
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"MUTATION_LIVE {report['caught']}/{report['cases']} CAUGHT / "
          f"DNR {report['dnr']} / MISSED {report['missed']} / "
          f"RESTORE {report['restored']}/{report['cases']} / "
          f"clean {report['clean_verify']}/{report['clean_verify_total']} "
          f"{'ALL GREEN' if clean_green else 'FAILED'}")
    if selftest:
        print("SELFTEST_DNR_EFFECTIVE" if report["dnr"] == 1
              and not proven else "SELFTEST_DNR_INEFFECTIVE")
        print("MUTATION_LIVE_FAILED (by design)")
        return 1
    print("MUTATION_LIVE_OK" if proven else "MUTATION_LIVE_FAILED")
    return 0 if proven else 1


if __name__ == "__main__":
    raise SystemExit(main())
