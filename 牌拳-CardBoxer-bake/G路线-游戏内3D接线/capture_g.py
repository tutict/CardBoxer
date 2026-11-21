"""G 路线 A/B 截帧：复用侧身节奏接线已验证的「注入式确定性截帧」。

三组：
  baseline = orig/pre-3d 副本工程（改动前，无 3D）
  off      = 当前工程，CARD_BOXER_3D 未设（双轨默认关）
  on       = 当前工程，CARD_BOXER_3D=1（玩家侧 3D）
每组同一套注入（构造牌型 -> _resolve_taikou -> 手动推进节奏 -> hitstop 冻结），
arena.gd 逐字节还原 + sha256 证明，保证 A/B 可复算。

用法：python capture_g.py baseline|off|on [mode ...]
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
BASE_PROJECT = HERE / "baseline_project"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
OUT = HERE / "data"

DEFAULT_MODES = ["t000", "t048", "t112", "t140", "draw", "foewin"]


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("baseline", "off", "on"):
        print("USAGE: python capture_g.py baseline|off|on [mode ...]")
        return 2
    group = sys.argv[1]
    modes = sys.argv[2:] or DEFAULT_MODES

    sys.path.insert(0, str(BAKE / "侧身节奏接线"))
    import capture_rhythm as cr  # noqa: E402

    project = BASE_PROJECT if group == "baseline" else GAME
    assert project.is_dir(), project
    shots = HERE / "shots" / group
    shots.mkdir(parents=True, exist_ok=True)
    logdir = HERE / "logs" / ("capture_" + group)
    logdir.mkdir(parents=True, exist_ok=True)

    cr.GAME = project
    cr.ARENA = project / "scripts" / "arena.gd"
    cr.GODOT = GODOT
    cr.OUT = shots
    cr.TMP = Path(tempfile.mkdtemp(prefix="fa-g-%s-" % group))
    cr.LOGDIR = logdir
    full_cases = dict(cr.CASES)
    cr.CASES = {k: full_cases[k] for k in modes}

    if group == "on":
        os.environ["CARD_BOXER_3D"] = "1"
    else:
        os.environ.pop("CARD_BOXER_3D", None)

    sys.argv = [sys.argv[0]] + modes
    rc = cr.main()

    result = {}
    p = shots / "capture_result.json"
    if p.is_file():
        result = json.loads(p.read_text(encoding="utf-8"))
    payload = {
        "group": group, "project": str(project), "modes": modes,
        "env_3d": os.environ.get("CARD_BOXER_3D", ""),
        "returncode": rc, "restore_ok": result.get("restore_ok"),
        "records": result.get("records", []),
        "pngs": sorted(x.name for x in shots.glob("*.png")),
    }
    (OUT / ("capture_%s.json" % group)).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"GROUP {group} rc={rc} restore={payload['restore_ok']} "
          f"pngs={len(payload['pngs'])}")
    # 临时目录只留证据，不进交付清单
    shutil.rmtree(cr.TMP, ignore_errors=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
