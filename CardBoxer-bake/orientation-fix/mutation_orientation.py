"""变异验证：证明 verify_orientation.py 每条关键判据真的会红。

逐字节还原 + sha256 证明；锚点失配记 DID NOT RUN 并计入未证明。
用法：python mutation_orientation.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
VERIFY = HERE / "verify_orientation.py"
LAYER = GAME / "scripts" / "fighter_3d_layer.gd"
ARENA = GAME / "scripts" / "arena.gd"
FINAL_JSON = HERE / "data" / "final_shot.json"
FINAL_PNG = HERE / "shots" / "final" / "display-live.png"
BEFORE_PNG = BAKE / "display-stopgap" / "shots" / "after-3d" / "display-live.png"

CASES = [
    ("M1", LAYER, b"const DEFAULT_SIDE_YAW := -55.0",
     b"const DEFAULT_SIDE_YAW := 55.0", "A_side_yaw_minus55"),
    ("M2", LAYER, b"const DEFAULT_FOE_YAW := 55.0",
     b"const DEFAULT_FOE_YAW := -55.0", "A_foe_yaw_plus55"),
    ("M3", ARENA, b"Fighter3DLayerScript.DEFAULT_FOE_YAW",
     b"55.0", "A_arena_uses_foe_constant"),
    ("M4", FINAL_JSON, b'"f_yaw": 55.0',
     b'"f_yaw": -55.0', "B_engine_foe_yaw_plus55"),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_verify() -> str:
    p = subprocess.run([sys.executable, "-u", str(VERIFY)],
                       capture_output=True, timeout=180, cwd=str(HERE))
    return (p.stdout + p.stderr).decode("utf-8", "replace")


def main() -> int:
    assert VERIFY.is_file() and BEFORE_PNG.is_file()
    rows = []

    def record(name: str, expect: str, caught: bool, out: str,
               original: bytes, path: Path) -> bool:
        failed_line = next((l for l in out.splitlines()
                            if l.startswith("FAILED ")), "FAILED ")
        caught = caught and "ORIENTATION_FAILED" in out and expect in failed_line
        path.write_bytes(original)
        restored = sha(path.read_bytes()) == sha(original)
        status = "CAUGHT" if caught else "MISSED"
        rows.append({"case": name, "status": status, "expect": expect,
                     "restore_sha_ok": restored, "failed_line": failed_line})
        print(f"CASE {name} {status} expect={expect} restore={restored}")
        return restored

    for name, path, needle, mutant, expect in CASES:
        original = path.read_bytes()
        if needle not in original:
            rows.append({"case": name, "status": "DID NOT RUN",
                         "reason": "anchor not found", "expect": expect})
            print(f"CASE {name} DID NOT RUN (anchor not found)")
            continue
        path.write_bytes(original.replace(needle, mutant, 1))
        out = run_verify()
        failed_line = next((l for l in out.splitlines()
                            if l.startswith("FAILED ")), "FAILED ")
        caught = "ORIENTATION_FAILED" in out and expect in failed_line
        if not record(name, expect, caught, out, original, path):
            print("RESTORE FAILED - abort")
            return 1

    # M5：把改后截图换成改前截图，专门证明「像素 A/B」这条不会真空通过
    original = FINAL_PNG.read_bytes()
    shutil.copyfile(BEFORE_PNG, FINAL_PNG)
    out = run_verify()
    failed_line = next((l for l in out.splitlines()
                        if l.startswith("FAILED ")), "FAILED ")
    caught = ("ORIENTATION_FAILED" in out
              and "C_before_after_pixels_changed" in failed_line)
    if not record("M5", "C_before_after_pixels_changed", caught, out,
                  original, FINAL_PNG):
        print("RESTORE FAILED - abort")
        return 1

    clean = run_verify()
    clean_ok = "ORIENTATION_VERIFIED" in clean and "PASSED 18/18" in clean
    total = len(CASES) + 1
    caught_n = sum(r["status"] == "CAUGHT" for r in rows)
    not_run = sum(r["status"] == "DID NOT RUN" for r in rows)
    restored = sum(r.get("restore_sha_ok") is True for r in rows)
    ok = caught_n == total and not_run == 0 and restored == total and clean_ok
    (HERE / "data" / "mutation_orientation.json").write_text(
        json.dumps({"rows": rows, "caught": caught_n,
                    "did_not_run": not_run, "restored": restored,
                    "clean_rerun_green": clean_ok, "ok": ok},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CAUGHT {caught_n}/{total} DID_NOT_RUN {not_run} "
          f"RESTORE {restored}/{total} CLEAN_GREEN {clean_ok}")
    print("MUTATION_ORIENTATION_OK" if ok else "MUTATION_ORIENTATION_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
