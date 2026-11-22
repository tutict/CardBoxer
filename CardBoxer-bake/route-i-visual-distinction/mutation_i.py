"""I 路线变异验证：逐条改坏被守卫的对象，确认 verify_i.py 的**点名判据**报红。

比 H 路线更严：不只看 rc != 0，还要求输出里出现
`CHECK <expect_red_check> False`，否则算 MISSED。这样即使「清单 sha
不一致」这类泛化判据顺带变红，也不能冒充针对性守卫有牙。

纪律：
- 二进制读写 + sha256 证明还原，不用 read_text/write_text（换行会被转）。
- needle 匹配 0 次 = DID NOT RUN，计入未证明，不直接崩、不算 CAUGHT。
- 每组还原后才进下一组；最后 clean re-run 必须 GREEN。
- 变异体必须仍能解析：改 GDScript 字面量 / JSON 布尔数值，不制造语法错。
- 守卫子进程禁写字节码：CPython 时间戳 pyc 只对照整数秒 mtime + size，
  同一秒内多次变异会读到上一例的陈旧字节码，误报 GREEN (MISSED!)。

I_ROOT 环境变量供 selftest_did_not_run_i.py 把副本放到 logs/ 下时
仍指向真正的工作区；正常运行时不设。
用法：python mutation_i.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(os.environ.get("I_ROOT", str(Path(__file__).resolve().parent)))
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
VERIFY = HERE / "verify_i.py"

# (编号, 目标, needle, mutant, 期望变红的判据名)；"GAME:" 指游戏工程内文件。
CASES = [
    ("M01_source_scale_reverted", "GAME:scripts/fighter_3d_layer.gd",
     b"const FOE_DRAW_SCALE_X := 1.22",
     b"const FOE_DRAW_SCALE_X := 1.16",
     "source_scale_matches_spec"),
    ("M02_source_tint_changed", "GAME:scripts/fighter_3d_layer.gd",
     b"vec3(0.42, 0.30, 0.28)", b"vec3(0.99, 0.99, 0.99)",
     "source_tint_matches_spec"),
    ("M03_retired_constant_reintroduced",
     "GAME:scripts/fighter_3d_layer.gd",
     b"const FOE_CANVAS_SHADER_CODE",
     b"const FOE_TINT := [0.46, 0.34, 0.30]\n"
     b"const FOE_CANVAS_SHADER_CODE",
     "source_retired_constants_absent"),
    ("M04_off_switch_renamed", "GAME:scripts/fighter_3d_layer.gd",
     b'"CARD_BOXER_FOE_VISUAL"', b'"CARD_BOXER_FOE_VISUAL_X"',
     "source_off_switch_present"),
    ("M05_spec_width_target_relaxed", "data/visual_diff_spec.json",
     b'"min_subject_width_ratio": 1.1',
     b'"min_subject_width_ratio": 1.0',
     "spec_width_target_not_relaxed"),
    ("M06_r1_negative_flipped", "data/visual_diag_r1_failed.json",
     b'"ok": false', b'"ok": true',
     "r1_negative_result_kept_false"),
    ("M07_diag_player_check_flipped", "data/visual_diag_i.json",
     b'"player_roi_pixel_identical": true',
     b'"player_roi_pixel_identical": false',
     "visual_diag_all_checks_true"),
    ("M08_off_player_check_flipped", "data/off_switch_i.json",
     b'"player_roi_never_changes": true',
     b'"player_roi_never_changes": false',
     "off_switch_all_checks_true"),
    ("M09_all_checks_not_green", "data/all_checks_i.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"',
     "all_checks_15_green"),
    ("M10_static_ab_pixels_changed", "data/static_ab_i.json",
     b'"changed_pixels": 0', b'"changed_pixels": 1',
     "static_ab_zero_pixels"),
    ("M11_baseline_sha_tampered", "baseline_i.json",
     b"c5dd4a3056a52e77f2269832bd898d8fbd03f2a61b81cc97b01d38e4c057e38e",
     b"d5dd4a3056a52e77f2269832bd898d8fbd03f2a61b81cc97b01d38e4c057e38e",
     "arena_sha_matches_baseline"),
    ("M12_final_patch_ok_flipped", "data/patch_visual_final_i.json",
     b'"ok": true', b'"ok": false',
     "final_patch_report_ok"),
]


def resolve(target: str) -> Path:
    if target.startswith("GAME:"):
        return GAME / target[5:]
    return HERE / target


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def guard_env() -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_verify() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-u", str(VERIFY)],
                       capture_output=True, timeout=180, env=guard_env())
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def main() -> int:
    assert VERIFY.is_file(), VERIFY
    caught = 0
    did_not_run: list[str] = []
    restore_ok = 0
    restore_total = 0
    for name, target, needle, mutant, expect in CASES:
        path = resolve(target)
        if not path.is_file():
            did_not_run.append(name + ":FILE_MISSING")
            print(f"{name} DID NOT RUN (missing file)")
            continue
        orig = path.read_bytes()
        count = orig.count(needle)
        if count == 0:
            did_not_run.append(name + ":ANCHOR_MISS")
            print(f"{name} DID NOT RUN (anchor not found)")
            continue
        path.write_bytes(orig.replace(needle, mutant, 1))
        restore_total += 1
        try:
            rc, out = run_verify()
            red = (rc != 0 and "I_NOT_VERIFIED" in out
                   and f"CHECK {expect} False" in out)
            if red:
                caught += 1
            else:
                print(f"  MISSED_DETAIL {name} rc={rc} "
                      f"expect=CHECK {expect} False")
            print(f"{name} {'CAUGHT' if red else 'MISSED'} rc={rc}")
        finally:
            path.write_bytes(orig)
            after = path.read_bytes()
            if after == orig and digest(after) == digest(orig):
                restore_ok += 1

    rc_clean, out_clean = run_verify()
    clean_green = rc_clean == 0 and "I_VERIFIED" in out_clean
    total = len(CASES)
    ok = (caught == total and not did_not_run
          and restore_ok == restore_total == total and clean_green)
    print(f"CAUGHT={caught}/{total} DID_NOT_RUN={len(did_not_run)} "
          f"restore={restore_ok}/{restore_total} "
          f"clean={'GREEN' if clean_green else 'RED'}")
    for x in did_not_run:
        print("  DNR", x)
    print("MUTATION_I_OK" if ok else "MUTATION_I_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
