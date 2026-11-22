"""World3D 接线修复 · 最小改动口径探针（四组独立 Godot 进程）。

  none  现状，两层都不设任何 world 属性
  own   只设 own_world_3d = true          ← 候选最小落地
  world 只设 world_3d = World3D.new()
  both  两者都设                          ← B 路线 P0 探针口径

逐组读回 world3d_id / own_world_3d / 两层 SubViewport 像素 / 整帧，
并统计 Godot 日志里的 `Parameter "scenario" is null.`（P0 遗留观测点）。

用独立进程而不是同进程切状态：运行时切 world 会留下 visibility mask
清理噪音，也会让「启动即设」的真实落地情形测不准。

用法：python run_world3d_min.py
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
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "world3d_min_probe.gd"
DST = GAME / "tests" / "world3d_min_probe.gd"
OUTDIR = HERE / "shots" / "world3d_min"
OUT = HERE / "data" / "world3d_min.json"
LOGDIR = HERE / "logs"
SOURCE = GAME / "scripts" / "fighter_3d_layer.gd"
# P0「一次只挂一层」的单层真值：落地态必须与之逐字节一致。
SINGLE_TRUTH = (HERE.parent / "route-b-asset-deduplication" / "data"
                / "single_layers.json")
MARKER = "W3D_MIN_JSON "
MODES = ("none", "own", "world", "both")
SCENARIO = 'Parameter "scenario" is null'


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


def run(mode: str) -> dict:
    d = OUTDIR / mode
    d.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for k in ("CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
              "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
              "W3D_OUT"):
        env.pop(k, None)
    env["CARD_BOXER_3D"] = "1"
    env["W3D_MIN_OUT"] = str(d)
    env["W3D_MIN_MODE"] = mode
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", "1200", "--script",
             "res://tests/world3d_min_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = proc.returncode
        text = (proc.stdout + b"\n--- STDERR ---\n"
                + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    (LOGDIR / f"godot_min_{mode}.log").write_text(text, encoding="utf-8")
    line = next((l for l in text.splitlines()
                 if l.startswith(MARKER)), None)
    payload = json.loads(line[len(MARKER):]) if line else {"error": "no marker"}
    layers = {r["label"]: r for r in payload.get("state", {}).get("layers", [])}
    for rec in layers.values():
        p = Path(rec.get("sv_png", ""))
        rec["pixels"] = stats(p)
        rec["png_sha256"] = sha(p)
    live = Path(payload.get("live_png", ""))
    return {
        "mode": mode,
        "seconds": round(time.perf_counter() - t0, 3),
        "returncode": rc,
        "script_errors": text.count("SCRIPT ERROR") + text.count("Parse Error"),
        "scenario_errors": text.count(SCENARIO),
        "engine_error_lines": text.count("ERROR:"),
        "payload": payload,
        "layers": layers,
        "live_png": str(live),
        "live_sha256": sha(live),
        "live_size": list(Image.open(live).size)
        if live.is_file() else [],
    }


def pix(res: dict, label: str, key: str, default=0):
    return res["layers"].get(label, {}).get("pixels", {}).get(key, default)


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    LOGDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    results = {m: run(m) for m in MODES}
    n, own, world, both = (results[m] for m in MODES)
    # 判据前提：源码落地前后，world/both 两组走的是不同渲染路径。
    # 落地前它们是「运行时切到自己创建的 world」，与 own 组等价；
    # 落地后源码已自带 own world，这两组变成「二次替换」，不能再要求
    # 与 own 逐字节等价。前提不适用的判据点名 N/A，不折进计数。
    landed = "sv.own_world_3d = true" in SOURCE.read_text(encoding="utf-8")
    truth = {r["role"]: r for r in
             json.loads(SINGLE_TRUTH.read_text(encoding="utf-8"))["runs"]}

    def ids(res):
        return {r.get("world3d_id", 0) for r in res["layers"].values()}

    checks = {
        "four_modes_ran": all(
            "error" not in results[m]["payload"] for m in MODES),
        "all_rc_zero": all(results[m]["returncode"] == 0 for m in MODES),
        "no_script_errors": all(
            results[m]["script_errors"] == 0 for m in MODES),
        "two_layers_each": all(
            set(results[m]["layers"]) == {"player", "foe"} for m in MODES),
        "four_groups_eight_sv": sum(
            1 for m in MODES for r in results[m]["layers"].values()
            if Path(r.get("sv_png", "")).is_file()
            and r.get("sv_error") == 0) == 8,
        "all_sv_nonblank": all(
            r.get("pixels", {}).get("opaque_px", 0) > 10000
            for m in MODES for r in results[m]["layers"].values()),
        # 现状：两层 world_3d 都是 null，都串进两个角色
        "none_world3d_null": ids(n) == {0},
        "none_own_false": all(
            r.get("own_world_3d") is False for r in n["layers"].values()),
        "none_both_viewports_white": all(
            pix(n, l, "white_ratio", 0) > 0.10 for l in ("player", "foe")),
        # 候选最小改动：只设 own_world_3d = true 就足够。
        # 判据口径订正（2026-11-14）：不能用 sv.world_3d 的 instance_id
        # 判是否独立。Godot 4.5 里 own_world_3d=true 时引擎内部用自己的
        # world，但 `world_3d` 这个「显式覆盖」属性 getter 仍返回 null(0)；
        # 只有显式 World3D.new() 赋值才让它非 0。判「生效」必须看可观察
        # 行为：own flag + 像素隔离 + 与 both 组 PNG 逐字节相同。
        "own_world3d_getter_null_is_expected": ids(own) == {0},
        "own_flag_true": all(
            r.get("own_world_3d") is True for r in own["layers"].values()),
        "own_apply_readback_true": all(
            r.get("own_after_apply") is True
            for r in own["payload"].get("apply_rows", [])),
        "own_foe_clean": (pix(own, "foe", "white_ratio", 1) < 0.03
                          and pix(own, "foe", "near_white_px", 99999) < 1500),
        "own_player_white": pix(own, "player", "white_ratio", 0) > 0.20,
        # none 组必须与落生态不同（证明强制关确实把两个角色串进同一视口）。
        "none_png_sha_differs": all(
            n["layers"][l]["png_sha256"] != own["layers"][l]["png_sha256"]
            for l in ("player", "foe")),
        # P0 遗留观测点：那条 `Parameter "scenario" is null.` 只在
        # 「运行时显式替换 world_3d」时出现；启动即设 own 是 0 条。
        "own_scenario_error_zero": own["scenario_errors"] == 0,
        "both_foe_clean": (pix(both, "foe", "white_ratio", 1) < 0.03
                           and pix(both, "foe", "near_white_px", 99999) < 1500),
        # 整帧都渲出来了（非空、尺寸一致）
        "four_live_frames": all(
            results[m]["live_size"] == [1280, 720] for m in MODES),
        # P0 遗留观测点：启动即设 own 不应比「运行时切」更差
        "own_scenario_not_worse_than_both": (
            own["scenario_errors"] <= both["scenario_errors"]),
    }

    # ── 前提相关判据（点名 N/A，不折进计数）──────────────────────
    premise_pre = {
        # 落地前：三种独立 world 写法必须逐字节等价，才能判定
        # 「只落一行 own_world_3d = true」是充分的最小改动。
        "pre_own_png_sha_equals_both": all(
            own["layers"][l]["png_sha256"]
            == both["layers"][l]["png_sha256"] != ""
            for l in ("player", "foe")),
        "pre_world_only_png_sha_equals_own": all(
            world["layers"][l]["png_sha256"]
            == own["layers"][l]["png_sha256"]
            for l in ("player", "foe")),
        "pre_own_equals_both_opaque": all(
            abs(pix(own, l, "opaque_px") - pix(both, l, "opaque_px"))
            / max(1, pix(both, l, "opaque_px", 1)) < 0.08
            for l in ("player", "foe")),
        "pre_own_equals_both_white": all(
            abs(pix(own, l, "near_white_px")
                - pix(both, l, "near_white_px")) < 200
            and abs(pix(own, l, "white_ratio")
                    - pix(both, l, "white_ratio")) < 0.01
            for l in ("player", "foe")),
    }
    premise_post = {
        # 落地后：源码自己设 own，own 组就是真实落生态；必须与 P0
        # 「一次只挂一层」的单层真值逐字节相同，才算彻底没有串扰。
        "post_shipped_matches_single_layer_bytewise": all(
            own["layers"][l]["png_sha256"] == truth[l]["png_sha256"] != ""
            for l in ("player", "foe")),
        "post_shipped_pixels_match_single_layer": all(
            all(own["layers"][l]["pixels"][k] == truth[l]["pixels"][k]
                for k in ("opaque_px", "near_white_px",
                          "cyan_px", "white_ratio"))
            for l in ("player", "foe")),
        "post_legacy_differs_from_single_layer": all(
            n["layers"][l]["png_sha256"] != truth[l]["png_sha256"]
            for l in ("player", "foe")),
    }
    applicable = premise_post if landed else premise_pre
    not_applicable = premise_pre if landed else premise_post
    checks.update(applicable)
    ok = all(checks.values())
    report = {
        "landed": landed,
        "premise": "post" if landed else "pre",
        "not_applicable": list(not_applicable),
        "modes": {m: {k: v for k, v in results[m].items()
                      if k != "payload"} for m in MODES},
        "payloads": {m: results[m]["payload"] for m in MODES},
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
        "conclusion": (
            "落地前：own / world / both 三种写法渲出的两层 SubViewport PNG "
            "逐字节相同，setup() 只需一行 sv.own_world_3d = true；显式 "
            "World3D.new() 是冗余，且运行时替换会触发 scenario is null。"
            "落地后：源码自带 own，own 组即真实落生态，与 P0「一次只挂一层」"
            "单层真值逐字节相同（重叠彻底消失）；world/both 变成二次替换，"
            "不再等价属预期，相关判据点名 N/A。注意 sv.world_3d getter 在 "
            "own 组仍为 null，这是 Godot 4.5 的显式覆盖属性语义。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for m in MODES:
        r = results[m]
        print(f"MODE {m:5s} rc={r['returncode']} {r['seconds']}s "
              f"script_err={r['script_errors']} "
              f"scenario_err={r['scenario_errors']} "
              f"engine_err_lines={r['engine_error_lines']}")
        for label in ("player", "foe"):
            rec = r["layers"].get(label, {})
            print("      ", label, "world", rec.get("world3d_id"),
                  "own", rec.get("own_world_3d"),
                  "pixels", rec.get("pixels"),
                  "sha", str(rec.get("png_sha256", ""))[:12])
    for k, v in checks.items():
        print("CHECK", k, v)
    reason = ("source already has own_world_3d" if landed
              else "source not yet landed")
    for k in report["not_applicable"]:
        print("N/A", k, "(" + reason + ")")
    print("PREMISE", report["premise"])
    print("WORLD3D_MIN_OK" if ok else "WORLD3D_MIN_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
