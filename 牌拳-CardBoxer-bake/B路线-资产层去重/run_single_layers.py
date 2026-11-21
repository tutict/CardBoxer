"""用同一份单层探针分别渲染 foe / player，杜绝多 viewport 标签错位。

输出 shots/single/single-foe.png、single-player.png 与
data/single_layers.json（含逐图像素统计、两图 sha256、材质读回）。
用法：python run_single_layers.py
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
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "single_layer_probe.gd"
DST = GAME / "tests" / "single_layer_probe.gd"
OUTDIR = HERE / "shots" / "single"
OUT = HERE / "data" / "single_layers.json"
LOGDIR = HERE / "logs"
MARKER = "SINGLE_JSON "

SPECS = [
    {"role": "foe", "glb": "res://assets/3d/foe-rigged.glb",
     "yaw": 55.0, "expect_verts": 64059,
     "expect_albedo": "foe-rigged_texture_pbr_20250901.png"},
    {"role": "player", "glb": "res://assets/3d/player-rigged.glb",
     "yaw": -55.0, "expect_verts": 57934,
     "expect_albedo": "player-rigged_texture_pbr_20250901.png"},
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pixel_stats(p: Path) -> dict:
    im = Image.open(p).convert("RGBA")
    opaque = white = cyan = bright = 0
    for r, g, b, a in im.getdata():
        if a < 32:
            continue
        opaque += 1
        if r > 175 and g > 175 and b > 175:
            white += 1
        if b > 110 and g > 110 and r < g - 18:
            cyan += 1
        if max(r, g, b) > 200:
            bright += 1
    return {"opaque_px": opaque, "near_white_px": white,
            "cyan_px": cyan, "bright_px": bright,
            "white_ratio": round(white / max(1, opaque), 6)}


def one(spec: dict) -> dict:
    env = os.environ.copy()
    for k in ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW",
              "CARD_BOXER_3D_FLIP", "CARD_BOXER_3D_STANCE"):
        env.pop(k, None)
    env["CARD_BOXER_FOE_VISUAL"] = "none"
    env["SINGLE_OUT"] = str(OUTDIR)
    env["SINGLE_ROLE"] = spec["role"]
    env["SINGLE_GLB"] = spec["glb"]
    env["SINGLE_YAW"] = str(spec["yaw"])
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "900", "--script",
         "res://tests/single_layer_probe.gd"],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    text = (proc.stdout + b"\n--- STDERR ---\n"
            + proc.stderr).decode("utf-8", "replace")
    (LOGDIR / f"godot_single_{spec['role']}.log").write_text(
        text, encoding="utf-8")
    line = next((l for l in text.splitlines()
                 if l.startswith(MARKER)), None)
    payload = json.loads(line[len(MARKER):]) if line else {"error": "no marker"}
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    p = Path(payload.get("sv_png", ""))
    mesh = (payload.get("meshes") or [{}])[0]
    rec = {
        "role": spec["role"], "seconds": round(time.perf_counter() - t0, 3),
        "rc": proc.returncode, "script_errors": errors,
        "payload": payload, "mesh": mesh,
        "png": str(p), "png_sha256": sha256(p) if p.is_file() else "",
        "pixels": pixel_stats(p) if p.is_file() else {},
    }
    rec["checks"] = {
        "rc": proc.returncode == 0,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "role_matches": payload.get("role") == spec["role"],
        "glb_matches": payload.get("glb") == spec["glb"],
        "yaw_matches": abs(payload.get("yaw", 0.0) - spec["yaw"]) < 0.01,
        "verts_match": mesh.get("verts") == spec["expect_verts"],
        "albedo_match": str(mesh.get("albedo", "")).endswith(
            spec["expect_albedo"]),
        "one_surface": mesh.get("surfaces") == 1,
        "png_written": p.is_file() and payload.get("sv_error") == 0,
        # 非空下限：全透明 PNG 也能「保存成功」，必须挡住真空通过。
        "png_not_blank": rec["pixels"].get("opaque_px", 0) > 10000,
    }
    rec["ok"] = all(rec["checks"].values())
    return rec


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    recs = [one(s) for s in SPECS]
    by_role = {r["role"]: r for r in recs}
    pf, pp = by_role["foe"], by_role["player"]
    checks = {
        "both_runs_ok": all(r["ok"] for r in recs),
        "two_pngs_distinct": pf["png_sha256"] != pp["png_sha256"],
        "two_albedo_distinct": (
            pf["mesh"].get("albedo") != pp["mesh"].get("albedo")),
        "foe_and_player_verts_distinct": (
            pf["mesh"].get("verts") != pp["mesh"].get("verts")),
        # 单层取证里，player 的近白/青像素必须显著高于 foe：
        # 这才是「白布青云纹属于哪一侧」的干净判据。
        "player_is_the_white_one": (
            pp["pixels"]["near_white_px"]
            > 3 * max(1, pf["pixels"]["near_white_px"])),
        "player_is_the_cyan_one": (
            pp["pixels"]["cyan_px"]
            > 2 * max(1, pf["pixels"]["cyan_px"])),
    }
    ok = all(checks.values())
    report = {
        "runs": recs, "checks": checks,
        "failed": [k for k, v in checks.items() if not v], "ok": ok,
        "conclusion": (
            "同一份单层探针分别渲染两侧，排除多 viewport 取图标签错位；"
            "近白/青像素更高的一侧才是真正带白布青云纹的资产。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                   + "\n", encoding="utf-8")
    for r in recs:
        print(r["role"], "rc", r["rc"], "errs", r["script_errors"],
              "verts", r["mesh"].get("verts"),
              "albedo", r["mesh"].get("albedo"),
              "pixels", r["pixels"], "sha", r["png_sha256"][:12])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("SINGLE_LAYERS_OK" if ok else "SINGLE_LAYERS_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
