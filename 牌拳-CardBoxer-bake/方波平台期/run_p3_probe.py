"""P3 · 引擎内上线态 A/B 取证（同进程，不写盘源文件）。

承重口径在看结果前钉死：
  * 落盘 leg_mode / leg_cap_deg 必须由引擎读回为 atan / 12.0；
  * 4 种模式逐场景的 mode、cap 读回必须与设定一致；
  * 每行 13 骨 delta 用 p3_math 独立同公式复算，逐骨对账；
  * shipped(atan12) vs rolled_back(hard9)：每个非站架动作帧双侧像素差 > 0，
    站架帧逐像素 0；
  * shipped vs reapplied 同进程逐像素相同（可逆且可复现）；
  * legacy_compat（删掉 leg_mode）必须与 rolled_back 逐像素相同
    —— 证明旧动作表配新驱动回落 hard，向后兼容；
  * 默认关 3D 零污染。

像素差只要求「> 0」这类结构性事实，不设凭结果调的量级阈值；
>200 px 的帧数单独作为观察值记录。

用法：python run_p3_probe.py
产出：data/p3_probe.json、shots/p3/**、shots/default_p3/**、logs/godot_p3*.log
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
sys.path.insert(0, str(HERE))
from p3_math import LEG_BONES, expected_delta  # noqa: E402

GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "p3_plateau_probe.gd"
DST = GAME / "tests" / "p3_plateau_probe.gd"
SHOTS = HERE / "shots" / "p3"
DEF = HERE / "shots" / "default_p3"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "p3_probe.json"
MAIN_MARKER = "P3_PLATEAU_JSON "
DISPLAY_MARKER = "DISPLAY_JSON "
CLEAR = ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
         "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
         "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_RAGE_START",
         "AMPLITUDE_P2_OUT", "P2_SHIPPED_OUT", "P3_OUT", "DISPLAY_DIR",
         "SHIPPED_OUT", "SHIPPED_MODE", "LIVE_MATCH_OUT",
         "LIVE_MATCH_CAP", "LIVE_MATCH_SEED")
FRAMES = [("stance", 0), ("jab", 1), ("sweep", 7), ("hit_heavy", 1)] + [
    ("sweep", i) for i in range(14, 22)]
MODES = ("shipped", "rolled_back", "reapplied", "legacy_compat")
MODE_LIVE = {"shipped": ("atan", 12.0), "rolled_back": ("hard", 9.0),
             "reapplied": ("atan", 12.0),
             "legacy_compat": ("<absent>", 9.0)}
MODE_MATH = {"shipped": ("atan", 12.0), "rolled_back": ("hard", 9.0),
             "reapplied": ("atan", 12.0),
             "legacy_compat": ("hard", 9.0)}


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() \
        if Path(p).is_file() else ""


def diff_px(a, b) -> int:
    a, b = Path(a), Path(b)
    if not (a.is_file() and b.is_file()):
        return -1
    ia, ib = Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")
    if ia.size != ib.size:
        return -1
    d = ImageChops.difference(ia, ib)
    r, g, bl, al = d.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g),
                            ImageChops.lighter(bl, al))
    return int(mx.point(lambda v: 255 if v > 8 else 0).histogram()[255])


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
            "rc": rc, "payload": payload,
            "script_errors": text.count("SCRIPT ERROR")
            + text.count("Parse Error"),
            "scenario_errors": text.count('Parameter "scenario" is null')}


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    assert GODOT.is_file() and SRC.is_file()
    shutil.copyfile(SRC, DST)
    if SHOTS.exists():
        shutil.rmtree(SHOTS)
    SHOTS.mkdir(parents=True, exist_ok=True)
    DEF.mkdir(parents=True, exist_ok=True)

    main_run = run_godot("p3plateau", "res://tests/p3_plateau_probe.gd",
                         {"CARD_BOXER_3D": "1", "P3_OUT": str(SHOTS)},
                         MAIN_MARKER, 6000)
    def_run = run_godot("p3default",
                        "res://tests/display_stopgap_probe.gd",
                        {"DISPLAY_DIR": str(DEF)}, DISPLAY_MARKER, 900)
    payload = main_run["payload"]
    rows = payload.get("rows", [])
    by_key = {r["key"]: r for r in rows}

    mode_bad, delta_bad = [], []
    for r in rows:
        want_mode, want_cap = MODE_LIVE[r["mode"]]
        for side in ("player", "foe"):
            if r.get(f"mode_live_{side}") != want_mode or abs(
                    float(r.get(f"cap_live_{side}", -1.0)) - want_cap) > 1e-6:
                mode_bad.append((r["key"], side,
                                 r.get(f"mode_live_{side}"),
                                 r.get(f"cap_live_{side}")))
        mm, mc = MODE_MATH[r["mode"]]
        exp = expected_delta(r["card"], r["frame"], mm, mc)
        for side in ("player", "foe"):
            got = r.get(f"{side}_delta", {})
            if not got or not exp:
                delta_bad.append((r["key"], side, "missing"))
                continue
            worst = max(abs(float(got.get(k, 1e9)) - exp[k]) for k in exp)
            if worst > 1e-3:
                delta_bad.append((r["key"], side, round(worst, 5)))
            peak = max(abs(float(got.get(k, 0.0))) for k in LEG_BONES)
            if peak > mc + 0.05:
                delta_bad.append((r["key"], side, "over_cap",
                                  round(peak, 4)))

    diffs: dict[str, int] = {}
    for mode in ("rolled_back", "reapplied", "legacy_compat"):
        for card, fr in FRAMES:
            for side in ("player", "foe"):
                a = by_key.get(f"shipped-{card}{fr:02d}", {}).get(
                    f"{side}_sv", "")
                b = by_key.get(f"{mode}-{card}{fr:02d}", {}).get(
                    f"{side}_sv", "")
                diffs[f"shipped_vs_{mode}:{card}{fr:02d}:{side}"] = \
                    diff_px(a, b)

    def group(prefix: str, exclude_stance: bool = False) -> list[str]:
        return [k for k in diffs if k.startswith(prefix)
                and (not exclude_stance or "stance" not in k)]

    action = group("shipped_vs_rolled_back", True)
    stance = [k for k in group("shipped_vs_rolled_back")
              if "stance" in k]
    reapp = group("shipped_vs_reapplied")
    legacy = group("shipped_vs_legacy_compat")
    rollback = group("shipped_vs_rolled_back")

    checks = {
        "main_marker_parsed": ("error" not in payload
                               and len(rows) == 4 * len(FRAMES)),
        "main_no_script_errors": (main_run["rc"] == 0
                                  and main_run["script_errors"] == 0),
        "main_no_scenario_errors": main_run["scenario_errors"] == 0,
        "use_3d_and_15_cards": (payload.get("use_3d") is True
                                and payload.get("cards_player") == 15
                                and payload.get("cards_foe") == 15),
        "shipped_readback_atan_12_both_sides": (
            payload.get("mapping_mode_player") == "atan"
            and payload.get("mapping_mode_foe") == "atan"
            and payload.get("mapping_cap_player") == 12.0
            and payload.get("mapping_cap_foe") == 12.0),
        "live_mode_and_cap_match_each_scene": not mode_bad,
        "hp_unchanged": payload.get("hp") == [100, 100],
        "delta_matches_python_formula": not delta_bad,
        "every_action_frame_changed_both_sides": (
            len(action) == 2 * (len(FRAMES) - 1)
            and all(diffs[k] > 0 for k in action)),
        "stance_untouched": (len(stance) == 2
                             and all(diffs[k] == 0 for k in stance)),
        "shipped_reapplied_identical_same_process": (
            len(reapp) == 2 * len(FRAMES)
            and all(diffs[k] == 0 for k in reapp)),
        "legacy_compat_equals_rollback_bytewise": (
            len(legacy) == len(rollback) == 2 * len(FRAMES)
            and all(diffs[k] == diffs[k.replace(
                "legacy_compat", "rolled_back")] for k in legacy)),
        "all_sv_pngs_nonempty": all(
            Path(r[f"{side}_sv"]).is_file()
            and Path(r[f"{side}_sv"]).stat().st_size > 5000
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
        "default_two_pngs": len(list(DEF.glob("*.png"))) == 2,
    }
    report = {
        "frames": [list(f) for f in FRAMES], "modes": list(MODES),
        "mode_live_spec": {k: list(v) for k, v in MODE_LIVE.items()},
        "mode_math_spec": {k: list(v) for k, v in MODE_MATH.items()},
        "main": main_run, "default": def_run, "rows": rows,
        "diff_px": diffs,
        "action_diff_gt_200": sum(diffs[k] > 200 for k in action),
        "action_diff_max": max((diffs[k] for k in action), default=-1),
        "mode_mismatches": mode_bad, "delta_mismatches": delta_bad,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("READBACK", payload.get("mapping_mode_player"),
          payload.get("mapping_cap_player"),
          payload.get("mapping_mode_foe"),
          payload.get("mapping_cap_foe"))
    print("ROWS", len(rows), "MODE_BAD", len(mode_bad),
          "DELTA_BAD", len(delta_bad))
    print("ACTION_DIFF_MAX", report["action_diff_max"],
          "ACTION_GT_200", report["action_diff_gt_200"], "/", len(action))
    print("STANCE_DIFF", [diffs[k] for k in stance])
    print("REAPPLIED_NONZERO",
          [k for k in reapp if diffs[k] != 0])
    print("LEGACY_MISMATCH",
          [k for k in legacy if diffs[k] != diffs[k.replace(
              "legacy_compat", "rolled_back")]])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("P3_PROBE_OK" if report["ok"] else "P3_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
