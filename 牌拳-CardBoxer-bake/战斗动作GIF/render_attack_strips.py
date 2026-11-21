"""用游戏自己的逐帧胶片通道渲一张牌的当前外观层，输出 PNG 序列。

复用 tests/motion_strip.gd（游戏内 SceneTree 脚本），不另写渲染器：
帧数 = card_data 的 windup+active+recover，画面 = 当前 fighter.gd 的
SKIN_V2 外观层 + CardMotion 关节表，和玩家在引擎里看到的完全一致。

必须带窗口运行（headless 没有渲染目标，frame_post_draw 永不触发）。
用法： python -u render_attack_strips.py jab [cross wave ...]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
CARDS = json.loads((GAME / "data/card_motion.json").read_text(encoding="utf-8"))["cards"]

assert GODOT.is_file(), f"missing Godot: {GODOT}"
assert GAME.is_dir(), f"missing game: {GAME}"

ids = sys.argv[1:] or ["jab"]
results = {}
for card_id in ids:
    assert card_id in CARDS, f"unknown card {card_id}"
    out = HERE / "frames" / card_id
    if out.exists():
        for p in out.glob("strip_*.png"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for key in ("CARD_BOXER_CAPTURE", "CARD_BOXER_CAPTURE_AT",
                "CARD_BOXER_CAPTURE_HIT", "CARD_BOXER_TK_SHOT",
                "CARD_BOXER_TAIKOU_BOT"):
        env.pop(key, None)
    env["CARD_BOXER_STRIP"] = card_id
    env["CARD_BOXER_STRIP_DIR"] = str(out)

    cmd = [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
           "--quit-after", "6000", "--script", "res://tests/motion_strip.gd"]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, timeout=240)
        rc, log = proc.returncode, proc.stdout + b"\n--- STDERR ---\n" + proc.stderr
    except subprocess.TimeoutExpired as exc:
        rc, log = -1, (exc.stdout or b"") + b"\n--- TIMEOUT ---\n" + (exc.stderr or b"")

    (HERE / "logs" / f"strip_{card_id}.log").parent.mkdir(parents=True, exist_ok=True)
    (HERE / "logs" / f"strip_{card_id}.log").write_bytes(log)
    text = log.decode("utf-8", "replace")
    shots = sorted(out.glob("strip_*.png"),
                   key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))
    expect = len(CARDS[card_id]["track"])
    has_gl = "OpenGL API" in text
    errors = text.count("SCRIPT ERROR")
    # motion_strip.gd 注释写「多存一帧」，但那段用同一个 n=total 文件名
    # 覆盖了第 total 帧，所以文件数 == track 帧数，不是 +1。实测 jab=14。
    # 副作用是末帧为收招后的静止姿态，正好适合 GIF 收尾。
    ok = rc == 0 and has_gl and errors == 0 and len(shots) == expect
    print(f"{card_id}: rc={rc} frames={len(shots)} expect={expect} "
          f"gl={has_gl} script_errors={errors} -> {'OK' if ok else 'FAIL'}", flush=True)
    results[card_id] = {"ok": ok, "frames": len(shots), "expected": expect,
                        "out": str(out), "bytes": sum(p.stat().st_size for p in shots)}

(HERE / "strip_result.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("STRIP_ALL_OK" if all(r["ok"] for r in results.values()) else "STRIP_FAILED")
sys.exit(0 if all(r["ok"] for r in results.values()) else 1)
