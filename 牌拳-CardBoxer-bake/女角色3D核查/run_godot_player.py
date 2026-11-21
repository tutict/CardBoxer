"""给女角色建 Godot 展示工程并渲引擎内四视角。

关键：渲染这一步绝不能加 --headless（dummy driver 不发
RenderingServer.frame_post_draw，D 路线已实测）。editor 导入可以 headless。
渲染脚本加载的是 project.godot 的 main_scene，所以「用户打开能看见」
与「自动截图」是同一条场景链，不是两套口径。

用法：python run_godot_player.py [front,back,...]
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
E_ROUTE = BAKE / "E路线-玩家3D绑骨"
PROJECT = HERE / "probe_project_player"
ASSETS = PROJECT / "assets"
SHOTS = HERE / "shots"
LOGS = HERE / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
GLB = "player-full.glb"
OUT = HERE / "godot_player_result.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_vis(line: str) -> dict:
    out = {"hidden_proxy_shell": -1, "visible_highpoly": -1}
    for part in line.split():
        if "=" in part:
            key, val = part.split("=", 1)
            if key in out and val.lstrip("-").isdigit():
                out[key] = int(val)
    return out


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

    src = E_ROUTE / GLB
    dst = ASSETS / GLB
    shutil.copyfile(src, dst)
    copied_ok = sha256(src) == sha256(dst)
    print(f"COPIED {GLB} bytes={dst.stat().st_size} identical={copied_ok}")
    if not copied_ok:
        return 1

    base_env = os.environ.copy()
    dt_import, rc_import, _ = run(
        [str(GODOT), "--headless", "--editor", "--quit",
         "--path", str(PROJECT)],
        base_env, 300, LOGS / "godot_editor_import_player.log")
    import_ok = (ASSETS / (GLB + ".import")).is_file()
    print(f"EDITOR_IMPORT seconds={dt_import} rc={rc_import} "
          f"import_file={import_ok}")
    if rc_import != 0 or not import_ok:
        return 1

    env = base_env.copy()
    env["P_SHOT_DIR"] = str(SHOTS)
    env["P_VIEWS"] = views
    dt_render, rc_render, log_render = run(
        [str(GODOT), "--path", str(PROJECT),
         "--resolution", "900x1100",
         "--script", "res://probes/render_player.gd",
         "--quit-after", "6000"],
        env, 300, LOGS / "godot_render_player.log")

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
        })
    lines = log_render.splitlines()
    init_vis = parse_vis(next((l for l in lines
                               if l.startswith("SCENE_LOADED ")), ""))
    ready_vis = parse_vis(next((l for l in lines
                                if l.startswith("SHOWCASE_READY ")), ""))
    frame_vis = parse_vis(next((l for l in lines
                                if l.startswith("FRAME_VISIBILITY ")), ""))
    hidden_shell = frame_vis["hidden_proxy_shell"]
    highpoly = frame_vis["visible_highpoly"]
    # SHOWCASE_READY 行只打印代理壳数与相机名，不打印高模数；
    # 高模可见性由 FRAME_VISIBILITY（抓帧前）单独证明。
    ready_ok = ready_vis["hidden_proxy_shell"] == 1
    has_gl = "OpenGL API" in log_render
    script_errors = log_render.count("SCRIPT ERROR")
    ok = (rc_render == 0 and has_gl and script_errors == 0
          and "error" not in payload and bool(pngs)
          and hidden_shell == 1 and highpoly == 1 and ready_ok
          and all(x["exists"] and x["bytes"] > 20000
                  and x["save_error"] == 0
                  and x["w"] == 900 and x["h"] == 1100 for x in pngs))
    out = {
        "godot_executable": str(GODOT),
        "probe_project": str(PROJECT),
        "main_scene": "res://scenes/player_showcase.tscn",
        "source_glb": str(src),
        "source_glb_sha256": sha256(src),
        "copy_identical": copied_ok,
        "editor_import": {"seconds": dt_import, "returncode": rc_import,
                          "import_file": import_ok},
        "render": {"seconds": dt_render, "returncode": rc_render,
                   "has_opengl": has_gl, "script_errors": script_errors,
                   "headless": False},
        "scene": {"init_before_ready": init_vis,
                  "after_ready": ready_vis,
                  "at_capture": frame_vis,
                  "hidden_proxy_shell": hidden_shell,
                  "visible_highpoly": highpoly,
                  "ready_ok": ready_ok},
        "views_requested": views or "ALL",
        "pngs": pngs,
        "ok": ok,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for x in pngs:
        print(f"SHOT {x['name']:<9} {x['w']}x{x['h']} {x['bytes']:>9} B "
              f"err={x['save_error']}")
    print(f"RENDER seconds={dt_render} rc={rc_render} gl={has_gl} "
          f"errs={script_errors} hidden_shell={hidden_shell} "
          f"highpoly={highpoly} shots={len(pngs)}")
    print("GODOT_PLAYER_OK" if ok else "GODOT_PLAYER_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
