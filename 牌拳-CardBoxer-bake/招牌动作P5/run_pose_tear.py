# -*- coding: utf-8 -*-
"""#215 · baseline + 推荐档，在真实游戏 GLB 上跑全量 284 帧撕裂成本。

直接复用 P2 的 headless Blender 扫描器（只消费 delta_deg / root_m），
不新写驱动公式。用法：python run_pose_tear.py
产出：data/pose_tear_blender.json、logs/pose_tear.out
"""
from __future__ import annotations

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
D = HERE / "data"
LOGS = HERE / "logs"
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
SWEEP = BAKE / "动作表现P2" / "tests" / "sweep_tear_blender.py"
PLAN = D / "pose_plan.json"
OUT = D / "pose_tear_blender.json"


def main() -> int:
    for p in (BLENDER, SWEEP, PLAN):
        if not p.is_file():
            print("MISSING", p)
            return 1
    cmd = [str(BLENDER), "-b", "--factory-startup",
           "--python", str(SWEEP), "--", str(PLAN), str(OUT)]
    print("CMD", " ".join(cmd), flush=True)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=900)
    except subprocess.TimeoutExpired:
        print("BLENDER_TIMEOUT")
        return 1
    text = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
    (LOGS / "pose_tear.out").write_text(text, encoding="utf-8")
    print(text[-2500:])
    ok = (p.returncode == 0 and OUT.is_file()
          and "TEAR_SWEEP_BLENDER_OK" in text)
    print("POSE_TEAR_RUN_OK" if ok else "POSE_TEAR_RUN_FAILED",
          "rc=", p.returncode)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
