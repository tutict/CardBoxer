"""H 路线变异验证：逐条改坏被守卫的对象，确认 verify_h.py 真的报红。

纪律（沿用 G/F 路线）：
- 用二进制读写 + sha256 证明还原，不用 read_text/write_text（换行会被转）。
- needle 匹配 0 次 = DID NOT RUN，计入未证明，不许直接崩、不许算 CAUGHT。
- 每组都还原后才进下一组；最后 clean re-run 必须 GREEN。
- 变异体必须仍能解析：改 JSON 布尔/数值、改 GDScript 字面量，不制造语法错。

H_ROOT 环境变量供 selftest_did_not_run_h.py 把副本放到 logs/ 下时
仍指向真正的工作区；正常运行时不设。
用法：python mutation_h.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(os.environ.get("H_ROOT", str(Path(__file__).resolve().parent)))
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
VERIFY = HERE / "verify_h.py"

# (编号, 目标, needle, mutant)；目标 "GAME:xxx" 表示游戏工程内文件。
CASES = [
    ("M01_retired_metric_renamed", "data/cross_h.json",
     b'"retired_metric":', b'"retired_v1_metric":'),
    ("M02_untouched_roi_not_zero", "data/vp_diag_h.json",
     b'"changed_px": 0', b'"changed_px": 1'),
    ("M03_static_ab_pixels_changed", "data/static_ab_h.json",
     b'"changed_pixels": 0', b'"changed_pixels": 1'),
    ("M04_all_checks_not_green", "data/all_checks_h.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"'),
    ("M05_foe_yaw_flipped", "data/two_side_ab.json",
     b'"foe_yaw": -55.0', b'"foe_yaw": 55.0'),
    ("M06_basecolor_identical", "data/identity_h.json",
     b'"basecolor_thumb_mae": 75.3802',
     b'"basecolor_thumb_mae": 0.0'),
    ("M07_arena_uses_player_yaw", "GAME:scripts/arena.gd",
     b"Fighter3DLayerScript.DEFAULT_FOE_YAW",
     b"Fighter3DLayerScript.DEFAULT_SIDE_YAW"),
    ("M08_layer_loads_fixed_glb", "GAME:scripts/fighter_3d_layer.gd",
     b"var res := load(glb_path)", b"var res := load(GLB_PATH)"),
    ("M09_copy_not_identical", "data/install_assets_h.json",
     b'"identical": true', b'"identical": false'),
    ("M10_v1_negative_result_erased", "data/cross_h_v1_retired.json",
     b'"ok": false', b'"ok": true'),
    ("M11_foe_apose_equals_player", "data/apose_crosscheck_h.json",
     b'"foe_apose_not_equal_player": true',
     b'"foe_apose_not_equal_player": false'),
    ("M12_glb_has_animations", "data/foe_gltf_inspection.json",
     b'"zero_animations": true', b'"zero_animations": false'),
    ("M13_roi_not_two_regions", "data/roi_h.json",
     b'"two_regions": true', b'"two_regions": false'),
]


def resolve(target: str) -> Path:
    if target.startswith("GAME:"):
        return GAME / target[5:]
    return HERE / target


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-u", str(VERIFY)],
                       capture_output=True, timeout=120)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def main() -> int:
    assert VERIFY.is_file(), VERIFY
    caught = 0
    did_not_run = []
    restore_ok = 0
    restore_total = 0
    for name, target, needle, mutant in CASES:
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
            red = rc != 0 and "H_NOT_VERIFIED" in out
            if red:
                caught += 1
            print(f"{name} {'CAUGHT' if red else 'MISSED'} rc={rc}")
        finally:
            path.write_bytes(orig)
            if path.read_bytes() == orig and digest(path.read_bytes()) == digest(orig):
                restore_ok += 1

    rc_clean, out_clean = run_verify()
    clean_green = rc_clean == 0 and "H_VERIFIED" in out_clean
    total = len(CASES)
    ok = (caught == total and not did_not_run
          and restore_ok == restore_total == total and clean_green)
    print(f"CAUGHT={caught}/{total} DID_NOT_RUN={len(did_not_run)} "
          f"restore={restore_ok}/{restore_total} "
          f"clean={'GREEN' if clean_green else 'RED'}")
    for x in did_not_run:
        print("  DNR", x)
    print("MUTATION_H_OK" if ok else "MUTATION_H_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
