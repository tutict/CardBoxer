"""I 路线：同进程证明 CARD_BOXER_FOE_VISUAL=none 是有效的可逆开关。

判据故意做成「开关有牙」三段：
  off1 == off2          同状态稳定
  off1 == restored      可逐像素还原
  off1 != forced        手动开时对手侧确实变（不是实现坏了所以都没效果）
  player ROI 全程 0 变化

用法：python run_off_switch_probe.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
H = HERE.parent / "H路线-双方3D侧面战斗"
OUTDIR = HERE / "shots" / "off_switch"
SRC = HERE / "tests" / "off_switch_probe.gd"
DST = GAME / "tests" / "off_switch_probe.gd"
OUT = HERE / "data" / "off_switch_i.json"
LOG = HERE / "logs" / "godot_off_switch.log"
THR = 18


def load(tag: str) -> Image.Image:
    return Image.open(OUTDIR / f"off-{tag}.png").convert("RGB")


def diff(a: Image.Image, b: Image.Image, box) -> dict:
    ia, ib = a.crop(box), b.crop(box)
    d = ImageChops.difference(ia, ib)
    changed = sum(1 for px in d.get_flattened_data() if sum(px) > THR)
    total = ia.width * ia.height
    return {"changed_px": changed, "total_px": total,
            "ratio": round(changed / total, 4)}


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env["CARD_BOXER_FOE_VISUAL"] = "none"
    env["I_OFF_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "900", "--script",
             "res://tests/off_switch_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = proc.returncode
        text = (proc.stdout + b"\n--- STDERR ---\n"
                + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    dt = round(time.perf_counter() - t0, 3)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(text, encoding="utf-8")
    marker = "IOFF_JSON "
    line = next((l for l in text.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    rows = payload.get("shots", [])
    states = {s.get("tag"): s for s in payload.get("states", [])}
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")

    boxes = json.loads((H / "data" / "roi_h.json").read_text(
        encoding="utf-8"))["boxes"]
    left, right = boxes[0], boxes[1]
    diffs = {}
    if all((OUTDIR / f"off-{t}.png").is_file()
           for t in ("off1", "off2", "forced", "restored")):
        imgs = {t: load(t) for t in
                ("off1", "off2", "forced", "restored")}
        full = (0, 0, 1280, 720)
        diffs = {
            "off1_vs_off2_full": diff(imgs["off1"], imgs["off2"], full),
            "off1_vs_restored_full": diff(
                imgs["off1"], imgs["restored"], full),
            "off1_vs_forced_foe_roi": diff(
                imgs["off1"], imgs["forced"], right),
            "off1_vs_forced_player_roi": diff(
                imgs["off1"], imgs["forced"], left),
        }
    d = diffs
    checks = {
        "rc": rc == 0,
        "has_opengl": "OpenGL API" in text,
        "no_script_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "five_shots": len(rows) == 5,
        "all_png_ok": all(r.get("save_error") == 0
                          and r.get("w") == 1280 and r.get("h") == 720
                          and Path(r.get("path", "")).is_file()
                          for r in rows),
        "both_layers_ready": (payload.get("player_layer_ready") is True
                              and payload.get("foe_layer_ready") is True),
        "env_is_none": payload.get("env_visual_none") == "none",
        "configure_did_not_enable": (
            payload.get("foe_initial_visual") is False),
        "off1_state_disabled": (states.get("off1", {}).get("foe_visual")
                                is False),
        "forced_state_enabled": (states.get("forced", {}).get("foe_visual")
                                 is True),
        "restored_state_disabled": (
            states.get("restored", {}).get("foe_visual") is False),
        "player_layer_never_visual": (
            payload.get("player_visual_state", {}).get("foe_visual") is False),
        "off_state_stable": d.get("off1_vs_off2_full", {}).get(
            "changed_px") == 0,
        "off_state_restorable": d.get("off1_vs_restored_full", {}).get(
            "changed_px") == 0,
        "switch_has_teeth": d.get("off1_vs_forced_foe_roi", {}).get(
            "ratio", 0.0) > 0.30,
        "player_roi_never_changes": d.get(
            "off1_vs_forced_player_roi", {}).get("changed_px") == 0,
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "run": {"seconds": dt, "returncode": rc,
                "script_errors": errors, "headless": False},
        "payload": payload, "diffs": diffs, "checks": checks,
        "failed": [k for k, v in checks.items() if not v], "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RUN {dt}s rc={rc} errors={errors}")
    print("ENV", payload.get("env_visual_none"),
          "FOE_INITIAL", payload.get("foe_initial_visual"))
    for s in payload.get("states", []):
        print("STATE", s)
    for k, v in diffs.items():
        print("DIFF", k, v)
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("OFF_SWITCH_I_OK" if ok else "OFF_SWITCH_I_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
