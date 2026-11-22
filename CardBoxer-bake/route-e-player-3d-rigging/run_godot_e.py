"""E 路线驱动：复制玩家 GLB 到隔离工程 → Godot 4.5 导入 → 引擎内读回结构。

游戏工程全程零改动；探针工程在 E路线/probe_project_e/。
用法：python run_godot_e.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "probe_project_e"
ASSETS = PROJECT / "assets"
LOGS = HERE / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
GLBS = ["player-full.glb", "player-stance.glb", "player-proxy-rig.glb"]
OUT = HERE / "godot_e_result.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_bytes(p: Path):
    if not p.is_dir():
        return 0, 0
    files = [x for x in p.rglob("*") if x.is_file()]
    return len(files), sum(x.stat().st_size for x in files)


def timed(cmd, timeout=300):
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return round(time.perf_counter() - t0, 3), r


def main() -> int:
    assert GODOT.is_file(), GODOT
    ASSETS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    copies = []
    for name in GLBS:
        src, dst = HERE / name, ASSETS / name
        shutil.copyfile(src, dst)
        copies.append({"file": name, "bytes": dst.stat().st_size,
                       "sha256": sha256(dst),
                       "identical": sha256(src) == sha256(dst)})
    assert all(c["identical"] for c in copies), copies
    print(f"COPIED={len(copies)} total_bytes={sum(c['bytes'] for c in copies)}")

    dt1, r1 = timed([str(GODOT), "--headless", "--editor", "--quit",
                     "--path", str(PROJECT)])
    (LOGS / "godot_editor_import_e.log").write_text(
        (r1.stdout or "") + "\n=== STDERR ===\n" + (r1.stderr or ""),
        encoding="utf-8")
    imports = [{"file": n + ".import",
                "exists": (ASSETS / (n + ".import")).is_file()}
               for n in GLBS]
    n_imp, b_imp = dir_bytes(PROJECT / ".godot" / "imported")
    print(f"EDITOR_IMPORT seconds={dt1} rc={r1.returncode} "
          f"all_import_files={all(x['exists'] for x in imports)}")

    dt2, r2 = timed([str(GODOT), "--headless", "--path", str(PROJECT),
                     "--script", "res://probes/inspect_e.gd"])
    (LOGS / "godot_inspect_e.log").write_text(
        (r2.stdout or "") + "\n=== STDERR ===\n" + (r2.stderr or ""),
        encoding="utf-8")
    marker = "PROBE_JSON "
    line = next((l for l in (r2.stdout or "").splitlines()
                 if l.startswith(marker)), None)
    if line is None:
        print("PROBE_JSON_MISSING head=" + repr((r2.stdout or "")[:400]))
        return 1
    probe = json.loads(line[len(marker):])

    log_text = (LOGS / "godot_inspect_e.log").read_text(
        encoding="utf-8", errors="replace")
    out = {
        "godot_executable": str(GODOT), "probe_project": str(PROJECT),
        "copies": copies,
        "editor_import": {"seconds": dt1, "returncode": r1.returncode,
                          "import_files": imports,
                          "imported_files": n_imp, "imported_bytes": b_imp},
        "inspect_probe": {"seconds": dt2, "returncode": r2.returncode,
                          "script_errors": log_text.count("SCRIPT ERROR")},
        "engine": probe["engine"], "targets": probe["targets"],
        "total_wall_seconds": round(dt1 + dt2, 3),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for t in probe["targets"]:
        print(f"{Path(t['path']).name:<22} load_ok={t['load_ok']} "
              f"nodes={t['node_count']} meshes={len(t['mesh_instances'])} "
              f"skels={len(t['skeletons'])} "
              f"anim_players={len(t['animation_players'])}")
    ok = (r1.returncode == 0 and r2.returncode == 0
          and all(x["exists"] for x in imports)
          and all(t["load_ok"] for t in probe["targets"])
          and out["inspect_probe"]["script_errors"] == 0)
    print(f"IMPORT_BYTES={b_imp} WALL={out['total_wall_seconds']}s")
    print("GODOT_IMPORT_E_OK" if ok else "GODOT_IMPORT_E_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
