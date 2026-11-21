"""跑 World3D 共享 A/B 探针，并做两状态像素对照。

用法：python run_world3d_probe.py
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
SRC = HERE / "tests" / "world3d_probe.gd"
DST = GAME / "tests" / "world3d_probe.gd"
OUTDIR = HERE / "shots" / "world3d"
OUT = HERE / "data" / "world3d_probe.json"
LOG = HERE / "logs" / "godot_world3d.log"
MARKER = "W3D_JSON "


def stats(p: Path) -> dict:
    if not p.is_file():
        return {}
    im = Image.open(p).convert("RGBA")
    opaque = white = cyan = 0
    for r, g, b, a in im.getdata():
        if a < 32:
            continue
        opaque += 1
        if r > 175 and g > 175 and b > 175:
            white += 1
        if b > 110 and g > 110 and r < g - 18:
            cyan += 1
    return {"opaque_px": opaque, "near_white_px": white,
            "cyan_px": cyan,
            "white_ratio": round(white / max(1, opaque), 6)}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    env = os.environ.copy()
    for k in ("CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
              "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL"):
        env.pop(k, None)
    env["CARD_BOXER_3D"] = "1"
    env["W3D_OUT"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "1200", "--script",
             "res://tests/world3d_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = proc.returncode
        text = (proc.stdout + b"\n--- STDERR ---\n"
                + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    LOG.write_text(text, encoding="utf-8")
    line = next((l for l in text.splitlines()
                 if l.startswith(MARKER)), None)
    payload = json.loads(line[len(MARKER):]) if line else {"error": "no marker"}
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")
    states = payload.get("states", [])
    by_tag = {s["tag"]: s for s in states}
    layers = {tag: {r["label"]: r for r in s.get("layers", [])}
              for tag, s in by_tag.items()}
    for tag, lm in layers.items():
        for label, rec in lm.items():
            p = Path(rec.get("sv_png", ""))
            rec["pixels"] = stats(p)
            rec["png_sha256"] = sha(p)

    before = layers.get("before", {})
    after = layers.get("after", {})
    bids = {r["world3d_id"] for r in before.values()}
    aids = {r["world3d_id"] for r in after.values()}
    checks = {
        "rc": rc == 0,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "two_states": set(by_tag) == {"before", "after"},
        "four_sv_written": sum(
            1 for lm in layers.values() for r in lm.values()
            if Path(r.get("sv_png", "")).is_file()
            and r.get("sv_error") == 0) == 4,
        "four_sv_nonblank": all(
            r.get("pixels", {}).get("opaque_px", 0) > 10000
            for lm in layers.values() for r in lm.values()),
        # 订正：Godot 4.5 里未设 own_world_3d 时 sv.world_3d 就是 null
        # （instance_id 记 0），两层都继承父 viewport 的同一个 World3D；
        # after 两层各自拿到非 0 且不同的 id。
        "before_world3d_is_null": bids == {0},
        "after_world3d_distinct": len(aids) == 2 and 0 not in aids,
        "before_shared_world": len(bids) == 1,
        "own_world_3d_before_false": all(
            r.get("own_world_3d") is False for r in before.values()),
        "own_world_3d_after_true": all(
            r.get("own_world_3d") is True for r in after.values()),
        "world_ids_changed": bids != aids,
        # 决定性像素：before 两个视口都很白（两个角色都画进去了）；
        # after foe 视口近白塌到 1% 级，player 视口仍保持白衫。
        "before_both_viewports_white": all(
            r.get("pixels", {}).get("white_ratio", 0) > 0.10
            for r in before.values()),
        "after_foe_white_drops": (
            after.get("foe", {}).get("pixels", {}).get("white_ratio", 1)
            < 0.03),
        "after_player_white_stays": (
            after.get("player", {}).get("pixels", {}).get("white_ratio", 0)
            > 0.20),
        # 独立 world 后应与「只挂一层」的单层探针逐项吻合（±10%）
        "after_foe_matches_single_layer": (
            63000 < after.get("foe", {}).get("pixels", {}).get(
                "opaque_px", 0) < 78000
            and after.get("foe", {}).get("pixels", {}).get(
                "near_white_px", 0) < 1500),
        "after_player_matches_single_layer": (
            38000 < after.get("player", {}).get("pixels", {}).get(
                "opaque_px", 0) < 50000
            and after.get("player", {}).get("pixels", {}).get(
                "near_white_px", 0) > 11000),
    }
    ok = all(checks.values())
    report = {
        "run": {"seconds": round(time.perf_counter() - t0, 3),
                "returncode": rc, "script_errors": errors},
        "payload": payload, "checks": checks,
        "failed": [k for k, v in checks.items() if not v], "ok": ok,
        "conclusion": (
            "若 before 两层 world_3d 的 instance_id 相同、own_world_3d=false，"
            "则两个 SubViewport 共用同一个 3D 世界，各自相机都会看到两个角色"
            " ⇒ 用户看到的『两个人物重叠』是接线层问题，不是 GLB 资产叠层。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                   + "\n", encoding="utf-8")
    print(f"RUN {report['run']['seconds']}s rc={rc} errors={errors}")
    for tag in ("before", "after"):
        for label in ("player", "foe"):
            r = layers.get(tag, {}).get(label, {})
            print(tag, label, "world", r.get("world3d_id"),
                  "own", r.get("own_world_3d"),
                  "pixels", r.get("pixels"),
                  "sha", str(r.get("png_sha256", ""))[:12])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("WORLD3D_PROBE_OK" if ok else "WORLD3D_PROBE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
