"""隔离 Godot 工程导入探针的驱动脚本：复制 GLB → 编辑器导入 → 引擎内读回。

游戏工程 C:\\...\\CardBoxer 全程零改动；探针工程在 WORK/probe_project/。
计时用 Python 的 perf_counter，避免 Godot 内部时间受渲染器影响。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "probe_project"
ASSETS = PROJECT / "assets"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
GLBS = ["foe-full.glb", "foe-stance.glb", "foe-proxy-rig.glb"]
OUT = HERE / "godot_import_result.json"
LOG_IMPORT = HERE / "logs" / "godot_editor_import.log"
LOG_PROBE = HERE / "logs" / "godot_inspect_probe.log"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_bytes(p: Path) -> tuple[int, int]:
    if not p.is_dir():
        return 0, 0
    files = [x for x in p.rglob("*") if x.is_file()]
    return len(files), sum(x.stat().st_size for x in files)


def timed(cmd: list[str], timeout: int = 300):
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return round(time.perf_counter() - t0, 3), r


def main() -> int:
    assert GODOT.is_file(), GODOT
    ASSETS.mkdir(parents=True, exist_ok=True)
    copies = []
    for name in GLBS:
        src, dst = HERE / name, ASSETS / name
        shutil.copyfile(src, dst)
        copies.append({"file": name, "bytes": dst.stat().st_size,
                       "sha256": sha256(dst),
                       "identical": sha256(src) == sha256(dst)})
    assert all(c["identical"] for c in copies), copies
    print(f"COPIED={len(copies)} total_bytes={sum(c['bytes'] for c in copies)}")

    # 1) 编辑器导入：生成 .import 与 .godot/imported/*
    dt1, r1 = timed([str(GODOT), "--headless", "--editor", "--quit",
                     "--path", str(PROJECT)])
    LOG_IMPORT.write_text(
        (r1.stdout or "") + "\n=== STDERR ===\n" + (r1.stderr or ""),
        encoding="utf-8")
    print(f"EDITOR_IMPORT seconds={dt1} returncode={r1.returncode}")

    imports = []
    for name in GLBS:
        imp = ASSETS / (name + ".import")
        imports.append({"file": name + ".import", "exists": imp.is_file(),
                        "bytes": imp.stat().st_size if imp.is_file() else 0})
    imported_dir = PROJECT / ".godot" / "imported"
    n_imported, b_imported = dir_bytes(imported_dir)

    # 2) 引擎内读回资源结构
    dt2, r2 = timed([str(GODOT), "--headless", "--path", str(PROJECT),
                     "--script", "res://probes/inspect_import.gd"])
    LOG_PROBE.write_text(
        (r2.stdout or "") + "\n=== STDERR ===\n" + (r2.stderr or ""),
        encoding="utf-8")
    print(f"INSPECT_PROBE seconds={dt2} returncode={r2.returncode}")

    marker = "PROBE_JSON "
    line = next((l for l in (r2.stdout or "").splitlines()
                 if l.startswith(marker)), None)
    if line is None:
        print("PROBE_JSON_MISSING stdout_head="
              + repr((r2.stdout or "")[:400]))
        return 1
    probe = json.loads(line[len(marker):])

    out = {
        "godot_executable": str(GODOT),
        "probe_project": str(PROJECT),
        "copies": copies,
        "editor_import": {
            "seconds": dt1, "returncode": r1.returncode,
            "import_files": imports,
            "all_import_files_present": all(i["exists"] for i in imports),
            "imported_files": n_imported,
            "imported_bytes": b_imported,
        },
        "inspect_probe": {"seconds": dt2, "returncode": r2.returncode},
        "engine": probe["engine"],
        "targets": probe["targets"],
        "total_wall_seconds": round(dt1 + dt2, 3),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for t in probe["targets"]:
        print(f"{Path(t['path']).name:<20} load_ok={t['load_ok']} "
              f"class={t['resource_class']} nodes={t['node_count']} "
              f"meshes={len(t['mesh_instances'])} "
              f"skels={len(t['skeletons'])} "
              f"anim_players={len(t['animation_players'])}")
    print(f"IMPORT_BYTES={b_imported} FILES={n_imported} "
          f"WALL={out['total_wall_seconds']}s")
    print("GODOT_IMPORT_PROBE_OK"
          if out["editor_import"]["all_import_files_present"]
          and all(t["load_ok"] for t in probe["targets"])
          else "GODOT_IMPORT_PROBE_FAILED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
