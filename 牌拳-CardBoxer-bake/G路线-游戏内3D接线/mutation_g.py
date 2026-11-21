"""G 路线变异验证：逐条改坏被测物，确认 verify_g.py 真的报红。

纪律（本机踩过的坑，全部落进实现）：
  · needle / mutant 只能是 ASCII bytes；含中文会 SyntaxError。
  · 锚点出现 0 次或 >1 次 = DID NOT RUN，计入未证明，不崩、不跳过 clean。
  · 还原必须逐字节 + sha256 证明（read_text/write_text 会转换换行）。
  · 守卫跑禁字节码（PYTHONDONTWRITEBYTECODE=1）。
  · 负对照选清单外且 verify 不读的文件（logs/），否则会被清单判据抓到，
    负对照就假了。
  · 每条变异必须点到「被点名的那条判据」红，别的判据连带红不算证明。

用法：python mutation_g.py [--selftest]
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "牌拳-CardBoxer"
LOGS = HERE / "logs"
OUT_MAIN = LOGS / "mutation_g_result.json"
OUT_SELFTEST = LOGS / "mutation_g_selftest_result.json"
PY = sys.executable
GUARD = HERE / "verify_g.py"
VERIFY_JSON = LOGS / "verify_g.json"

# id, 目标根(HERE / GAME), 相对路径, needle(bytes ASCII), mutant, 期望红的判据
CASES = [
    ("M01", "HERE", "data/side_view_probe.json",
     b'"views": 8', b'"views": 7', "E07_side_view_probe_ok"),
    ("M02", "HERE", "data/static_ab_g.json",
     b'"changed_pixels": 0,', b'"changed_pixels": 9,',
     "E01_static_pixel_identical"),
    ("M03", "HERE", "data/same_tree_ab_g.json",
     b'"ok": true', b'"ok": false', "E02_same_tree_ok"),
    ("M04", "HERE", "data/ab_g.json",
     b'"ok": true', b'"ok": false', "D03_ab_ok"),
    # GLB 的 sha 在 copies 与 generated 各出现一次，改用 motion 的唯一 sha。
    ("M05", "HERE", "data/install_assets_g.json",
     b'"sha256": "c3ff4f76f5582b59d8706a611eb0bbbba4f8a8ee28bcf61a3cd801acd06f5cd2"',
     b'"sha256": "03ff4f76f5582b59d8706a611eb0bbbba4f8a8ee28bcf61a3cd801acd06f5cd2"',
     "C01_copy_data_motion_input.json"),
    # E05 读的是顶层 ok，不是 checks.bones_13；改后者守卫不会红。
    ("M06", "HERE", "data/three_d_ab.json",
     b'"ok": true', b'"ok": false', "E05_three_d_ab_ok"),
    ("M07", "HERE", "verify_g.py",
     b'ALLOWED_CHANGED = {"scripts/arena.gd", "scripts/fighter.gd"}',
     b'ALLOWED_CHANGED = {"scripts/arena.gd"}',
     "B02_only_allowed_changed"),
    # 把已退役的跨进程等价判据塞回 ab_g.json 的 checks，D04 应报红。
    ("M08", "HERE", "data/ab_g.json",
     b'"checks": {',
     b'"checks": {\n    "off_pixel_identical_t000": true,',
     "D04_retired_claim_absent"),
    ("M09", "HERE", "data/all_checks_after.json",
     b'"total": 15', b'"total": 14', "F01_all_green_after"),
    ("M10", "GAME", "scripts/fighter_3d_layer.gd",
     b"const DEFAULT_SIDE_YAW := 55.0", b"const DEFAULT_SIDE_YAW := 0.0",
     "A05_side_yaw_is_55"),
    ("M11", "GAME", "scripts/fighter_3d_layer.gd",
     b"const DEFAULT_SIDE_FLIP := false", b"const DEFAULT_SIDE_FLIP := true",
     "A06_side_flip_false"),
    ("M12", "GAME", "scripts/fighter_3d_layer.gd",
     b'"upperarm_f": 26.0', b'"upperarm_f": -26.0',
     "A08_stance_bias_exact"),
    ("M13", "GAME", "scripts/fighter_3d_layer.gd",
     b"var stance_bias_deg: Dictionary = DEFAULT_STANCE_BIAS.duplicate()",
     b"var stance_bias_deg: Dictionary = {}",
     "A09_stance_bias_default_applied"),
    ("M14", "GAME", "scripts/fighter_3d_layer.gd",
     b"drv.skel.set_bone_pose_rotation(i, cur * q)",
     b"drv.skel.set_bone_pose_rotation(i, cur)",
     "A11_bias_uses_bone_pose_rotation"),
    ("M15", "GAME", "scripts/arena.gd",
     b'use_3d = OS.get_environment("CARD_BOXER_3D") != ""',
     b'use_3d = OS.get_environment("CARD_BOXER_3D") == ""',
     "A01_switch_default_off"),
    ("M16", "GAME", "scripts/fighter.gd",
     b"var draw_3d_override := false", b"var draw_3d_override := true",
     "A02_override_default_false"),
    # 负对照：logs/ 在清单外且 verify 不读，改它一条判据都不该红。
    ("N01", "HERE", "logs/run_compare_g.out",
     b"AB_G_OK", b"AB_G_OK\nNEGATIVE_CONTROL", None),
]

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def guard_env() -> dict:
    env = os.environ.copy()
    # 陈旧 pyc 会让「改完立刻跑」导入上一例字节码，误报 GREEN(MISSED)。
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_guard() -> tuple[int, set]:
    if VERIFY_JSON.is_file():
        VERIFY_JSON.unlink()
    p = subprocess.run([PY, str(GUARD)], cwd=str(HERE),
                       env=guard_env(), capture_output=True, timeout=240)
    failed = set()
    if VERIFY_JSON.is_file():
        d = json.loads(VERIFY_JSON.read_text(encoding="utf-8"))
        failed = set(d.get("failed", []))
    return p.returncode, failed


def target(root: str, rel: str) -> Path:
    return (HERE if root == "HERE" else GAME) / rel


def main() -> int:
    selftest = "--selftest" in sys.argv
    cases = list(CASES)
    if selftest:
        # 故意把 M10 的锚点改成不存在，证明 DID NOT RUN 分支有牙。
        i = next(k for k, c in enumerate(cases) if c[0] == "M10")
        c = cases[i]
        cases[i] = (c[0], c[1], c[2], b"NO_SUCH_ANCHOR_999", c[4], c[5])
        out_path = OUT_SELFTEST
    else:
        out_path = OUT_MAIN

    LOGS.mkdir(parents=True, exist_ok=True)
    results, restore_ok = [], []
    for cid, root, rel, needle, mutant, expect in cases:
        p = target(root, rel)
        if not p.is_file():
            results.append({"id": cid, "status": "DID NOT RUN",
                            "reason": "target missing", "expect": expect})
            continue
        raw = p.read_bytes()
        before_sha = sha256(p)
        count = raw.count(needle)
        if count != 1:
            results.append({"id": cid, "status": "DID NOT RUN",
                            "reason": f"anchor_count={count}", "expect": expect,
                            "path": rel})
            continue
        mutated = raw.replace(needle, mutant, 1)
        p.write_bytes(mutated)
        try:
            rc, failed = run_guard()
            if expect is None:
                status = "MISSED (expected)" if not failed else "UNEXPECTED_RED"
            else:
                status = "CAUGHT" if expect in failed else (
                    "MISSED" if not failed else "OTHER")
        finally:
            p.write_bytes(raw)
            ok = sha256(p) == before_sha
            restore_ok.append(ok)
            if not ok:
                print(f"RESTORE FAILED {cid} {rel}", file=sys.stderr)
        results.append({"id": cid, "status": status, "expect": expect,
                        "failed_sample": sorted(failed)[:6],
                        "guard_rc": rc})

    rc_clean, failed_clean = run_guard()
    clean_green = rc_clean == 0 and not failed_clean
    caught = [r for r in results if r["status"] == "CAUGHT"]
    neg = [r for r in results if r["expect"] is None]
    dnr = [r for r in results if r["status"] == "DID NOT RUN"]
    positive = [r for r in results if r["expect"] is not None]
    unproven = (len(positive) - len(caught)) + any(
        r["status"] == "UNEXPECTED_RED" for r in neg)
    ok = (not selftest and unproven == 0 and clean_green
          and all(restore_ok) and len(restore_ok) == len(results))
    selftest_ok = (selftest and len(dnr) >= 1
                   and any(r["status"] == "CAUGHT" for r in results)
                   and clean_green and all(restore_ok))
    payload = {
        "selftest": selftest, "cases": results,
        "total": len(results), "caught": len(caught),
        "did_not_run": len(dnr),
        "negative_controls": len(neg),
        "unproven_positive": unproven,
        "restore_ok": sum(1 for x in restore_ok if x),
        "restore_total": len(restore_ok),
        "clean_rerun": "GREEN" if clean_green else "RED",
        "clean_failed": sorted(failed_clean)[:10],
        "ok": ok, "selftest_ok": selftest_ok,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    for r in results:
        print(f"{r['id']:<4} {r['status']:<20} "
              f"expect={r.get('expect')}")
    print(f"CAUGHT={len(caught)}/{len(positive)} "
          f"DID_NOT_RUN={len(dnr)} restore={sum(restore_ok)}/{len(restore_ok)} "
          f"clean={payload['clean_rerun']}")
    if selftest:
        print("SELFTEST_DID_NOT_RUN_OK" if selftest_ok
              else "SELFTEST_DID_NOT_RUN_FAILED")
        return 0 if selftest_ok else 1
    print("MUTATION_G_OK" if ok else "MUTATION_G_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
