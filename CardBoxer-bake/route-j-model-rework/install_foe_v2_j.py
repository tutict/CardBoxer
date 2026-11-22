"""J 路线 P3：把新造型 GLB 装进可运行工程，先逐字节备份再替换。

产物：
  orig/pre-shape/        旧 foe-rigged.glb + .import 逐字节备份
  data/install_j.json    size + sha256 前后对账
  logs/godot_reimport_j.log

不删任何工程文件；回滚只需把 orig/pre-shape/ 两件复制回去。
用法：python install_foe_v2_j.py
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
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "foe-rigged-v2.glb"
DST = GAME / "assets" / "3d" / "foe-rigged.glb"
IMPORT = DST.with_suffix(".glb.import")
ORIG = HERE / "orig" / "pre-shape"
OUT = HERE / "data" / "install_j.json"
LOG = HERE / "logs" / "godot_reimport_j.log"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    assert SRC.is_file() and DST.is_file() and IMPORT.is_file()
    ORIG.mkdir(parents=True, exist_ok=True)
    before = {"glb_bytes": DST.stat().st_size,
              "glb_sha256": sha256(DST),
              "import_bytes": IMPORT.stat().st_size,
              "import_sha256": sha256(IMPORT)}
    for p in (DST, IMPORT):
        q = ORIG / p.name
        shutil.copy2(p, q)
        assert sha256(q) == sha256(p), f"backup mismatch: {p.name}"

    shutil.copyfile(SRC, DST)
    after = {"glb_bytes": DST.stat().st_size,
             "glb_sha256": sha256(DST),
             "import_bytes": IMPORT.stat().st_size,
             "import_sha256": sha256(IMPORT)}

    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env.pop("CARD_BOXER_FOE_VISUAL", None)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--headless", "--path", str(GAME), "--import"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = proc.returncode
        text = (proc.stdout + b"\n--- STDERR ---\n"
                + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(text, encoding="utf-8")
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")

    checks = {
        "backup_verified": all(
            (ORIG / p.name).is_file()
            and sha256(ORIG / p.name) == before[
                "glb_sha256" if p == DST else "import_sha256"]
            for p in (DST, IMPORT)),
        "glb_replaced": after["glb_sha256"] == sha256(SRC)
                        and after["glb_sha256"] != before["glb_sha256"],
        "import_file_untouched": (
            after["import_sha256"] == before["import_sha256"]),
        "reimport_rc0": rc == 0,
        "no_script_errors": errors == 0,
        "has_opengl_marker_or_clean": (
            "OpenGL API" in text or "Godot Engine" in text
            or len(text.strip()) > 20),
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": str(SRC), "source_sha256": sha256(SRC),
        "destination": str(DST), "backup_dir": str(ORIG),
        "before": before, "after": after,
        "reimport": {"seconds": round(time.perf_counter() - t0, 3),
                     "returncode": rc, "script_errors": errors},
        "checks": checks, "failed": [k for k, v in checks.items()
                                     if not v], "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BEFORE", before["glb_bytes"], before["glb_sha256"][:16])
    print("AFTER ", after["glb_bytes"], after["glb_sha256"][:16])
    print("REIMPORT", rc, f"{round(time.perf_counter() - t0, 3)}s",
          "errors", errors)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("INSTALL_J_OK" if ok else "INSTALL_J_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
