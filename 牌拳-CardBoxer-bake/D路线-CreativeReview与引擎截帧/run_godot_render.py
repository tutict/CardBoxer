"""D 路线驱动：隔离工程导入 GLB → **带窗口** Godot 逐视角渲染 → 落 PNG 与报告。

关键：渲染这一步绝不能加 --headless。本机实测 dummy driver 不发
RenderingServer.frame_post_draw（外观层 capture_skin.py 踩过），脚本会挂住。
--quit-after 只是挂起保护，脚本自己 quit(0)。

用法：
  python run_godot_render.py front,back     # 小探针
  python run_godot_render.py                # 全六视角
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
C_ROUTE = BAKE / "C路线-glTF-Godot探针"
PROJECT = HERE / "probe_project_d"
ASSETS = PROJECT / "assets"
SHOTS = HERE / "shots"
LOGS = HERE / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
GLB = "foe-full.glb"
OUT = HERE / "godot_render_result.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], env: dict, timeout: int, log: Path):
    t0 = time.perf_counter()
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, timeout=timeout)
        code, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as exc:
        code = -1
        out = exc.stdout or b""
        err = (exc.stderr or b"") + b"\n=== TIMEOUT ===\n"
    text = (out + b"\n=== STDERR ===\n" + err).decode("utf-8", "replace")
    log.write_text(text, encoding="utf-8")
    return round(time.perf_counter() - t0, 3), code, text


def main() -> int:
    assert GODOT.is_file(), GODOT
    LOGS.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    views = sys.argv[1] if len(sys.argv) > 1 else ""

    # 1) 资源复制 + 编辑器导入（这一步可以 headless）
    src = C_ROUTE / GLB
    dst = ASSETS / GLB
    shutil.copyfile(src, dst)
    copied_ok = sha256(src) == sha256(dst)
    print(f"COPIED {GLB} bytes={dst.stat().st_size} identical={copied_ok}")
    if not copied_ok:
        return 1

    base_env = os.environ.copy()
    dt_import, rc_import, log_import = run(
        [str(GODOT), "--headless", "--editor", "--quit",
         "--path", str(PROJECT)],
        base_env, 300, LOGS / "godot_editor_import_d.log")
    import_ok = (ASSETS / (GLB + ".import")).is_file()
    print(f"EDITOR_IMPORT seconds={dt_import} rc={rc_import} "
          f"import_file={import_ok}")
    if rc_import != 0 or not import_ok:
        return 1

    # 2) 带窗口渲染
    env = base_env.copy()
    env["D_SHOT_DIR"] = str(SHOTS)
    env["D_VIEWS"] = views
    dt_render, rc_render, log_render = run(
        [str(GODOT), "--path", str(PROJECT),
         "--resolution", "900x1100",
         "--script", "res://probes/render_3d.gd",
         "--quit-after", "6000"],
        env, 300, LOGS / "godot_render_3d.log")

    marker = "RENDER_JSON "
    line = next((l for l in log_render.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no RENDER_JSON"}
    rows = payload.get("views", [])
    pngs = []
    for row in rows:
        p = Path(row["path"])
        pngs.append({
            "name": row["name"], "path": str(p),
            "exists": p.is_file(),
            "bytes": p.stat().st_size if p.is_file() else 0,
            "w": row.get("w"), "h": row.get("h"),
            "save_error": row.get("save_error"),
            "yaw": row.get("yaw"), "radius": row.get("radius"),
            "fov": row.get("fov"),
        })

    has_gl = "OpenGL API" in log_render
    script_errors = log_render.count("SCRIPT ERROR")
    ok = (rc_render == 0 and has_gl and script_errors == 0
          and "error" not in payload and bool(pngs)
          and all(x["exists"] and x["bytes"] > 20000 for x in pngs)
          and all(x["save_error"] == 0 for x in pngs))
    out = {
        "godot_executable": str(GODOT),
        "probe_project": str(PROJECT),
        "views_requested": views or "ALL",
        "copy_identical": copied_ok,
        "editor_import": {"seconds": dt_import, "returncode": rc_import,
                          "import_file": import_ok},
        "render": {"seconds": dt_render, "returncode": rc_render,
                   "has_opengl": has_gl, "script_errors": script_errors,
                   "headless": False},
        "engine_version_marker": "4.5-stable",
        "pngs": pngs,
        "ok": ok,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for x in pngs:
        print(f"SHOT {x['name']:<9} {x['w']}x{x['h']} {x['bytes']:>9} B "
              f"err={x['save_error']}")
    print(f"RENDER seconds={dt_render} rc={rc_render} gl={has_gl} "
          f"errs={script_errors} shots={len(pngs)}")
    print("GODOT_RENDER_OK" if ok else "GODOT_RENDER_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
