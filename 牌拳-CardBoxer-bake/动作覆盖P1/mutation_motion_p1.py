"""动作覆盖 P1 · 承重判据变异验证。

纪律（沿用 World3D 接线修复轮）：
  * needle / mutant 是 bytes 字面量，只能 ASCII（中文值要写 \\xNN 转义）；
  * 还原用二进制读写 + sha256 证明，不靠文本模式读写；
  * 锚点匹配次数必须恰好 1，否则记 DID NOT RUN 并计入「未证明」；
  * 守卫崩栈 / 语法错不算 CAUGHT（证明的是文件坏了，不是守卫有牙）；
  * 报告里的数值型 needle 从当前报告动态生成，重跑探针也不会变成 DNR；
  * 子进程禁写字节码，避免陈旧 pyc 让变异没真正执行；
  * 最后 clean re-run 必须 ALL GREEN。

用法：
  python mutation_motion_p1.py                 # 正常 N 组
  python mutation_motion_p1.py --selftest-dnr # 额外插一组不存在锚点，
                                             # 证明 DID NOT RUN 分支有牙
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
VERIFY = HERE / "verify_motion_p1.py"
D = HERE / "data"
OUT_NORMAL = D / "mutation_motion_p1.json"
OUT_SELFTEST = D / "mutation_dnr_selftest.json"

# (name, 目标文件, needle, mutant) —— 静态锚点
CASES = [
    ("M01_whitelist_reverted_to_hardcoded_three",
     GAME / "scripts" / "fighter_3d_layer.gd",
     b'if c != "stance" and not motion["cards"].has(c):',
     b'if c != "jab" and c != "cross" and c != "wave":'),
    ("M02_reveal_branch_disabled",
     GAME / "scripts" / "arena.gd",
     b'if tk_phase == "reveal" and has_focus:',
     b'if false and has_focus:'),
    ("M03_loser_react_branch_disabled",
     GAME / "scripts" / "arena.gd",
     b'if has_react and tk_winner != "":',
     b'if false and tk_winner != "":'),
    ("M04_reveal_s_decoupled_from_phase",
     GAME / "scripts" / "arena.gd",
     b"const REVEAL_S := 1.5", b"const REVEAL_S := 3.0"),
    ("M05_declared_frame_count_faked",
     GAME / "data" / "motion_input.json",
     b'"uppercut":{"frames":24,"track":',
     b'"uppercut":{"frames":23,"track":'),
    ("M06_probe_check_flipped",
     D / "motion_p1_probe.json",
     b'"legacy_winner_sv_bytewise_identical": true',
     b'"legacy_winner_sv_bytewise_identical": false'),
    ("M09_all_checks_out_faked",
     HERE / "logs" / "all_checks_p1.out",
     b"ALL_CHECKS_LOCAL 15/15 ALL GREEN",
     b"ALL_CHECKS_LOCAL 14/15 FAILED"),
    ("M10_all_checks_json_faked",
     D / "all_checks_local.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"'),
    ("M12_build_cross_file_flipped",
     D / "build_motion_p1.json",
     b'"two_cards_identical": true',
     b'"two_cards_identical": false'),
    ("M13_world3d_fix_regressed",
     GAME / "scripts" / "fighter_3d_layer.gd",
     b"sv.own_world_3d = true", b"sv.own_world_3d = false"),
    ("M14_explicit_bool_reverted_to_parse_error",
     GAME / "scripts" / "arena.gd",
     b'var has_focus: bool = motion_3d["cards"].has("focus")',
     b'var has_focus := motion_3d["cards"].has("focus")'),
]

DNR_SELFTEST = (
    "SELFTEST_anchor_missing",
    D / "verify_motion_p1.json",
    b'"THIS_ANCHOR_DOES_NOT_EXIST": true',
    b'"THIS_ANCHOR_DOES_NOT_EXIST": false',
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, "-u", str(VERIFY)],
                       capture_output=True, timeout=180, cwd=str(HERE),
                       env=env)
    text = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode(
        "utf-8", "replace")
    return p.returncode, text


def reds(out: str) -> list[str]:
    names = []
    for ln in out.splitlines():
        parts = ln.strip().split()
        if len(parts) >= 2 and parts[0] == "FAIL":
            names.append(parts[1])
    return names


def dynamic_cases() -> list[tuple]:
    """数值型锚点从当前报告动态生成，避免重跑探针后锚点失配。"""
    probe = json.loads((D / "motion_p1_probe.json").read_text(
        encoding="utf-8"))
    baseline = json.loads((D / "baseline.json").read_text(
        encoding="utf-8"))
    winner_sha = probe["sv_sha256"]["player_win_player"]
    reveal_diff = probe["diff_px"]["reveal_player"]
    watched_sha = baseline["files"]["scripts/fighter.gd"]["sha256"]
    return [
        ("M07_winner_ab_sha_tampered",
         D / "motion_p1_probe.json",
         ('"player_win_player": "%s"' % winner_sha).encode("ascii"),
         ('"player_win_player": "%s"' % ("0" * 64)).encode("ascii")),
        ("M08_diff_px_tampered",
         D / "motion_p1_probe.json",
         ('"reveal_player": %d' % reveal_diff).encode("ascii"),
         b'"reveal_player": 1'),
        ("M11_baseline_watched_sha_tampered",
         D / "baseline.json",
         ('"sha256": "%s"' % watched_sha).encode("ascii"),
         ('"sha256": "%s"' % ("0" * 64)).encode("ascii")),
    ]


def main() -> int:
    cases = list(CASES) + dynamic_cases()
    selftest = "--selftest-dnr" in sys.argv
    if selftest:
        cases.append(DNR_SELFTEST)
    rows = []
    for name, path, needle, mutant in cases:
        path = Path(path)
        original = path.read_bytes()
        n = original.count(needle)
        if n != 1:
            rows.append({"name": name, "file": str(path),
                         "anchor_count": n, "status": "DID NOT RUN",
                         "restored": sha(path.read_bytes()) == sha(original)})
            print(f"DID NOT RUN {name} anchor_count={n}", flush=True)
            continue
        path.write_bytes(original.replace(needle, mutant, 1))
        changed = path.read_bytes() != original
        rc, out = run_verify()
        path.write_bytes(original)
        restored = sha(path.read_bytes()) == sha(original)
        clean_out = ("Traceback" not in out and "SyntaxError" not in out
                     and "ModuleNotFoundError" not in out)
        caught = (changed and rc == 1 and clean_out and bool(reds(out)))
        rows.append({"name": name, "file": str(path),
                     "anchor_count": n, "changed": changed, "rc": rc,
                     "red_names": reds(out),
                     "status": "CAUGHT" if caught else "MISSED",
                     "restored": restored, "clean_output": clean_out})
        print(f"{'CAUGHT' if caught else 'MISSED':12s} {name} "
              f"rc={rc} reds={len(reds(out))} restore={restored} "
              f"{','.join(reds(out)[:3])}", flush=True)

    clean_rc, clean_out = run_verify()
    clean_green = (clean_rc == 0 and "ALL GREEN" in clean_out)
    caught_n = sum(r["status"] == "CAUGHT" for r in rows)
    dnr_n = sum(r["status"] == "DID NOT RUN" for r in rows)
    missed_n = sum(r["status"] == "MISSED" for r in rows)
    restored_n = sum(bool(r["restored"]) for r in rows)
    # DID NOT RUN / MISSED 都算未证明。自测模式故意插一条不存在的锚点，
    # 因此本脚本按设计返回 FAILED；分支有牙由 selftest_expectations_met 判。
    ok = (caught_n == len(cases) and dnr_n == 0 and missed_n == 0
          and restored_n == len(cases) and clean_green)
    selftest_ok = (selftest and dnr_n == 1
                   and caught_n == len(cases) - 1
                   and missed_n == 0 and restored_n == len(rows)
                   and clean_green)
    report = {
        "total": len(cases), "caught": caught_n,
        "did_not_run": dnr_n, "missed": missed_n,
        "restored": restored_n,
        "clean_rerun": {"rc": clean_rc, "green": clean_green,
                        "tail": clean_out.strip().splitlines()[-1:]},
        "selftest_dnr": selftest,
        "selftest_expectations_met": selftest_ok,
        "cases": rows, "ok": ok,
    }
    (OUT_SELFTEST if selftest else OUT_NORMAL).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"MUTATION {caught_n}/{len(cases)} CAUGHT / "
          f"DID_NOT_RUN {dnr_n} / MISSED {missed_n} / "
          f"RESTORE {restored_n}/{len(rows)} / clean={clean_green}",
          flush=True)
    print("MUTATION_MOTION_P1_OK" if ok
          else "MUTATION_MOTION_P1_FAILED", flush=True)
    if selftest and selftest_ok:
        print("SELFTEST_DNR_EFFECTIVE (DID NOT RUN 分支有牙；"
              "整体仍按设计判 FAILED)", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
