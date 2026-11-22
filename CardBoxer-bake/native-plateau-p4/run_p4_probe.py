"""P4 · 引擎内上线态 A/B 取证（同进程，不写盘源文件）。

承重口径在看结果前钉死：
  * 落盘 mapping 仍为 P3 的 atan / 12.0（P4 只换数据层，不改驱动）；
  * 三模式运行时表标记必须区分开：shipped/reapplied = 落盘表，
    rolled_back = orig/pre-p4 原表；
  * 每行 13 骨 delta 用 p4_math 按「哪张表」独立同公式复算，逐骨对账；
  * 全部动作帧 shipped vs rolled_back 的腿骨 delta 必须不同（数值判据，
    比像素可靠；微扰不足 2px 时不强求每帧都有可见像素差）；
  * shipped vs reapplied 同进程逐像素相同（可逆且可复现）；
  * 站架帧逐像素 0；
  * 2D 侧由引擎读回 CardMotion._tracks，量化 11 关节位移 < 2px；
  * 默认关 3D 零污染。

像素差只记分布，不设凭结果调的量级阈值。

用法：python run_p4_probe.py
产出：data/p4_probe.json、shots/p4/**、shots/default_p4/**、
      logs/godot_p4*.log
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
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
sys.path.insert(0, str(HERE))
from p4_math import LEG_BONES, expected_delta  # noqa: E402

GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "p4_native_probe.gd"
SRC_2D = HERE / "tests" / "p4_2d_readback.gd"
DST = GAME / "tests" / "p4_native_probe.gd"
DST_2D = GAME / "tests" / "p4_2d_readback.gd"
SHOTS = HERE / "shots" / "p4"
DEF = HERE / "shots" / "default_p4"
ORIG = HERE / "orig" / "pre-p4"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "p4_probe.json"
LANDING = HERE / "data" / "landing_tracks.json"
MAIN_MARKER = "P4_NATIVE_JSON "
DISPLAY_MARKER = "DISPLAY_JSON "
TWOD_MARKER = "P4_2D_JSON "
CLEAR = ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
         "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
         "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_RAGE_START",
         "AMPLITUDE_P2_OUT", "P2_SHIPPED_OUT", "P3_OUT", "DISPLAY_DIR",
         "SHIPPED_OUT", "SHIPPED_MODE", "LIVE_MATCH_OUT",
         "LIVE_MATCH_CAP", "LIVE_MATCH_SEED", "P4_OUT", "P4_ORIG")
# 全部动作帧都取自 landing_tracks.json 的 micro2 改动帧
FRAMES = [("stance", 0), ("jab", 6), ("sweep", 14),
          ("hit_heavy", 8)] + [("focus", i) for i in range(6, 12)] + [
    ("wave", i) for i in range(29, 31)]
MODES = ("shipped", "rolled_back", "reapplied")
MODE_TABLE = {"shipped": "shipped", "rolled_back": "rolled_back",
              "reapplied": "shipped"}
ACTION = [f for f in FRAMES if f[0] != "stance"]


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
              frames: int, headless: bool = False) -> dict:
    env = os.environ.copy()
    for k in CLEAR:
        env.pop(k, None)
    env.update(extra)
    cmd = [str(GODOT)]
    if headless:
        cmd.append("--headless")
    cmd += ["--path", str(GAME)]
    if not headless:
        cmd += ["--resolution", "1280x720"]
    cmd += ["--quit-after", str(frames), "--script", script]
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, env=env, capture_output=True,
                           timeout=300, cwd=str(GAME))
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
    assert GODOT.is_file() and SRC.is_file() and SRC_2D.is_file()
    changed_frames = json.loads(LANDING.read_text(
        encoding="utf-8"))["changed_frames"]
    probe_frames_bad = [(c, f) for c, f in ACTION
                        if f not in changed_frames.get(c, [])]
    shutil.copyfile(SRC, DST)
    shutil.copyfile(SRC_2D, DST_2D)
    if SHOTS.exists():
        shutil.rmtree(SHOTS)
    SHOTS.mkdir(parents=True, exist_ok=True)
    DEF.mkdir(parents=True, exist_ok=True)

    main_run = run_godot(
        "p4native", "res://tests/p4_native_probe.gd",
        {"CARD_BOXER_3D": "1", "P4_OUT": str(SHOTS),
         "P4_ORIG": str(ORIG)}, MAIN_MARKER, 6000)
    def_run = run_godot(
        "p4default", "res://tests/display_stopgap_probe.gd",
        {"DISPLAY_DIR": str(DEF)}, DISPLAY_MARKER, 900)
    two_d = run_godot(
        "p4twod", "res://tests/p4_2d_readback.gd",
        {"P4_ORIG": str(ORIG)}, TWOD_MARKER, 300, headless=True)

    payload = main_run["payload"]
    rows = payload.get("rows", [])
    by_key = {r["key"]: r for r in rows}

    shipped_mp = payload.get("shipped_marker_p", "")
    shipped_mf = payload.get("shipped_marker_f", "")
    legacy_mp = payload.get("legacy_marker_p", "")
    legacy_mf = payload.get("legacy_marker_f", "")

    marker_bad, delta_bad = [], []
    for r in rows:
        want_p = legacy_mp if r["mode"] == "rolled_back" else shipped_mp
        want_f = legacy_mf if r["mode"] == "rolled_back" else shipped_mf
        if (r.get("table_marker_player") != want_p
                or r.get("table_marker_foe") != want_f):
            marker_bad.append((r["key"], r.get("table_marker_player"),
                               r.get("table_marker_foe")))
        exp = expected_delta(r["card"], r["frame"],
                             MODE_TABLE[r["mode"]])
        for side in ("player", "foe"):
            got = r.get(f"{side}_delta", {})
            if not got or not exp:
                delta_bad.append((r["key"], side, "missing"))
                continue
            worst = max(abs(float(got.get(k, 1e9)) - exp[k]) for k in exp)
            if worst > 1e-3:
                delta_bad.append((r["key"], side, round(worst, 5)))

    # 数值判据：动作帧两版表的腿骨 delta 必须不同
    delta_same = []
    for card, fr in ACTION:
        for side in ("player", "foe"):
            a = by_key.get(f"shipped-{card}{fr:02d}", {}).get(
                f"{side}_delta", {})
            b = by_key.get(f"rolled_back-{card}{fr:02d}", {}).get(
                f"{side}_delta", {})
            if not a or not b:
                delta_same.append((card, fr, side, "missing"))
                continue
            gap = max(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0)))
                      for k in LEG_BONES)
            if gap <= 1e-4:
                delta_same.append((card, fr, side, round(gap, 6)))

    diffs: dict[str, int] = {}
    for mode in ("rolled_back", "reapplied"):
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
    nonzero = [k for k in action if diffs[k] > 0]

    twod_payload = two_d["payload"]
    checks = {
        "all_action_frames_are_edited_frames": not probe_frames_bad,
        "main_marker_parsed": ("error" not in payload
                               and len(rows) == len(MODES) * len(FRAMES)),
        "main_no_script_errors": (main_run["rc"] == 0
                                  and main_run["script_errors"] == 0),
        "main_no_scenario_errors": main_run["scenario_errors"] == 0,
        "use_3d_and_15_cards": (payload.get("use_3d") is True
                                and payload.get("cards_player") == 15
                                and payload.get("cards_foe") == 15),
        "shipped_mapping_still_atan12": (
            payload.get("mapping_mode") == "atan"
            and payload.get("mapping_cap") == 12.0),
        "shipped_and_legacy_table_markers_differ": (
            bool(shipped_mp) and bool(legacy_mp)
            and shipped_mp != legacy_mp
            and shipped_mf != legacy_mf),
        "table_marker_matches_every_scene": not marker_bad,
        "hp_unchanged": payload.get("hp") == [100, 100],
        "delta_matches_python_formula_per_table": not delta_bad,
        "all_action_deltas_differ_between_tables": not delta_same,
        "action_pixel_diffs_present": len(nonzero) >= 1,
        "action_pixel_diffs_majority": len(nonzero) >= len(action) // 2,
        "stance_untouched": (len(stance) == 2
                             and all(diffs[k] == 0 for k in stance)),
        "shipped_reapplied_identical_same_process": (
            len(reapp) == 2 * len(FRAMES)
            and all(diffs[k] == 0 for k in reapp)),
        "all_sv_pngs_nonempty": all(
            Path(r[f"{side}_sv"]).is_file()
            and Path(r[f"{side}_sv"]).stat().st_size > 5000
            for r in rows for side in ("player", "foe")),
        "two_d_readback_ok": (
            "error" not in twod_payload
            and bool(twod_payload.get("checks"))
            and all(v is True for v in twod_payload["checks"].values())
            and twod_payload.get("ok") is True
            and twod_payload.get("max_joint_delta_px", 99) < 2.0),
        "two_d_no_script_errors": (two_d["rc"] == 0
                                   and two_d["script_errors"] == 0),
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
        "mode_table_spec": MODE_TABLE,
        "main": main_run, "default": def_run, "two_d": two_d,
        "rows": rows, "diff_px": diffs,
        "action_diff_max": max((diffs[k] for k in action), default=-1),
        "action_diff_nonzero": len(nonzero),
        "action_diff_total": len(action),
        "action_diff_zero_keys": [k for k in action if diffs[k] == 0],
        "action_delta_gaps_bad": delta_same,
        "probe_frames_not_in_edited_set": probe_frames_bad,
        "marker_mismatches": marker_bad, "delta_mismatches": delta_bad,
        "shipped_marker_p": shipped_mp, "legacy_marker_p": legacy_mp,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("READBACK", payload.get("mapping_mode"),
          payload.get("mapping_cap"))
    print("MARKERS shipped", shipped_mp, "legacy", legacy_mp)
    print("ROWS", len(rows), "MARKER_BAD", len(marker_bad),
          "DELTA_BAD", len(delta_bad), "DELTA_SAME", len(delta_same))
    print("ACTION_DIFF_MAX", report["action_diff_max"],
          "NONZERO", len(nonzero), "/", len(action))
    print("STANCE_DIFF", [diffs[k] for k in stance])
    print("REAPPLIED_NONZERO", [k for k in reapp if diffs[k] != 0])
    print("TWO_D", twod_payload)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("P4_PROBE_OK" if report["ok"] else "P4_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
