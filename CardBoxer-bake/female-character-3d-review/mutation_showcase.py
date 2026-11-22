"""女角色 3D 核查判据的变异验证：逐条打红，证明 12 条守卫不是摆设。

纪律：锚点失配 = DID NOT RUN 并计入未证明；还原逐字节 + sha256；
全部跑完 clean re-run 12/12；--selftest 故意让一个锚点失配。
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
RESULT = HERE / "verify_showcase_result.json"
SELFTEST = "--selftest" in sys.argv
OUT = HERE / ("mutation_showcase_selftest_result.json" if SELFTEST
              else "mutation_showcase_result.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def solid_png(data: bytes) -> bytes:
    size = Image.open(io.BytesIO(data)).size
    buf = io.BytesIO()
    Image.new("RGB", size, (20, 24, 36)).save(buf, format="PNG")
    return buf.getvalue()


CASES = [
    {"id": "M1", "path": "godot_player_result.json", "kind": "text",
     "needle": b'"ok": true', "mutant": b'"ok": false',
     "expect": ["S-05_godot_render_clean"]},
    {"id": "M2", "path": "boards/female-vs-foe-Godot-comparison.png",
     "kind": "solid_png",
     "expect": ["S-08_two_boards_valid"]},
    {"id": "M3", "path": "probe_project_player/project.godot",
     "kind": "text",
     "needle": b'run/main_scene="res://scenes/player_showcase.tscn"',
     "mutant": b'run/main_scene=""',
     "expect": ["S-04_godot_main_scene_wired"]},
    {"id": "M4", "path": "viewer_manifest.json", "kind": "text",
     "needle": b'"offline": true', "mutant": b'"offline": false',
     "expect": ["S-10_offline_viewer_complete"]},
    {"id": "M5", "path": "scene_inventory.json", "kind": "text",
     "needle": b'"name": "node_0"', "mutant": b'"name": "foe_0"',
     "expect": ["S-01_blend_contains_player_not_foe"]},
    {"id": "M6", "path": "shots/godot-player-front.png",
     "kind": "copy_from", "arg": "shots/godot-player-back.png",
     "expect": ["S-07_four_godot_shots_valid"]},
]


def mutate(case: dict, data: bytes) -> bytes | None:
    kind = case["kind"]
    if kind == "text":
        if data.count(case["needle"]) != 1:
            return None
        return data.replace(case["needle"], case["mutant"], 1)
    if kind == "solid_png":
        return solid_png(data)
    if kind == "copy_from":
        other = (HERE / case["arg"]).read_bytes()
        return other if other != data else None
    raise ValueError(kind)


def run_verify() -> dict:
    subprocess.run([sys.executable, "-u", "verify_showcase.py"],
                   cwd=str(HERE), capture_output=True, timeout=180)
    return json.loads(RESULT.read_text(encoding="utf-8"))


def main() -> int:
    cases = [dict(c) for c in CASES]
    if SELFTEST:
        cases[0]["needle"] = b'"ok": __NO_SUCH_KEY__'
        cases[0]["mutant"] = b'"ok": false'
    rows, restored = [], {}
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
            hit = [n for n in case["expect"] if n in red]
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
    caught = sum(r["status"] == "CAUGHT" for r in rows)
    did_not_run = sum(r["status"] == "DID NOT RUN" for r in rows)
    missed = sum(r["status"] == "MISSED" for r in rows)
    write_failed = sum(r["status"] == "WRITE_FAILED" for r in rows)
    all_restored = all(restored.values())
    clean_green = (clean["passed"] == clean["total"] == 12
                   and not clean["failed"])
    total = len(cases)
    all_proven = (caught == total and did_not_run == 0 and missed == 0
                  and write_failed == 0)
    if SELFTEST:
        assertion_ok = (caught == total - 1 and did_not_run == 1
                        and missed == 0 and write_failed == 0
                        and not all_proven and all_restored and clean_green)
    else:
        assertion_ok = all_proven and all_restored and clean_green

    OUT.write_text(json.dumps({
        "selftest": SELFTEST, "total": total, "caught": caught,
        "did_not_run": did_not_run, "missed": missed,
        "write_failed": write_failed,
        "restore_all_ok": all_restored,
        "clean_rerun": {"passed": clean["passed"],
                        "total": clean["total"], "green": clean_green},
        "all_proven": all_proven, "selftest_assertion_ok": assertion_ok,
        "rows": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        print(f"{r['id']:<4} {r['status']:<11} red={r['red'][:3]}")
    print(f"CAUGHT={caught}/{total} DID_NOT_RUN={did_not_run} "
          f"MISSED={missed} RESTORE={sum(restored.values())}/"
          f"{len(restored)} CLEAN={clean['passed']}/{clean['total']}")
    if SELFTEST:
        print("SELFTEST_ASSERTION_OK" if assertion_ok
              else "SELFTEST_ASSERTION_FAILED")
        print("MUTATION_SHOWCASE_FAILED (expected 1 DID NOT RUN)"
              if not all_proven else "MUTATION_SHOWCASE_OK")
    else:
        print("MUTATION_SHOWCASE_OK" if all_proven
              else "MUTATION_SHOWCASE_FAILED")
    return 0 if assertion_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
