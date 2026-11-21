"""复用上轮 capture_rhythm.py 的注入式 GL 截帧，但输出全落在本目录。

不复制注入逻辑（会过期），直接 import 上轮脚本并改它的输出常量：
这样优化前后用的是同一套确定性注入，A/B 才可复算。
arena.gd 仍由上轮脚本逐字节还原并打印 sha256。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "侧身节奏接线"))

import capture_rhythm as cr  # noqa: E402

cr.OUT = HERE / "回归帧"
cr.TMP = Path(tempfile.mkdtemp(prefix="cardboxer-opt-shots-"))
cr.LOGDIR = HERE / "logs"
cr.OUT.mkdir(parents=True, exist_ok=True)
cr.LOGDIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    raise SystemExit(cr.main())
