"""G 路线 P0 技术探针：2D 主视口 + 3D SubViewport 混合渲染能否成立。

只读 F 路线已交付的 player-rigged.glb，复制到隔离工程，
editor 导入后带窗口截一张 1280x720，用 Pillow 证明 3D 区域真的有内容。
用法：python run_probe_subviewport.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
F = BAKE / "F路线-Godot驱动层"
PROJECT = HERE / "probe_project_g"
ASSETS = PROJECT / "assets"
SHOTS = HERE / "shots"
LOGS = HERE / "logs"
DATA = HERE / "data"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
GLB = "player-rigged.glb"
OUT = DATA / "subviewport_probe.json"

VIEW_BOX = (340, 80, 940, 640)     # 3D SubViewport 贴到 2D 的位置
RED_BOX = (40, 120, 220, 540)      # 2D 绘制链锚点


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


def pixels(path: Path) -> dict:
    im = Image.open(path).convert("RGB")
    view = im.crop(VIEW_BOX)
    red = im.crop(RED_BOX)
    bright = 0
    colors = set()
    for r, g, b in view.get_flattened_data():
        if r + g + b > 150:
            bright += 1
        colors.add((r // 8, g // 8, b // 8))
    red_px = sum(1 for r, g, b in red.get_flattened_data()
                 if r > 100 and r > g * 2)
    return {
        "w": im.width, "h": im.height,
        "view_bright_px": bright,
        "view_color_bins": len(colors),
        "red_anchor_px": red_px,
    }


def main() -> int:
    assert GODOT.is_file(), GODOT
    for d in (ASSETS, SHOTS, LOGS, DATA):
        d.mkdir(parents=True, exist_ok=True)
    src = F / GLB
    dst = ASSETS / GLB
    assert src.is_file(), src
    shutil.copyfile(src, dst)
    src_sha, dst_sha = sha256(src), sha256(dst)
    assert src_sha == dst_sha

    env = os.environ.copy()
    dt_import, rc_import, _ = run(
        [str(GODOT), "--headless", "--editor", "--quit",
         "--path", str(PROJECT)],
        env, 300, LOGS / "godot_editor_import_g.log")

    env["G_SHOT_DIR"] = str(SHOTS)
    dt, rc, log = run(
        [str(GODOT), "--path", str(PROJECT),
         "--resolution", "1280x720",
         "--script", "res://probes/probe_subviewport.gd",
         "--quit-after", "6000"],
        env, 300, LOGS / "godot_subviewport.log")

    marker = "SV_JSON "
    line = next((l for l in log.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no SV_JSON"}
    p = Path(payload.get("path", "")) if payload.get("path") else None
    stats = pixels(p) if p and p.is_file() else {}
    has_gl = "OpenGL API" in log
    errors = log.count("SCRIPT ERROR")

    checks = {
        "import_rc": rc_import == 0,
        "render_rc": rc == 0,
        "has_opengl": has_gl,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "texture_drawn": payload.get("tex_ok") is True,
        "save_ok": payload.get("save_error") == 0,
        "size_1280x720": stats.get("w") == 1280 and stats.get("h") == 720,
        "canvas_redrawn": int(payload.get("draw_count", 0)) >= 2,
        "3d_region_nonblank": stats.get("view_bright_px", 0) > 20000,
        "3d_region_textured": stats.get("view_color_bins", 0) > 200,
        "2d_anchor_visible": stats.get("red_anchor_px", 0) > 50000,
        "glb_identical": src_sha == dst_sha,
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "src": str(src), "src_sha256": src_sha,
        "import": {"seconds": dt_import, "returncode": rc_import},
        "render": {"seconds": dt, "returncode": rc,
                   "has_opengl": has_gl, "script_errors": errors,
                   "headless": False},
        "payload": payload, "pixels": stats,
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"IMPORT rc={rc_import} {dt_import}s  RENDER rc={rc} {dt}s "
          f"gl={has_gl} errs={errors}")
    print(f"PAYLOAD tex_ok={payload.get('tex_ok')} "
          f"draw_count={payload.get('draw_count')} "
          f"sv_size={payload.get('sv_size')} "
          f"save_error={payload.get('save_error')}")
    print(f"PIXELS {stats}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("SUBVIEWPORT_PROBE_OK" if ok else "SUBVIEWPORT_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
