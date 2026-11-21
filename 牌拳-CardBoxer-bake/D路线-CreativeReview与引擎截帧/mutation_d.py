"""D 路线变异验证：逐条打红判据，证明 18 条守卫不是摆设。

纪律：
  · needle 锚点失配 = DID NOT RUN，计入未证明，不静默算成 CAUGHT；
  · 还原必须逐字节 + sha256 校验；
  · 全部跑完必须 clean re-run 18/18；
  · --selftest 故意让一个锚点失配，证明 DID NOT RUN 分支本身有牙。
  变异目标只在 D 工作区内，不改可运行游戏工程、不改 C 路线归档、
  不改 verify_d.py 自身。
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
RESULT = HERE / "verify_d_result.json"
SELFTEST = "--selftest" in sys.argv
OUT = HERE / ("mutation_d_selftest_result.json" if SELFTEST
              else "mutation_d_result.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def solid_png(data: bytes, size: tuple[int, int] | None = None) -> bytes:
    if size is None:
        size = Image.open(io.BytesIO(data)).size
    buf = io.BytesIO()
    Image.new("RGB", size, (0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


CASES = [
    {"id": "M1", "path": "baseline_d.json", "kind": "text",
     "needle": b'"entries": 58', "mutant": b'"entries": 59',
     "expect": ["D-01_baseline_inputs_intact"]},
    {"id": "M2", "path": "godot_render_result.json", "kind": "text",
     "needle": b'"headless": false', "mutant": b'"headless": true',
     "expect": ["D-03_render_channel_windowed_opengl"]},
    {"id": "M3", "path": "shots/godot-front.png", "kind": "solid_png",
     "expect": ["D-05_frames_nonblank_and_textured"]},
    {"id": "M4", "path": "shots/godot-back.png", "kind": "copy_from",
     "arg": "shots/godot-side90.png",
     "expect": ["D-06_views_are_distinct"]},
    {"id": "M5", "path": "scale_metrics.json", "kind": "text",
     "needle": b'"mae_vs_direct_400": 4.9525',
     "mutant": b'"mae_vs_direct_400": 0.1000',
     "expect": ["D-11_scale_loss_monotonic"]},
    {"id": "M6", "path": "boards/D-侧视退化诊断.png", "kind": "small_png",
     "expect": ["D-12_four_boards_nonblank"]},
    {"id": "M7", "path": "review_conclusion.json", "kind": "text",
     "needle": b'"recommendation": "B"', "mutant": b'"recommendation": "C"',
     "expect": ["D-13_review_conclusion_recomputable"]},
    {"id": "M8", "path": "make_review_boards.py", "kind": "text",
     "needle": b"BOARD_LIST_MISMATCH", "mutant": b"BOARD_LIST_CHANGED",
     "expect": ["D-16_source_wiring"]},
    {"id": "M9", "path": "board_stats.json", "kind": "text",
     "needle": b'"game_character_px": 172.0',
     "mutant": b'"game_character_px": 180.0',
     "expect": ["D-10_game_scale_from_baked2"]},
    {"id": "M10", "path": "probe_project_d/assets/foe-full.glb",
     "kind": "flip_byte",
     "expect": ["D-15_isolation_and_clean_logs"]},
    {"id": "M11", "path": "run_godot_render.py", "kind": "text",
     "needle": b'"--resolution", "900x1100",',
     "mutant": b'"--headless", "--resolution", "900x1100",',
     "expect": ["D-07_capture_wiring_no_headless"]},
    {"id": "M12", "path": "measure_scale.py", "kind": "text",
     "needle": b"ImageChops.difference", "mutant": b"ImageChops.darker",
     "expect": ["D-16_source_wiring"]},
]


def mutate(case: dict, data: bytes) -> bytes | None:
    """返回 None 表示锚点失配（DID NOT RUN），绝不当成已证明。"""
    kind = case["kind"]
    if kind == "text":
        needle = case["needle"]
        if data.count(needle) != 1:
            return None
        return data.replace(needle, case["mutant"], 1)
    if kind == "solid_png":
        return solid_png(data)
    if kind == "small_png":
        return solid_png(data, (8, 8))
    if kind == "copy_from":
        other = (HERE / case["arg"]).read_bytes()
        return other if other != data else None
    if kind == "flip_byte":
        if len(data) < 2:
            return None
        return data[:-1] + bytes([data[-1] ^ 0x01])
    raise ValueError(kind)


def run_verify() -> dict:
    subprocess.run([sys.executable, "-u", "verify_d.py"], cwd=str(HERE),
                   capture_output=True, timeout=180)
    return json.loads(RESULT.read_text(encoding="utf-8"))


def main() -> int:
    cases = [dict(c) for c in CASES]
    if SELFTEST:
        # 故意让 M1 的锚点不存在，验证 DID NOT RUN 分支有牙。
        cases[0]["needle"] = b'"entries": 999999'
        cases[0]["mutant"] = b'"entries": 999998'

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
    clean_green = clean["passed"] == clean["total"] == 18 and not clean["failed"]
    expected_total = len(cases)
    all_proven = (caught == expected_total and did_not_run == 0
                  and missed == 0 and write_failed == 0)
    if SELFTEST:
        # selftest 的「成功」是：恰好少证明 1 条、DID_NOT_RUN=1、
        # 整体判定为未证明、还原与 clean 仍绿。
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
        print(f"{r['id']:<4} {r['status']:<11} red={r['red']}")
    print(f"CAUGHT={caught}/{expected_total} DID_NOT_RUN={did_not_run} "
          f"MISSED={missed} RESTORE={sum(restored.values())}/{len(restored)} "
          f"CLEAN={clean['passed']}/{clean['total']}")
    if SELFTEST:
        print("SELFTEST_ASSERTION_OK" if assertion_ok
              else "SELFTEST_ASSERTION_FAILED")
        print("MUTATION_D_FAILED (expected 1 DID NOT RUN)"
              if not all_proven else "MUTATION_D_OK")
    else:
        print("MUTATION_D_OK" if all_proven else "MUTATION_D_FAILED")
    return 0 if assertion_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
