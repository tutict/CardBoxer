"""在大窗口（project.godot 的 1600x900，不传 --resolution）下截一张完整游戏帧。

复用上轮注入式截帧器，只跑 t048 一帧，用来肉眼/像素核对
「canvas_items 等比放大后 HUD、角色、手牌、背景没有错位或裁切」。
arena.gd 由上轮脚本逐字节还原。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "side-view-rhythm"))

import capture_rhythm as cr  # noqa: E402

cr.OUT = HERE / "large-window-captures"
cr.TMP = Path(tempfile.mkdtemp(prefix="cardboxer-large-shots-"))
cr.LOGDIR = HERE / "logs"
cr.OUT.mkdir(parents=True, exist_ok=True)
cr.LOGDIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "t048"]
    raise SystemExit(cr.main())
