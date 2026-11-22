"""World3D 接线修复 · 落地态验收（三个独立进程）。

  shipped  开 3D，探针零运行时改动 → 真实游戏落生态
  legacy   开 3D，首帧强制 own_world_3d=false → 复现旧 bug 作 A/B
  default  不开 3D（display_stopgap_probe.gd）→ 默认关零污染读回

注意：整帧含随机发牌，sha 不可跨进程比较；SubViewport 原图是稳定 stance
帧，可逐字节对账 P0「一次只挂一层」的单层真值。默认关零污染因此按
「引擎读回 + 静态源码守卫」判定，不靠整帧像素等价。

用法：python run_shipped_check.py
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
SRC = HERE / "tests" / "shipped_probe.gd"
DST = GAME / "tests" / "shipped_probe.gd"
SHOTS = HERE / "shots"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "shipped_check.json"
SINGLE_TRUTH = (HERE.parent / "route-b-asset-deduplication" / "data"
                / "single_layers.json")
ARENA = GAME / "scripts" / "arena.gd"
SCENARIO = 'Parameter "scenario" is null'
CLEAR = ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
         "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
         "W3D_MIN_OUT", "W3D_MIN_MODE", "W3D_OUT", "DISPLAY_DIR",
         "SHIPPED_OUT", "SHIPPED_MODE")


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


def roi_luma(p: Path, box=(730, 275, 985, 535)) -> float:
    """整帧里 foe 角色 ROI 的平均亮度（不含卡牌 HUD）。"""
    if not p.is_file():
        return 0.0
    im = Image.open(p).convert("RGB").crop(box)
    vals = [(r * 299 + g * 587 + b * 114) // 1000
            for r, g, b in im.getdata()]
    return round(sum(vals) / max(1, len(vals)), 3)


def run_godot(tag: str, script: str, extra: dict, marker: str,
              warm_frames: int) -> dict:
    d = SHOTS / tag
    d.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for k in CLEAR:
        env.pop(k, None)
    env.update(extra)
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", str(warm_frames + 600), "--script", script],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = p.returncode
        text = (p.stdout + b"\n--- STDERR ---\n"
                + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    (LOGDIR / f"godot_{tag}.log").write_text(text, encoding="utf-8")
    line = next((l for l in text.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    return {"tag": tag, "seconds": round(time.perf_counter() - t0, 3),
            "rc": rc,
            "script_errors": text.count("SCRIPT ERROR")
            + text.count("Parse Error"),
            "scenario_errors": text.count(SCENARIO),
            "payload": payload,
            "pngs": sorted(str(x) for x in d.glob("*.png"))}


def main() -> int:
    assert GODOT.is_file() and SRC.is_file()
    LOGDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    truth = {r["role"]: r for r in
             json.loads(SINGLE_TRUTH.read_text(encoding="utf-8"))["runs"]}

    shipped = run_godot(
        "shipped", "res://tests/shipped_probe.gd",
        {"CARD_BOXER_3D": "1", "SHIPPED_MODE": "shipped",
         "SHIPPED_OUT": str(SHOTS / "shipped")}, "SHIPPED_JSON ", 60)
    legacy = run_godot(
        "legacy", "res://tests/shipped_probe.gd",
        {"CARD_BOXER_3D": "1", "SHIPPED_MODE": "legacy",
         "SHIPPED_OUT": str(SHOTS / "legacy")}, "SHIPPED_JSON ", 60)
    # 只关 I 路线 foe canvas shader，用环境变量，不改源码：把「对手偏暗」
    # 归因到 tint 还是独立 world 后灯数变少。
    no_tint = run_godot(
        "no_tint", "res://tests/shipped_probe.gd",
        {"CARD_BOXER_3D": "1", "SHIPPED_MODE": "shipped",
         "SHIPPED_OUT": str(SHOTS / "no_tint"),
         "CARD_BOXER_FOE_VISUAL": "none"}, "SHIPPED_JSON ", 60)
    default = run_godot(
        "default", "res://tests/display_stopgap_probe.gd",
        {"DISPLAY_DIR": str(SHOTS / "default")}, "DISPLAY_JSON ", 120)

    def layers(res):
        return {r["label"]: r for r in
                res["payload"].get("state", {}).get("layers", [])}

    sl, ll, nl = layers(shipped), layers(legacy), layers(no_tint)
    for lm in (sl, ll, nl):
        for rec in lm.values():
            p = Path(rec.get("sv_png", ""))
            rec["pixels"] = stats(p)
            rec["png_sha256"] = sha(p)
    dpay = default["payload"]
    ship_live = Path(shipped["payload"].get("live_png", ""))
    leg_live = Path(legacy["payload"].get("live_png", ""))
    nt_live = Path(no_tint["payload"].get("live_png", ""))
    foe_luma = {"shipped": roi_luma(ship_live),
                "legacy": roi_luma(leg_live),
                "no_tint": roi_luma(nt_live)}

    # 静态源码守卫：3D 层只在 use_3d 分支里被创建，默认关不会加载本文件。
    arena_src = ARENA.read_text(encoding="utf-8")
    guard_lines = [l for l in arena_src.splitlines()
                   if "Fighter3DLayer" in l or "layer_3d" in l]
    use3d_guard = "CARD_BOXER_3D" in arena_src

    four = (shipped, legacy, no_tint, default)
    checks = {
        "four_ran": all("error" not in r["payload"] for r in four),
        "all_rc_zero": all(r["rc"] == 0 for r in four),
        "no_script_errors": all(r["script_errors"] == 0 for r in four),
        # 落生态：探针零改动，两层 own=true，朝向修复仍在，I shader 仍在
        "shipped_use_3d": shipped["payload"].get("use_3d") is True,
        "shipped_two_layers": set(sl) == {"player", "foe"}
        and all(r["present"] for r in sl.values()),
        "shipped_own_true": all(
            r.get("own_world_3d") is True for r in sl.values()),
        "shipped_yaw_face_to_face": (sl["player"]["yaw"] == -55.0
                                     and sl["foe"]["yaw"] == 55.0),
        "shipped_flip_false": all(
            r.get("flip") is False for r in sl.values()),
        "shipped_foe_visual_on": (
            sl["foe"]["visual_state"].get("foe_visual") is True
            and sl["player"]["visual_state"].get("foe_visual") is False),
        "shipped_4_lights_each": all(
            r["visual_state"].get("light_rows") == 4 for r in sl.values()),
        # 决定性：落生态两层 SubViewport 原图与单层真值逐字节相同
        "shipped_sv_matches_single_layer": all(
            sl[l]["png_sha256"] == truth[l]["png_sha256"] != ""
            for l in ("player", "foe")),
        "shipped_sv_pixels_match_single_layer": all(
            all(sl[l]["pixels"][k] == truth[l]["pixels"][k]
                for k in ("opaque_px", "near_white_px",
                          "cyan_px", "white_ratio"))
            for l in ("player", "foe")),
        "shipped_two_sv_written": all(
            Path(r.get("sv_png", "")).is_file()
            and r.get("sv_error") == 0 for r in sl.values()),
        "shipped_no_scenario_error": shipped["scenario_errors"] == 0,
        "shipped_live_frame": Image.open(ship_live).size == (1280, 720)
        if ship_live.is_file() else False,
        # 强制关：旧 bug 复现，两层都串进白衫
        "legacy_own_false": all(
            r.get("own_world_3d") is False for r in ll.values()),
        "legacy_both_white": all(
            ll[l]["pixels"]["white_ratio"] > 0.10
            for l in ("player", "foe")),
        "legacy_sv_differs_from_single_layer": all(
            ll[l]["png_sha256"] != truth[l]["png_sha256"]
            for l in ("player", "foe")),
        "legacy_live_frame": Image.open(leg_live).size == (1280, 720)
        if leg_live.is_file() else False,
        # 关掉 I 路线 2D shader 的归因组：shader 只作用于 2D 合成，
        # 3D SubViewport 原图必须逐字节不变，整帧 foe ROI 必须变亮。
        "no_tint_foe_visual_off": (
            nl["foe"]["visual_state"].get("foe_visual") is False),
        "no_tint_both_sv_unchanged": all(
            nl[l]["png_sha256"] == sl[l]["png_sha256"] != ""
            for l in ("player", "foe")),
        "no_tint_foe_roi_brighter": (
            foe_luma["no_tint"] > foe_luma["shipped"]),
        "no_tint_live_frame": Image.open(nt_live).size == (1280, 720)
        if nt_live.is_file() else False,
        # 默认关：双轨开关仍是关，3D 层根本不创建
        "default_use_3d_false": dpay.get("use_3d") is False,
        "default_no_layers": (dpay.get("layer_3d") is False
                              and dpay.get("layer_3d_foe") is False),
        "default_no_overrides": (dpay.get("player_override") is False
                                 and dpay.get("enemy_override") is False),
        "default_no_yaw_read": (dpay.get("p_yaw") == 0.0
                                and dpay.get("f_yaw") == 0.0),
        "default_two_pngs": len(default["pngs"]) == 2,
        "default_arena_has_use3d_guard": use3d_guard,
        "default_layer_creation_is_guarded": len(guard_lines) > 0,
    }
    ok = all(checks.values())
    report = {
        "runs": {r["tag"]: {k: v for k, v in r.items()
                            if k != "payload"}
                 for r in four},
        "payloads": {r["tag"]: r["payload"] for r in four},
        "foe_roi_mean_luma": foe_luma,
        "shipped_layers": sl,
        "legacy_layers": ll,
        "no_tint_layers": nl,
        "single_layer_truth_sha256": {l: truth[l]["png_sha256"]
                                      for l in ("player", "foe")},
        "arena_guard_lines": guard_lines[:12],
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": ok,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in four:
        print(f"CASE {r['tag']:8s} rc={r['rc']} {r['seconds']}s "
              f"script_err={r['script_errors']} "
              f"scenario={r['scenario_errors']} pngs={len(r['pngs'])}")
    print("  foe ROI mean luma", foe_luma)
    for l in ("player", "foe"):
        print("  shipped", l, sl[l].get("own_world_3d"),
              sl[l].get("yaw"), sl[l]["pixels"],
              "sha", sl[l]["png_sha256"][:12])
    for k, v in checks.items():
        print("CHECK", k, v)
    print(f"PASSED {sum(checks.values())}/{len(checks)}")
    print("SHIPPED_CHECK_OK" if ok else "SHIPPED_CHECK_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
