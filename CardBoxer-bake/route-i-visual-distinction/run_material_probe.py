"""I 路线 P0：驱动 Godot 材质探针，落盘可复算的材质结构。

把 tests/material_probe.gd 复制进游戏工程（新增文件，不改既有），
headless 跑 Godot 4.5，解析 IMAT_JSON 并判定「运行时 tint 可行」。
用法：python run_material_probe.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "material_probe.gd"
DST = GAME / "tests" / "material_probe.gd"
OUT = HERE / "data" / "material_i.json"
LOG = HERE / "logs" / "godot_material_probe.log"


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    p = subprocess.run(
        [str(GODOT), "--headless", "--path", str(GAME),
         "--script", "res://tests/material_probe.gd"],
        capture_output=True, timeout=180, cwd=str(GAME))
    text = (p.stdout + b"\n--- STDERR ---\n"
            + p.stderr).decode("utf-8", "replace")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(text, encoding="utf-8")
    marker = "IMAT_JSON "
    line = next((l for l in text.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    surfaces = {k: v.get("surfaces", []) for k, v in payload.items()
                if isinstance(v, dict)}
    standard = {k: [s for s in v
                    if s.get("material_class") == "StandardMaterial3D"]
                for k, v in surfaces.items()}
    checks = {
        "rc0": p.returncode == 0,
        "marker_present": line is not None,
        "no_parse_error": ("Parse Error" not in text
                           and "SCRIPT ERROR" not in text),
        "both_loaded": all("error" not in v for v in payload.values()
                           if isinstance(v, dict)),
        "both_have_standard_material": all(len(v) > 0
                                           for v in standard.values()),
        "both_have_albedo_texture": all(
            bool(s.get("albedo_texture")) for v in standard.values()
            for s in v),
        "albedo_colors_are_white": all(
            all(abs(c - 1.0) < 0.01
                for c in s["albedo_color"][:3])
            for v in standard.values() for s in v),
        "textures_differ_between_roles": (
            standard.get("player") and standard.get("foe")
            and standard["player"][0]["albedo_texture"]
            != standard["foe"][0]["albedo_texture"]),
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "payload": payload, "standard_surfaces": standard,
        "checks": checks, "failed": [k for k, v in checks.items()
                                     if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RC", p.returncode, "marker", line is not None)
    for k, v in surfaces.items():
        print(k, "surfaces", len(v),
              [(s.get("material_class"), s.get("albedo_texture", "")[-40:])
               for s in v[:2]])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("MATERIAL_I_OK" if ok else "MATERIAL_I_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
