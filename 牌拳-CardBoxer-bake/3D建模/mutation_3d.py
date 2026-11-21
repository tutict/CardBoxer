"""Load-bearing mutation checks for verify_3d.py.

A guard that has never been shown to go red is not a guard. Three mutants,
each restored with a binary write + sha256 proof (text-mode restore silently
changes line endings on this machine):

  M1  replace the repeat render with a DIFFERENT pose
      -> repeat_pixels_identical / repeat_bytes_fully_explained must FAIL
  M2  corrupt one skinned part's vertex weight in rig_stats.json
      -> rig_is_real must FAIL
  M3  flatten every skinned part to 2 lateral layers (a 2.5D ribbon)
      -> mesh_has_depth must FAIL
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe"
VERIFY = HERE / "verify_3d.py"
REPEAT = HERE / "3d-stance_repeat.png"
JAB = HERE / "3d-jab_impact.png"
RIG = HERE / "rig_stats.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_verify():
    p = subprocess.run([PY, "-u", str(VERIFY)], capture_output=True, text=True,
                       cwd=str(HERE), encoding="utf-8", errors="replace")
    lines = p.stdout.splitlines()
    fails = [ln.split(":", 1)[0].replace("FAIL ", "").strip()
             for ln in lines if ln.startswith("FAIL ")]
    return p.returncode, fails, lines


def mutate(path: Path, payload: bytes, expect: list[str], label: str) -> bool:
    original = path.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    path.write_bytes(payload)
    rc, fails, lines = run_verify()
    hit = [e for e in expect if e in fails]
    caught = rc != 0 and len(hit) == len(expect)
    path.write_bytes(original)  # binary, no newline translation
    after = sha(path)
    restored = after == before
    verdict = "CAUGHT" if (caught and restored) else "MISSED"
    print(f"{label} {verdict} rc={rc} expected={expect} got_fails={fails} "
          f"restored={restored} sha={after[:12]}", flush=True)
    if not caught:
        for ln in lines[:6]:
            print("   " + ln, flush=True)
    return caught and restored


results = []

# M1
results.append(mutate(REPEAT, JAB.read_bytes(),
                      ["repeat_pixels_identical", "repeat_bytes_fully_explained"], "M1"))

# M2
rig_orig = RIG.read_bytes()
d = json.loads(rig_orig.decode("utf-8"))
d["skinned"][0]["weight_total_min"] = 0.5
results.append(mutate(RIG, json.dumps(d, ensure_ascii=False, indent=2).encode("utf-8"),
                      ["rig_is_real"], "M2"))

# M3
d = json.loads(rig_orig.decode("utf-8"))
for part in d["skinned"]:
    part["distinct_y_levels"] = 2
    part["lateral_span_m"] = 0.01
results.append(mutate(RIG, json.dumps(d, ensure_ascii=False, indent=2).encode("utf-8"),
                      ["mesh_has_depth"], "M3"))

# final clean run (also rewrites verify_3d_result.json back to the green state)
rc, fails, lines = run_verify()
final_green = rc == 0 and not fails
print(f"FINAL rc={rc} fails={fails} green={final_green}", flush=True)
print(f"MUTATIONS {sum(results)}/{len(results)} CAUGHT", flush=True)
print("MUTATION_OK" if all(results) and final_green else "MUTATION_FAILED", flush=True)
raise SystemExit(0 if all(results) and final_green else 1)
