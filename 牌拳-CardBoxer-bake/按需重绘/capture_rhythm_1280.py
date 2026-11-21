"""跑同一套注入式节奏截帧，但强制 1280x720 物理窗口。

capture_rhythm.py 不带 --resolution，而 project.godot 现在有
window_width_override=1600 / height_override=900，于是它出的 PNG 是
1600x900；引擎优化/回归帧/ 的基线是 1280x720。这里只给命令补一个
--resolution，注入逻辑仍完全复用（不复制、不过期）。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "侧身节奏接线"))

import capture_rhythm as cr  # noqa: E402

_orig_run = cr.subprocess.run


def _run_1280(cmd, *args, **kwargs):
    cmd = list(cmd)
    if "--resolution" not in cmd and "--path" in cmd:
        i = cmd.index("--path") + 2
        cmd[i:i] = ["--resolution", "1280x720"]
    return _orig_run(cmd, *args, **kwargs)


cr.subprocess.run = _run_1280
cr.OUT = HERE / "节奏回归帧1280"
cr.TMP = Path(tempfile.mkdtemp(prefix="cardboxer-redraw-1280-"))
cr.LOGDIR = HERE / "logs"
cr.OUT.mkdir(parents=True, exist_ok=True)
cr.LOGDIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    raise SystemExit(cr.main())
