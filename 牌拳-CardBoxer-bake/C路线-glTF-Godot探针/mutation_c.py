"""verify_c.py 的变异验证：改坏盘上产物，确认被点名的判据真的报红。

纪律（沿用本仓 harness）：
  · needle / mutant 只用 ASCII bytes；中文值不进 needle；
  · 锚点 count != 1 一律记 DID NOT RUN 并计入未证明，绝不静默跳过；
  · 逐字节还原 + sha256 比对，不用文本模式读写（换行会被转换）；
  · 每组要求「指定判据红」且「哨兵判据仍绿」，防止一个文件坏掉全表皆红；
  · 收尾 clean re-run 必须 25/25 全绿。
  · C_MUTATION_SELFTEST=1 故意让 M1 锚点失配，验证失配分支有牙。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
VERIFY = HERE / "verify_c.py"
RESULT = HERE / "verify_c_result.json"
ZERO = b"0" * 64

CASES = [
    {"id": "M1", "file": "基线.json",
     "needle": b'"sha256": "88dca6d28aa36caeda9f5af5564bf553aa8a9ee618846457b036fe3b1bd54239"',
     "mutant": b'"sha256": "' + ZERO + b'"',
     "red": ["C-01_baseline_inputs_intact"],
     "sentinel": "C-05_blend_structure_diagnosis"},
    {"id": "M2", "file": "基线.json",
     "needle": b'"sha256": "ae5ab3382f0a6da19b3882b9bd403c22c19da6b2e9b43f50c49c49f5d2d46145"',
     "mutant": b'"sha256": "' + ZERO + b'"',
     "red": ["C-02_game_source_unchanged"],
     "sentinel": "C-01_baseline_inputs_intact"},
    {"id": "M3", "file": "gltf_inspection.json",
     "needle": b'"vertex_total": 84263', "mutant": b'"vertex_total": 1',
     "red": ["C-08_foe_full_glb_shape"],
     "sentinel": "C-10_textures_not_reencoded"},
    {"id": "M4", "file": "gltf_inspection.json",
     "needle": b'"image_share_of_glb": 0.9108',
     "mutant": b'"image_share_of_glb": 0.1000',
     "red": ["C-10_textures_not_reencoded"],
     "sentinel": "C-08_foe_full_glb_shape"},
    {"id": "M5", "file": "gltf_inspection.json",
     "needle": b'"max_abs_delta": 0.187166',
     "mutant": b'"max_abs_delta": 0.000000',
     "red": ["C-14_gltf_is_static_snapshot"],
     "sentinel": "C-10_textures_not_reencoded"},
    {"id": "M6", "file": "godot_import_result.json",
     "needle": b'"all_import_files_present": true',
     "mutant": b'"all_import_files_present": false',
     "red": ["C-15_editor_import_succeeded"],
     "sentinel": "C-17_foe_full_scene_tree"},
    {"id": "M7", "file": "godot_import_result.json",
     "needle": b'"MeshInstance3D": 2', "mutant": b'"MeshInstance3D": 0',
     "red": ["C-17_foe_full_scene_tree"],
     "sentinel": "C-15_editor_import_succeeded"},
    {"id": "M8", "file": "godot_pose_result.json",
     "needle": b'"unbound_mesh_count": 1',
     "mutant": b'"unbound_mesh_count": 0',
     "red": ["C-20_pose_writable_but_highpoly_unbound"],
     "sentinel": "C-17_foe_full_scene_tree"},
    {"id": "M9", "file": "godot_pose_result.json",
     "needle": b'"pose_local_changed": true',
     "mutant": b'"pose_local_changed": false',
     "red": ["C-20_pose_writable_but_highpoly_unbound"],
     "sentinel": "C-17_foe_full_scene_tree"},
    {"id": "M10", "file": "export_gltf.py",
     "needle": b'export_format="GLB"',
     "mutant": b'export_format="GLTF_SEPARATE"',
     "red": ["C-22_source_wiring"],
     "sentinel": "C-07_glb_files_intact"},
    {"id": "M11", "file": "blend_structure.json",
     "needle": b'"action_count": 0', "mutant": b'"action_count": 5',
     "red": ["C-05_blend_structure_diagnosis", "C-13_animations_nowhere"],
     "sentinel": "C-10_textures_not_reencoded"},
]


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def as_eol(data: bytes, needle: bytes) -> bytes:
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    return needle.replace(b"\n", eol)


def run_verify():
    subprocess.run([PY, "-u", str(VERIFY)], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=180)
    return json.loads(RESULT.read_text(encoding="utf-8"))


def main() -> int:
    selftest = os.environ.get("C_MUTATION_SELFTEST") == "1"
    cases = [dict(c) for c in CASES]
    if selftest:
        cases[0]["needle"] = b'"sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"'

    rows = []
    restore = {}
    restore_ok = 0
    for case in cases:
        p = HERE / case["file"]
        orig = p.read_bytes()
        needle = as_eol(orig, case["needle"])
        mutant = as_eol(orig, case["mutant"])
        count = orig.count(needle)
        if count != 1:
            rows.append({"id": case["id"], "status": "DID NOT RUN",
                         "reason": f"anchor count={count} (need 1)"})
            print(f"{case['id']} DID NOT RUN anchor count={count}")
            continue
        mutated = orig.replace(needle, mutant, 1)
        try:
            p.write_bytes(mutated)
            res = run_verify()
        finally:
            p.write_bytes(orig)
            # 按「用例」计数，不能按文件名字典：多个用例改同一文件会被合并。
            ok_restore = sha256(p.read_bytes()) == sha256(orig)
            restore[case["file"]] = ok_restore
            restore_ok += int(ok_restore)
        red = [c["name"] for c in res["checks"] if not c["ok"]]
        green = [c["name"] for c in res["checks"] if c["ok"]]
        caught = all(n in red for n in case["red"]) and case["sentinel"] in green
        rows.append({"id": case["id"], "status": "CAUGHT" if caught else "MISSED",
                     "red": red, "sentinel_green": case["sentinel"] in green,
                     "restored": restore[case["file"]]})
        print(f"{case['id']} {'CAUGHT' if caught else 'MISSED'} "
              f"red={red} restored={restore[case['file']]}")

    clean = run_verify()
    clean_green = clean["passed"] == clean["total"]
    caught = sum(r["status"] == "CAUGHT" for r in rows)
    dnr = sum(r["status"] == "DID NOT RUN" for r in rows)
    all_restored = restore_ok == (len(cases) - dnr) and all(restore.values())
    ok = (caught == len(cases) and dnr == 0 and all_restored and clean_green)
    out = {"selftest": selftest, "total": len(cases), "caught": caught,
           "did_not_run": dnr, "restore": restore,
           "restore_all_ok": all_restored,
           "clean_rerun": {"passed": clean["passed"], "total": clean["total"],
                           "green": clean_green},
           "all_proven": ok, "rows": rows}
    (HERE / ("mutation_c_selftest_result.json" if selftest
             else "mutation_c_result.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TOTAL={len(cases)} CAUGHT={caught} DID_NOT_RUN={dnr} "
          f"RESTORE={restore_ok}/{len(cases)-dnr} CLEAN={clean_green}")
    print("MUTATION_C_OK" if ok else "MUTATION_C_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
