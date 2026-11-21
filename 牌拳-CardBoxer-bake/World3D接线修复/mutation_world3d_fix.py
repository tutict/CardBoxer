"""World3D 接线修复 · 承重判据变异验证。

纪律：
  * needle / mutant 是 bytes 字面量，只能 ASCII（中文值要写 \\xNN 转义）；
  * 还原用二进制读写 + sha256 证明，不靠文本模式读写；
  * 锚点匹配次数必须恰好 1，否则记 DID NOT RUN 并计入「未证明」；
  * 守卫崩栈 / 语法错不算 CAUGHT（证明的是文件坏了，不是守卫有牙）；
  * 最后 clean re-run 必须 51/51 ALL GREEN；
  * 子进程禁写字节码，避免陈旧 pyc 让变异没真正执行。

用法：
  python mutation_world3d_fix.py              # 正常 8 组
  python mutation_world3d_fix.py --selftest-dnr  # 额外插一组不存在锚点，
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
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
VERIFY = HERE / "verify_world3d_fix.py"
D = HERE / "data"
OUT_NORMAL = D / "mutation_world3d_fix.json"
OUT_SELFTEST = D / "mutation_dnr_selftest.json"

# (name, 目标文件, needle, mutant)
CASES = [
    ("M1_own_world_3d_flipped_to_false",
     GAME / "scripts" / "fighter_3d_layer.gd",
     b"sv.own_world_3d = true", b"sv.own_world_3d = false"),
    ("M2_own_world_3d_commented_out",
     GAME / "scripts" / "fighter_3d_layer.gd",
     b"sv.own_world_3d = true", b"# sv.own_world_3d = true"),
    ("M3_min_post_premise_faked",
     D / "world3d_min.json",
     b'"landed": true', b'"landed": false'),
    ("M4_shipped_check_boolean_flipped",
     D / "shipped_check.json",
     b'"shipped_sv_matches_single_layer": true',
     b'"shipped_sv_matches_single_layer": false'),
    ("M5_all_checks_result_faked",
     D / "all_checks_local.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"'),
    ("M6_legacy_stopgap_boolean_flipped",
     D / "legacy_guard_state.json",
     b'"stopgap_still_green": true',
     b'"stopgap_still_green": false'),
    ("M7_baseline_boolean_flipped",
     D / "baseline.json",
     b'"backup_matches_source": true',
     b'"backup_matches_source": false'),
    ("M8_tint_effect_flipped_negative",
     D / "review_brightness.json",
     b'"tint_effect": 3.644', b'"tint_effect": -1.0'),
]

DNR_SELFTEST = (
    "SELFTEST_anchor_missing",
    D / "prepost.json",
    b'"THIS_ANCHOR_DOES_NOT_EXIST": true',
    b'"THIS_ANCHOR_DOES_NOT_EXIST": false',
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, "-u", str(VERIFY)],
                       capture_output=True, timeout=120, cwd=str(HERE),
                       env=env)
    text = (p.stdout + b"\n--- STDERR ---\n" + p.stderr).decode(
        "utf-8", "replace")
    return p.returncode, text


def reds(out: str) -> list[str]:
    return [ln.strip().split()[-1] for ln in out.splitlines()
            if ln.strip().startswith("FAIL ")]


def main() -> int:
    cases = list(CASES)
    selftest = "--selftest-dnr" in sys.argv
    if selftest:
        cases.append(DNR_SELFTEST)
    rows = []
    for name, path, needle, mutant in cases:
        original = path.read_bytes()
        n = original.count(needle)
        if n != 1:
            rows.append({"name": name, "file": str(path),
                         "anchor_count": n, "status": "DID NOT RUN",
                         "restored": sha(path.read_bytes()) == sha(original)})
            print(f"DID NOT RUN {name} anchor_count={n}")
            continue
        path.write_bytes(original.replace(needle, mutant, 1))
        rc, out = run_verify()
        path.write_bytes(original)
        restored = sha(path.read_bytes()) == sha(original)
        clean_out = "Traceback" not in out and "SyntaxError" not in out
        caught = (rc == 1 and clean_out and bool(reds(out)))
        rows.append({"name": name, "file": str(path),
                     "anchor_count": n, "rc": rc,
                     "red_names": reds(out),
                     "status": "CAUGHT" if caught else "MISSED",
                     "restored": restored,
                     "clean_output": clean_out})
        print(f"{'CAUGHT' if caught else 'MISSED':12s} {name} "
              f"rc={rc} reds={len(reds(out))} restore={restored} "
              f"{','.join(reds(out)[:3])}")

    clean_rc, clean_out = run_verify()
    clean_green = (clean_rc == 0 and "ALL GREEN" in clean_out)
    caught_n = sum(r["status"] == "CAUGHT" for r in rows)
    dnr_n = sum(r["status"] == "DID NOT RUN" for r in rows)
    missed_n = sum(r["status"] == "MISSED" for r in rows)
    restored_n = sum(bool(r["restored"]) for r in rows)
    # DID NOT RUN / MISSED 都算未证明。自测模式故意插一条不存在的锚点，
    # 因此本脚本必须返回 FAILED；「分支有牙」由 selftest_expectations_met 判。
    ok = (caught_n == len(cases) and dnr_n == 0 and missed_n == 0
          and restored_n == len(cases) and clean_green)
    selftest_ok = (selftest and dnr_n == 1 and caught_n == len(CASES)
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
          f"RESTORE {restored_n}/{len(rows)} / clean={clean_green}")
    print("MUTATION_WORLD3D_FIX_OK" if ok
          else "MUTATION_WORLD3D_FIX_FAILED")
    if selftest and selftest_ok:
        print("SELFTEST_DNR_EFFECTIVE (DID NOT RUN 分支有牙；"
              "整体仍按设计判 FAILED)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
