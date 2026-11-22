"""P1 动作覆盖 · 引擎内 A/B 取证（两个独立 Godot 进程）。

  主探针   CARD_BOXER_3D=1，注入 6 个场景，读回两层 last_card/frame +
           截 SubViewport 原图与整帧；最后一场运行时裁回 3 卡做零回归 A/B。
  默认关   不带 CARD_BOXER_3D，用既有 display_stopgap_probe.gd 读回零污染。

判据不看上游 ok 字段，只信读回的 card/frame、PNG sha 与像素差异。

用法：python run_motion_p1_probe.py
产出：data/motion_p1_probe.json、shots/**、logs/godot_*.log
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
W3D = HERE.parent / "world3d-integration-fix"
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "motion_p1_probe.gd"
DST = GAME / "tests" / "motion_p1_probe.gd"
SHOTS = HERE / "shots"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "motion_p1_probe.json"

CLEAR = ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
         "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
         "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_RAGE_START",
         "MOTION_P1_OUT", "DISPLAY_DIR", "SHIPPED_OUT", "SHIPPED_MODE")
MARKER = "MOTION_P1_JSON "
DISPLAY_MARKER = "DISPLAY_JSON "
MIN_DIFF_PX = 500


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def diff_px(a: Path, b: Path) -> int:
    if not (a.is_file() and b.is_file()):
        return 0
    ia = Image.open(a).convert("RGBA")
    ib = Image.open(b).convert("RGBA")
    if ia.size != ib.size:
        return 0
    d = ImageChops.difference(ia, ib)
    r, g, bl, al = d.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g),
                            ImageChops.lighter(bl, al))
    mask = mx.point(lambda v: 255 if v > 8 else 0)
    return int(mask.histogram()[255])


def run_godot(tag: str, script: str, extra: dict, marker: str,
              frames: int) -> dict:
    env = os.environ.copy()
    for k in CLEAR:
        env.pop(k, None)
    env.update(extra)
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", str(frames), "--script", script],
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
            "scenario_errors": text.count('Parameter "scenario" is null'),
            "payload": payload}


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    assert GODOT.is_file() and SRC.is_file()
    shutil.copyfile(SRC, DST)

    main_dir = SHOTS / "p1"
    def_dir = SHOTS / "default"
    main_dir.mkdir(parents=True, exist_ok=True)
    def_dir.mkdir(parents=True, exist_ok=True)
    main_run = run_godot(
        "p1", "res://tests/motion_p1_probe.gd",
        {"CARD_BOXER_3D": "1", "MOTION_P1_OUT": str(main_dir)},
        MARKER, 3000)
    def_run = run_godot(
        "default", "res://tests/display_stopgap_probe.gd",
        {"DISPLAY_DIR": str(def_dir)}, DISPLAY_MARKER, 900)

    payload = main_run["payload"]
    rows = payload.get("rows", [])
    by_id = {r["id"]: r for r in rows}

    def sv(scene: str, side: str) -> Path:
        return Path(by_id.get(scene, {}).get(f"{side}_sv", ""))

    diffs = {}
    for scene in ("reveal", "player_win", "enemy_win", "draw"):
        for side in ("player", "foe"):
            diffs[f"{scene}_{side}"] = diff_px(
                sv(scene, side), sv("stance", side))

    shas = {}
    for r in rows:
        for side in ("player", "foe"):
            shas[f"{r['id']}_{side}"] = sha(Path(r.get(f"{side}_sv", "")))

    def quad(scene: str, pc: str, fc: str, pf_min: int,
             ff_min: int) -> bool:
        r = by_id.get(scene)
        if not r:
            return False
        return (r.get("player_card") == pc and r.get("foe_card") == fc
                and int(r.get("player_frame", -1)) >= pf_min
                and int(r.get("foe_frame", -1)) >= ff_min)

    checks = {
        "main_marker_parsed": "error" not in payload and len(rows) == 6,
        "main_no_script_errors": (main_run["rc"] == 0
                                  and main_run["script_errors"] == 0),
        "main_no_scenario_errors": main_run["scenario_errors"] == 0,
        "use_3d_and_both_overrides": (payload.get("use_3d") is True
                                      and payload.get("player_override") is True
                                      and payload.get("enemy_override") is True),
        "hp_unchanged": payload.get("hp") == [100, 100],
        "normal_scenes_have_15_cards": all(
            by_id.get(s, {}).get("cards_at_scene") == 15
            for s in ("stance", "reveal", "player_win",
                      "enemy_win", "draw")),
        "legacy_scene_has_3_cards": (
            by_id.get("legacy_player_win", {}).get("cards_at_scene") == 3),
        "stance_is_stance": quad("stance", "stance", "stance", 0, 0)
        and by_id.get("stance", {}).get("player_frame") == 0
        and by_id.get("stance", {}).get("foe_frame") == 0,
        "reveal_both_focus": quad("reveal", "focus", "focus", 1, 1),
        "player_win_bindings": quad("player_win", "wave", "hit_heavy", 1, 1),
        "enemy_win_bindings": quad("enemy_win", "hit_heavy", "cross", 1, 1),
        "draw_both_hit_light": quad("draw", "hit_light", "hit_light", 1, 1),
        "legacy_bindings": quad("legacy_player_win", "wave", "stance", 1, 0)
        and by_id.get("legacy_player_win", {}).get("foe_frame") == 0,
        "reveal_player_sv_changed": diffs.get("reveal_player", 0) > MIN_DIFF_PX,
        "reveal_foe_sv_changed": diffs.get("reveal_foe", 0) > MIN_DIFF_PX,
        "player_win_foe_sv_changed": diffs.get("player_win_foe", 0) > MIN_DIFF_PX,
        "enemy_win_player_sv_changed": diffs.get("enemy_win_player", 0) > MIN_DIFF_PX,
        "draw_player_sv_changed": diffs.get("draw_player", 0) > MIN_DIFF_PX,
        "draw_foe_sv_changed": diffs.get("draw_foe", 0) > MIN_DIFF_PX,
        "legacy_winner_sv_bytewise_identical": (
            shas.get("player_win_player") != ""
            and shas.get("player_win_player")
            == shas.get("legacy_player_win_player")),
        "legacy_winner_frame_identical": (
            by_id.get("player_win", {}).get("player_frame")
            == by_id.get("legacy_player_win", {}).get("player_frame")),
        "all_sv_pngs_nonempty": all(
            Path(r.get(f"{side}_sv", "")).is_file()
            and Path(r.get(f"{side}_sv", "")).stat().st_size > 5000
            for r in rows for side in ("player", "foe")),
        "default_zero_pollution": (
            def_run["payload"].get("use_3d") is False
            and def_run["payload"].get("layer_3d") is False
            and def_run["payload"].get("layer_3d_foe") is False
            and def_run["payload"].get("player_override") is False
            and def_run["payload"].get("enemy_override") is False
            and def_run["payload"].get("env_3d") == ""),
        "default_no_script_errors": (def_run["rc"] == 0
                                     and def_run["script_errors"] == 0),
        "default_two_pngs": len(list(def_dir.glob("*.png"))) == 2,
    }
    report = {
        "main": main_run, "default": def_run,
        "rows": rows, "diff_px": diffs, "sv_sha256": shas,
        "min_diff_threshold_px": MIN_DIFF_PX,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print("SCENE", r.get("id"), "cards", r.get("cards_at_scene"),
              "P", r.get("player_card"), r.get("player_frame"),
              "F", r.get("foe_card"), r.get("foe_frame"))
    for k, v in diffs.items():
        print("DIFF", k, v)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("MOTION_P1_PROBE_OK" if report["ok"]
          else "MOTION_P1_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
