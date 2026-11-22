"""G 路线 A/B：从 orig/pre-3d 造一份可运行的「改动前」游戏工程副本。

副本是独立 Godot 工程，注入式截帧在它上面跑，不与当前工程抢资源。
用法：python make_baseline_project_g.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIG = HERE / "orig" / "pre-3d"
PROJECT = HERE / "baseline_project"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "data" / "baseline_project_g.json"
LOGS = HERE / "logs"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    assert ORIG.is_dir(), ORIG
    assert GODOT.is_file(), GODOT
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if PROJECT.is_dir():
        shutil.rmtree(PROJECT)
    PROJECT.mkdir(parents=True)

    rows = []
    for p in sorted(ORIG.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ORIG)
        dst = PROJECT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dst)
        rows.append({"rel": str(rel).replace("\\", "/"),
                     "sha256": sha256(p),
                     "identical": sha256(p) == sha256(dst)})

    t0 = time.perf_counter()
    env = os.environ.copy()
    proc = subprocess.run(
        [str(GODOT), "--headless", "--editor", "--quit",
         "--path", str(PROJECT)],
        env=env, capture_output=True, timeout=300, cwd=str(PROJECT))
    dt = round(time.perf_counter() - t0, 3)
    (LOGS / "godot_editor_import_baseline_project.log").write_bytes(
        proc.stdout + b"\n--- STDERR ---\n" + proc.stderr)
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")

    checks = {
        "copied_105": len(rows) == 105,
        "all_identical": all(r["identical"] for r in rows),
        "import_rc": proc.returncode == 0,
        "import_no_errors": errors == 0,
        "project_godot_present": (PROJECT / "project.godot").is_file(),
        "no_3d_assets": not (PROJECT / "assets" / "3d").exists(),
        "no_rig_driver": not (PROJECT / "scripts" / "rig_driver.gd").exists(),
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "project": str(PROJECT), "files": len(rows),
        "import": {"seconds": dt, "returncode": proc.returncode,
                   "errors": errors},
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BASELINE_PROJECT files={len(rows)} import_rc={proc.returncode} "
          f"{dt}s errors={errors}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("BASELINE_PROJECT_G_OK" if ok else "BASELINE_PROJECT_G_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
