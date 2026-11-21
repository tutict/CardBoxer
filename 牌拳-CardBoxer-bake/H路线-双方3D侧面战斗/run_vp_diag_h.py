"""H 路线：同进程隐藏层对照，判定两个 SubViewport 是否串味。

判据（全部同进程，无 RNG 噪声）：
  隐藏 player 时：左侧 ROI 应显著变化、右侧 ROI 应几乎不变；
  隐藏 foe 时：右侧 ROI 应显著变化、左侧 ROI 应几乎不变。
用法：python run_vp_diag_h.py
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
OUTDIR = HERE / "shots" / "vp_diag"
LOGS = HERE / "logs"
OUT = HERE / "data" / "vp_diag_h.json"
ROI = HERE / "data" / "roi_h.json"
PROBE_SRC = HERE / "tests" / "vp_diag_probe.gd"
PROBE_DST = GAME / "tests" / "vp_diag_probe.gd"


def diff(a: Path, b: Path, box) -> dict:
    ia = Image.open(a).convert("RGB").crop(box)
    ib = Image.open(b).convert("RGB").crop(box)
    d = ImageChops.difference(ia, ib)
    changed = sum(1 for px in d.get_flattened_data() if sum(px) > 18)
    total = ia.width * ia.height
    return {"changed_px": changed, "total_px": total,
            "ratio": round(changed / total, 4)}


def main() -> int:
    assert GODOT.is_file() and PROBE_SRC.is_file() and ROI.is_file()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROBE_SRC, PROBE_DST)
    boxes = json.loads(ROI.read_text(encoding="utf-8"))["boxes"]
    left, right = boxes[0], boxes[1]

    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env["H_VP_DIR"] = str(OUTDIR)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "900", "--script", "res://tests/vp_diag_probe.gd"],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    text = (proc.stdout + b"\n--- STDERR ---\n"
            + proc.stderr).decode("utf-8", "replace")
    (LOGS / "godot_vp_diag.log").write_text(text, encoding="utf-8")
    marker = "HVP_JSON "
    line = next((l for l in text.splitlines() if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    rows = payload.get("shots", [])
    by = {r["name"]: Path(r["path"]) for r in rows}
    has_gl = "OpenGL API" in text
    errors = text.count("SCRIPT ERROR") + text.count("Parse Error")

    res = {}
    for hidden, untouched_side, changed_side in (
            ("player-hidden", right, left),
            ("foe-hidden", left, right)):
        res[f"{hidden}_untouched"] = diff(by["both"], by[hidden],
                                          untouched_side)
        res[f"{hidden}_changed"] = diff(by["both"], by[hidden], changed_side)

    checks = {
        "rc": proc.returncode == 0,
        "has_opengl": has_gl,
        "no_errors": errors == 0,
        "no_payload_error": "error" not in payload,
        "five_frames": len(rows) == 5,
        "all_png_ok": all(r.get("save_error") == 0
                          and r.get("w") == 1280 and r.get("h") == 720
                          and Path(r.get("path", "")).is_file() for r in rows),
        "both_layers_ready": (payload.get("player_layer_ready") is True
                              and payload.get("foe_layer_ready") is True),
        # 隐藏 player：右侧（对手）不受影响，左侧显著变化
        "hide_player_right_untouched": (
            res["player-hidden_untouched"]["ratio"] < 0.02),
        "hide_player_left_changed": (
            res["player-hidden_changed"]["ratio"] > 0.10),
        # 隐藏 foe：左侧（玩家）不受影响，右侧显著变化
        "hide_foe_left_untouched": (
            res["foe-hidden_untouched"]["ratio"] < 0.02),
        "hide_foe_right_changed": (
            res["foe-hidden_changed"]["ratio"] > 0.10),
    }
    report = {"run": {"seconds": round(time.perf_counter() - t0, 3),
                      "returncode": proc.returncode, "has_opengl": has_gl,
                      "script_errors": errors},
              "payload": payload, "roi": {"left": left, "right": right},
              "diffs": res, "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"RUN {report['run']['seconds']}s rc={proc.returncode} "
          f"gl={has_gl} errors={errors}")
    for k, v in res.items():
        print(f"DIFF {k:<28} {v['changed_px']:>6}/{v['total_px']} "
              f"ratio={v['ratio']}")
    for k, v in checks.items():
        if not v:
            print("  FAIL", k)
    print("VP_DIAG_OK" if report["ok"] else "VP_DIAG_SUSPICIOUS")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
