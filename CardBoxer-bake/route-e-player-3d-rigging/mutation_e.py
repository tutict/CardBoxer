"""E 路线变异验证：逐条打红 26 条判据，证明守卫不是摆设。

纪律（沿用 D 路线，本项目吃过亏）：
  · needle 锚点失配 = DID NOT RUN，计入未证明，绝不静默算 CAUGHT；
  · 还原必须逐字节 + sha256 校验，不用文本模式读写；
  · 全部跑完必须 clean re-run 26/26；
  · --selftest 故意让一个锚点失配，证明 DID NOT RUN 分支本身有牙。
  变异目标只在 E 工作区内，不改可运行游戏工程、不改 C/D 路线归档、
  不改 verify_e.py 自身。
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
RESULT = HERE / "verify_e_result.json"
SELFTEST = "--selftest" in sys.argv
OUT = HERE / ("mutation_e_selftest_result.json" if SELFTEST
              else "mutation_e_result.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def solid_png(data: bytes, size: tuple[int, int] | None = None) -> bytes:
    if size is None:
        size = Image.open(io.BytesIO(data)).size
    buf = io.BytesIO()
    Image.new("RGB", size, (250, 250, 250)).save(buf, format="PNG")
    return buf.getvalue()


CASES = [
    {"id": "M1", "path": "baseline_e.json", "kind": "text",
     "needle": b'"sha256": "09ddb7e1f7a4b7fa0aa2bfedc393fcbb884bfdaed8bcfd722e2dfe67c84a4e8f"',
     "mutant": b'"sha256": "09ddb7e1f7a4b7fa0aa2bfedc393fcbb884bfdaed8bcfd722e2dfe67c84a4e8e"',
     "expect": ["E-01_baseline_inputs_intact"]},
    {"id": "M2", "path": "source_probe.json", "kind": "text",
     "needle": b'"shells": 2035', "mutant": b'"shells": 2036',
     "expect": ["E-03_source_asset_structure"]},
    {"id": "M3", "path": "e_build.json", "kind": "text",
     "needle": b'"is_bound": true', "mutant": b'"is_bound": false',
     "expect": ["E-07_surface_deform_bound_and_reopened"]},
    {"id": "M4", "path": "e_build.json", "kind": "text",
     "needle": b'"count": 72', "mutant": b'"count": 71',
     "expect": ["E-10_72_frames_ledger"]},
    {"id": "M5", "path": "e_build.json", "kind": "text",
     "needle": b'"shells": 3', "mutant": b'"shells": 4',
     "expect": ["E-05_voxel_shell_collapses_2035_shells"]},
    {"id": "M6", "path": "e_build.json", "kind": "text",
     "needle": b'"reopen_drive_max_displacement_m": 0.82539',
     "mutant": b'"reopen_drive_max_displacement_m": 0.00001',
     "expect": ["E-09_reopen_still_drives"]},
    {"id": "M7", "path": "metrics_e.json", "kind": "text",
     "needle": b'"mean_tear_ratio": 1.27632',
     "mutant": b'"mean_tear_ratio": 0.50000',
     "expect": ["E-11_metrics_recomputed_from_raw_rows",
                "E-13_negative_result_not_sugarcoated",
                "E-14_conclusion_recomputable"]},
    {"id": "M8", "path": "frames/e-jab07-x15.png", "kind": "solid_png",
     "expect": ["E-15_all_16_frames_sha_matched"]},
    {"id": "M9", "path": "boards/E-all-72-frames-deformation-quality.png", "kind": "copy_from",
     "arg": "boards/E-model-and-motion-six-frames.png",
     "expect": ["E-16_four_boards_shape_and_distinct"]},
    {"id": "M10", "path": "board_stats_e.json", "kind": "text",
     "needle": b'"recommendation": "small_sprite_sample_first"',
     "mutant": b'"recommendation": "godot_rig_layer"',
     "expect": ["E-14_conclusion_recomputable"]},
    {"id": "M11", "path": "e_conclusion.json", "kind": "text",
     "needle": b'"deformation_verdict": "WORSE_THAN_FOE"',
     "mutant": b'"deformation_verdict": "NOT_WORSE"',
     "expect": ["E-13_negative_result_not_sugarcoated"]},
    {"id": "M12", "path": "gltf_e_inspection.json", "kind": "text",
     "needle": b'"all_match": true', "mutant": b'"all_match": false',
     "expect": ["E-20_pbr_zero_reencode"]},
    {"id": "M13", "path": "export_e.json", "kind": "text",
     "needle": b'"bytes": 38220692', "mutant": b'"bytes": 1',
     "expect": ["E-18_four_glb_exports_intact"]},
    {"id": "M14", "path": "godot_e_result.json", "kind": "text",
     "needle": b'"script_errors": 0', "mutant": b'"script_errors": 3',
     "expect": ["E-22_godot_import_clean"]},
    {"id": "M15", "path": "godot_e_result.json", "kind": "text_all",
     "needle": b'"skeleton_path": ""',
     "mutant": b'"skeleton_path": ".."',
     "expect": ["E-23_godot_skeleton_only_on_proxy"]},
    {"id": "M16", "path": "make_boards_e.py", "kind": "text",
     "needle": b"BOARD_LIST_MISMATCH", "mutant": b"BOARD_LIST_CHANGED",
     "expect": ["E-17_board_ledger_and_source_wiring"]},
    {"id": "M17", "path": "run_godot_e.py", "kind": "text",
     "needle": b'"--editor"', "mutant": b'"--headless"',
     "expect": ["E-24_pipeline_source_wiring"]},
    {"id": "M18", "path": "logs/e_build.log", "kind": "text",
     "needle": b"E_BUILD_OK",
     "mutant": b"Traceback (most recent call last)",
     "expect": ["E-25_logs_have_no_errors"]},
    {"id": "M19", "path": "player-full.glb", "kind": "flip_byte",
     "expect": ["E-18_four_glb_exports_intact"]},
]


def mutate(case: dict, data: bytes) -> bytes | None:
    """返回 None 表示锚点失配（DID NOT RUN），绝不当成已证明。"""
    kind = case["kind"]
    if kind == "text":
        needle = case["needle"]
        if data.count(needle) != 1:
            return None
        return data.replace(needle, case["mutant"], 1)
    if kind == "text_all":
        needle = case["needle"]
        if data.count(needle) < 1:
            return None
        return data.replace(needle, case["mutant"])
    if kind == "solid_png":
        return solid_png(data)
    if kind == "copy_from":
        other = (HERE / case["arg"]).read_bytes()
        return other if other != data else None
    if kind == "flip_byte":
        if len(data) < 2:
            return None
        return data[:-1] + bytes([data[-1] ^ 0x01])
    raise ValueError(kind)


def run_verify() -> dict:
    subprocess.run([sys.executable, "-u", "verify_e.py"], cwd=str(HERE),
                   capture_output=True, timeout=180)
    return json.loads(RESULT.read_text(encoding="utf-8"))


def main() -> int:
    cases = [dict(c) for c in CASES]
    if SELFTEST:
        # 故意让 M1 的锚点不存在，验证 DID NOT RUN 分支有牙。
        cases[0]["needle"] = b'"sha256": "deadbeef"'
        cases[0]["mutant"] = b'"sha256": "deadbead"'

    rows = []
    restored = {}
    for case in cases:
        p = HERE / case["path"]
        orig = p.read_bytes()
        orig_sha = sha(orig)
        changed = mutate(case, orig)
        if changed is None or changed == orig:
            rows.append({"id": case["id"], "status": "DID NOT RUN",
                         "red": [], "expected": case["expect"],
                         "restored": True})
            continue
        try:
            p.write_bytes(changed)
            if sha(p.read_bytes()) != sha(changed):
                rows.append({"id": case["id"], "status": "WRITE_FAILED",
                             "red": [], "expected": case["expect"],
                             "restored": False})
                continue
            res = run_verify()
            red = res["failed"]
            hit = [name for name in case["expect"] if name in red]
            rows.append({"id": case["id"],
                         "status": "CAUGHT" if hit else "MISSED",
                         "red": red, "expected": case["expect"],
                         "restored": False})
        finally:
            p.write_bytes(orig)
            restored[case["path"]] = sha(p.read_bytes()) == orig_sha
    for row in rows:
        row["restored"] = restored.get(
            next(c["path"] for c in cases if c["id"] == row["id"]), True)

    clean = run_verify()
    caught = sum(1 for r in rows if r["status"] == "CAUGHT")
    did_not_run = sum(1 for r in rows if r["status"] == "DID NOT RUN")
    missed = sum(1 for r in rows if r["status"] == "MISSED")
    write_failed = sum(1 for r in rows if r["status"] == "WRITE_FAILED")
    all_restored = all(restored.values())
    clean_green = (clean["passed"] == clean["total"] == 26
                   and not clean["failed"])
    expected_total = len(cases)
    all_proven = (caught == expected_total and did_not_run == 0
                  and missed == 0 and write_failed == 0)
    if SELFTEST:
        assertion_ok = (caught == expected_total - 1 and did_not_run == 1
                        and missed == 0 and write_failed == 0
                        and not all_proven and all_restored and clean_green)
    else:
        assertion_ok = all_proven and all_restored and clean_green

    out = {
        "selftest": SELFTEST, "total": expected_total, "caught": caught,
        "did_not_run": did_not_run, "missed": missed,
        "write_failed": write_failed,
        "restore": restored, "restore_all_ok": all_restored,
        "clean_rerun": {"passed": clean["passed"],
                        "total": clean["total"], "green": clean_green},
        "all_proven": all_proven,
        "selftest_assertion_ok": assertion_ok,
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print(f"{r['id']:<4} {r['status']:<11} red={len(r['red'])} "
              f"{r['red'][:4]}")
    print(f"CAUGHT={caught}/{expected_total} DID_NOT_RUN={did_not_run} "
          f"MISSED={missed} RESTORE={sum(restored.values())}/{len(restored)} "
          f"CLEAN={clean['passed']}/{clean['total']}")
    if SELFTEST:
        print("SELFTEST_ASSERTION_OK" if assertion_ok
              else "SELFTEST_ASSERTION_FAILED")
        print("MUTATION_E_FAILED (expected 1 DID NOT RUN)"
              if not all_proven else "MUTATION_E_OK")
    else:
        print("MUTATION_E_OK" if all_proven else "MUTATION_E_FAILED")
    return 0 if assertion_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
