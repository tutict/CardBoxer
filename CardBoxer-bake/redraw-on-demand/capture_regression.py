"""节奏层/截帧链兼容性回归：复用side-view-rhythm/capture_rhythm.py 的注入式 GL 截帧。

不复制注入逻辑（会过期），只改它的输出常量。arena.gd 由原脚本逐字节还原
并打印 sha256；本轮只验证「门控开启时 8 张注入态节奏帧仍能正常出图」。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "side-view-rhythm"))

import capture_rhythm as cr  # noqa: E402

cr.OUT = HERE / "rhythm-regression-frames"
cr.TMP = Path(tempfile.mkdtemp(prefix="cardboxer-redraw-shots-"))
cr.LOGDIR = HERE / "logs"
cr.OUT.mkdir(parents=True, exist_ok=True)
cr.LOGDIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    raise SystemExit(cr.main())
