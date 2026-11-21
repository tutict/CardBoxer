"""J 路线 r1 负结果后：把工程 foe-rigged.glb 逐字节还原并重新导入。

回滚不是「删掉失败产物」——失败的 GLB / 截帧 / 报告全部留在 J 目录，
只把可运行工程恢复到 I 路线验收时的状态，并用 sha256 证明。

用法：python rollback_shape_j.py
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
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
DST = GAME / "assets" / "3d" / "foe-rigged.glb"
IMPORT = DST.with_suffix(".glb.import")
ORIG = HERE / "orig" / "pre-shape"
OUT = HERE / "data" / "rollback_j.json"
LOG = HERE / "logs" / "godot_reimport_rollback_j.log"
INSTALL = HERE / "data" / "install_j.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    before_expected = json.loads(INSTALL.read_text(
        encoding="utf-8"))["before"]
    assert (ORIG / "foe-rigged.glb").is_file()
    shutil.copyfile(ORIG / "foe-rigged.glb", DST)
    now = {"glb_bytes": DST.stat().st_size,
           "glb_sha256": sha256(DST),
           "import_sha256": sha256(IMPORT)}
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env.pop("CARD_BOXER_FOE_VISUAL", None)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(GODOT), "--headless", "--path", str(GAME), "--import"],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    text = (proc.stdout + b"\n--- STDERR ---\n"
            + proc.stderr).decode("utf-8", "replace")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(text, encoding="utf-8")
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    checks = {
        "glb_sha_matches_i_baseline": (
            now["glb_sha256"] == before_expected["glb_sha256"]),
        "glb_size_matches": (
            now["glb_bytes"] == before_expected["glb_bytes"]),
        "import_file_untouched": (
            now["import_sha256"] == before_expected["import_sha256"]),
        "backup_still_intact": (
            sha256(ORIG / "foe-rigged.glb")
            == before_expected["glb_sha256"]),
        "reimport_rc0": proc.returncode == 0,
        "no_script_errors": errors == 0,
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "restored": str(DST), "from": str(ORIG / "foe-rigged.glb"),
        "expected": before_expected, "actual": now,
        "reimport": {"seconds": round(time.perf_counter() - t0, 3),
                     "returncode": proc.returncode,
                     "script_errors": errors},
        "checks": checks, "failed": [k for k, v in checks.items()
                                     if not v], "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESTORED", now["glb_bytes"], now["glb_sha256"][:16])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("ROLLBACK_J_OK" if ok else "ROLLBACK_J_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
