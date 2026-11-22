"""Prove the fighter-skin guard actually has teeth.

Three mutants, each syntactically valid GDScript (a broken file proves nothing):
  A  SKIN_V2 true -> false          : the layer is disconnected
  B  the _draw() call -> pass       : the layer exists but is never invoked
  C  drop "chinese_knot" from PARTS : a costume part silently disappears

Discipline:
  * binary read/write only, anchor must match exactly once
  * every mutant is restored in a finally block and proven by sha256
  * an anchor miss is DID NOT RUN and counts as NOT PROVEN, never as caught
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
FIGHTER = GAME / "scripts" / "fighter.gd"
SKIN = GAME / "scripts" / "fighter_skin.gd"
CHECK = "res://tests/fighter_skin_check.gd"

CASES = [
    {
        "name": "A_SKIN_V2_OFF",
        "path": FIGHTER,
        "needle": b"const SKIN_V2 := true",
        "mutant": b"const SKIN_V2 := false",
    },
    {
        "name": "B_CALL_REMOVED",
        "path": FIGHTER,
        "needle": b"\t\t_draw_skin_v2(p, body, trim, flash_mix)",
        "mutant": b"\t\tpass",
    },
    {
        "name": "C_PART_DELETED",
        "path": SKIN,
        "needle": b'\t"chinese_knot", "double_bun", "pom_pom", "hair_clip",',
        "mutant": b'\t"double_bun", "pom_pom", "hair_clip",',
    },
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_check() -> tuple[int, bytes]:
    proc = subprocess.run(
        [str(GODOT), "--headless", "--path", str(GAME), "--script", CHECK],
        capture_output=True,
        timeout=180,
    )
    return proc.returncode, proc.stdout + b"\n" + proc.stderr


def main() -> int:
    originals = {p: p.read_bytes() for p in (FIGHTER, SKIN)}
    results: list[str] = []

    try:
        # Baseline: the guard must pass on the unmodified tree.
        rc, out = run_check()
        baseline_ok = rc == 0 and b"FIGHTER SKIN CHECK: PASS" in out
        print("BASELINE: %s (rc=%d)" % ("PASS" if baseline_ok else "FAIL", rc))
        if not baseline_ok:
            print(b"".join(out.splitlines(keepends=True)[-12:]).decode("utf-8", "replace"))
            return 1

        for case in CASES:
            path: Path = case["path"]
            orig = originals[path]
            needle: bytes = case["needle"]
            mutant: bytes = case["mutant"]
            count = orig.count(needle)
            if count != 1:
                results.append("DID NOT RUN %s anchor_count=%d" % (case["name"], count))
                print("%s: DID NOT RUN (anchor matched %d times)" % (case["name"], count))
                continue

            changed = orig.replace(needle, mutant, 1)
            if changed == orig:
                results.append("DID NOT RUN %s no_op" % case["name"])
                print("%s: DID NOT RUN (mutant == original)" % case["name"])
                continue

            path.write_bytes(changed)
            if sha(path.read_bytes()) != sha(changed):
                results.append("WRITE_VERIFY_FAILED %s" % case["name"])
                print("%s: WRITE_VERIFY_FAILED" % case["name"])
                path.write_bytes(orig)
                continue

            try:
                rc, out = run_check()
            except subprocess.TimeoutExpired:
                results.append("TIMEOUT %s" % case["name"])
                print("%s: TIMEOUT" % case["name"])
                path.write_bytes(orig)
                continue

            fail_marker = b"FIGHTER SKIN CHECK: FAIL" in out
            parse_error = b"Parse Error" in out or b"SCRIPT ERROR" in out
            caught = rc != 0 and fail_marker and not parse_error
            fail_lines = [
                ln.strip().decode("utf-8", "replace")
                for ln in out.splitlines()
                if ln.strip().startswith(b"FAIL:")
            ]
            print(
                "%s: rc=%d guard_fail=%s parse_error=%s -> %s"
                % (case["name"], rc, fail_marker, parse_error, "CAUGHT" if caught else "MISSED")
            )
            for line in fail_lines[:4]:
                print("    " + line)
            results.append(
                "CAUGHT %s" % case["name"]
                if caught
                else "MISSED %s (rc=%d fail=%s parse=%s)" % (case["name"], rc, fail_marker, parse_error)
            )

            path.write_bytes(orig)
    finally:
        for path, orig in originals.items():
            path.write_bytes(orig)
            ok = sha(path.read_bytes()) == sha(orig)
            print("RESTORE %s %s sha256=%s" % (path.name, "OK" if ok else "FAILED", sha(path.read_bytes())))
            if not ok:
                results.append("RESTORE FAILED %s" % path.name)

    print("")
    print("RESULT: " + " | ".join(results))
    expected = len(CASES)
    caught = sum(1 for r in results if r.startswith("CAUGHT "))
    restored = all("RESTORE FAILED" not in r for r in results)
    return 0 if caught == expected and restored and "RESTORE OK" not in results else 1


if __name__ == "__main__":
    raise SystemExit(main())
