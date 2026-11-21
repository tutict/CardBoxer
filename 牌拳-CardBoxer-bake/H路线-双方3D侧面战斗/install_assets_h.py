"""H 路线 P2：把 foe-rigged.glb 与 foe 版 motion 装进可运行游戏工程。

只读 H 工作区产物，二进制复制，逐项 sha256 核对；不改任何既有文件。
Godot editor 导入可 headless（渲染才需要窗口）。
用法：python install_assets_h.py
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
LOGS = HERE / "logs"
OUT = HERE / "data" / "install_assets_h.json"

SOURCES = [
    (HERE / "foe-rigged.glb", "assets/3d/foe-rigged.glb"),
    (HERE / "data" / "motion_input_foe.json",
     "data/motion_input_foe.json"),
]


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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    (GAME / "assets" / "3d").mkdir(parents=True, exist_ok=True)

    copies = []
    for src, rel in SOURCES:
        assert src.is_file(), src
        dst = GAME / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        a, b = sha256(src), sha256(dst)
        copies.append({"src": str(src), "dst": str(dst), "rel": rel,
                       "bytes": dst.stat().st_size, "sha256": a,
                       "identical": a == b})
    env = os.environ.copy()
    dt, rc, text = run(
        [str(GODOT), "--headless", "--editor", "--quit",
         "--path", str(GAME)],
        env, 300, LOGS / "godot_editor_import_game_h.log")
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")

    d3 = GAME / "assets" / "3d"
    generated = []
    for p in sorted(d3.rglob("*")):
        if p.is_file() and p.name.startswith("foe-rigged"):
            row = {"rel": str(p.relative_to(GAME)).replace("\\", "/"),
                   "bytes": p.stat().st_size, "sha256": sha256(p)}
            if p.suffix.lower() == ".png":
                with Image.open(p) as im:
                    row["size"] = [im.width, im.height]
            generated.append(row)
    pngs = [g for g in generated if g["rel"].endswith(".png")]

    checks = {
        "two_copies_identical": all(c["identical"] for c in copies),
        "import_rc": rc == 0,
        "import_no_parse_errors": errors == 0,
        "glb_import_stamp": (d3 / "foe-rigged.glb.import").is_file(),
        "three_pbr_extracted": len(pngs) == 3,
        "pbr_all_4096": all(g.get("size") == [4096, 4096] for g in pngs),
        "foe_motion_in_game": (GAME / "data" / "motion_input_foe.json").is_file(),
        "player_glb_untouched": (
            sha256(d3 / "player-rigged.glb")
            == sha256(HERE.parent / "F路线-Godot驱动层" / "player-rigged.glb")),
    }
    ok = all(checks.values())
    OUT.write_text(json.dumps({
        "import": {"seconds": dt, "returncode": rc, "errors": errors},
        "copies": copies, "generated": generated,
        "checks": checks, "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for c in copies:
        print(f"COPY {c['rel']:40s} {c['bytes']:>10} B "
              f"sha={c['sha256'][:12]} identical={c['identical']}")
    print(f"IMPORT rc={rc} {dt}s errors={errors} "
          f"generated={len(generated)} pngs={len(pngs)}")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("INSTALL_ASSETS_H_OK" if ok else "INSTALL_ASSETS_H_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
