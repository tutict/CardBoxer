# -*- coding: utf-8 -*-
"""P5 · 引擎内 A/B 取证（同进程，不写盘源文件）。

承重口径在看结果前钉死：
  * 三模式 shipped / rolled_back / reapplied 在同一 Godot 进程内换运行时表，
    不碰 mapping（仍为 P3/P4 的 atan / 12.0）；
  * 帧清单从「独立读回算出的改动帧集合」生成，含 stance/jab 两个
    R2 明确不动的零差对照；
  * 每行 13 骨 delta 由 Python 按「哪张表」独立同公式复算，逐骨对账；
  * 改动帧两版表的臂骨 delta 必须不同，未改动帧必须相同；
  * shipped vs reapplied 同进程逐像素相同（可逆且可复现）；
  * stance/jab 逐像素 0（R2 不动 jab 的直接证据）；
  * 2D 侧由引擎读回 CardMotion._tracks，量化改动范围与 mf 峰值；
  * 默认关 3D 零污染。

像素差只记分布，不设凭结果调的量级阈值。

用法：python run_p5_probe.py
产出：data/p5_probe_frames.json、data/p5_probe.json、shots/p5/**、
      shots/default_p5/**、logs/godot_p5*.log
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pose_cost import GAME, delta_and_root, joints_of, load  # noqa: E402

GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "p5_pose_probe.gd"
SRC_2D = HERE / "tests" / "p5_2d_readback.gd"
DST = GAME / "tests" / "p5_pose_probe.gd"
DST_2D = GAME / "tests" / "p5_2d_readback.gd"
SHOTS = HERE / "shots" / "p5"
DEF = HERE / "shots" / "default_p5"
ORIG = HERE / "orig" / "pre-p5"
LOGDIR = HERE / "logs"
DATA = HERE / "data"
READBACK = DATA / "p5_readback.json"
CAND = DATA / "recommended_tracks.json"
FRAMES_FILE = DATA / "p5_probe_frames.json"
OUT = DATA / "p5_probe.json"

MAIN_MARKER = "P5_POSE_JSON "
DISPLAY_MARKER = "DISPLAY_JSON "
TWOD_MARKER = "P5_2D_JSON "
CLEAR = ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
         "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
         "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_RAGE_START",
         "AMPLITUDE_P2_OUT", "P2_SHIPPED_OUT", "P3_OUT", "DISPLAY_DIR",
         "SHIPPED_OUT", "SHIPPED_MODE", "LIVE_MATCH_OUT",
         "LIVE_MATCH_CAP", "LIVE_MATCH_SEED", "P4_OUT", "P4_ORIG",
         "P5_OUT", "P5_ORIG", "P5_FRAMES", "P5_EXPECT_MF")
MODES = ("shipped", "rolled_back", "reapplied")
ARM_BONES = ("upperarm_f", "forearm_f", "upperarm_b", "forearm_b")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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


def pick_frames(frames: list, peak: int, count: int) -> list:
    """改动帧里取首/四分位/峰值/末，去重后按时间排序。"""
    out = {frames[0], frames[-1], peak,
           frames[len(frames) // 4], frames[3 * len(frames) // 4]}
    if len(out) < count:
        for f in frames[1::3]:
            out.add(f)
            if len(out) >= count:
                break
    return sorted(out)[:count]


def make_frames_file() -> dict:
    rb = json.loads(READBACK.read_text(encoding="utf-8-sig"))
    cand = json.loads(CAND.read_text(encoding="utf-8-sig"))
    peaks = rb["axis_metrics_now"]
    wf = cand["changed_frames"]["wave"]
    cf = cand["changed_frames"]["cross"]
    wave_pk = peaks["wave"]["mf_peak_frame"]
    cross_pk = peaks["cross"]["mf_peak_frame"]
    assert wave_pk in wf and cross_pk in cf, "peak frame not in edited set"
    assert not cand["changed_frames"]["jab"], "R2 says jab must not change"

    frames = [
        {"card": "stance", "frame": 0, "role": "unchanged_stance"},
        {"card": "jab", "frame": peaks["jab"]["mf_peak_frame"],
         "role": "unchanged_jab"},
    ]
    for f in pick_frames(wf, wave_pk, 5):
        frames.append({"card": "wave", "frame": f,
                       "role": "edited_peak" if f == wave_pk else "edited"})
    for f in pick_frames(cf, cross_pk, 3):
        frames.append({"card": "cross", "frame": f,
                       "role": "edited_peak" if f == cross_pk else "edited"})
    cfg = {
        "source": "p5_readback.json + recommended_tracks.json (R1+R2)",
        "frames": frames,
        "marker": {"card": "wave", "frame": wave_pk, "joint": "f_hand"},
        "edited_cards": ["wave", "cross"],
        "expected_mf_peaks": {k: v["mf_peak_px"]
                              for k, v in peaks.items()},
    }
    FRAMES_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return cfg


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
                           timeout=600, cwd=str(GAME))
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
    DATA.mkdir(parents=True, exist_ok=True)
    assert GODOT.is_file() and SRC.is_file() and SRC_2D.is_file()
    assert ORIG.is_dir() and READBACK.is_file()
    cfg = make_frames_file()
    frames = [(f["card"], f["frame"], f["role"]) for f in cfg["frames"]]
    edited = [(c, f) for c, f, role in frames
              if role.startswith("edited")]
    unchanged = [(c, f) for c, f, role in frames
                 if role.startswith("unchanged")]

    cur = {side: load(GAME / "data" / name) for side, name in
           (("player", "motion_input.json"),
            ("foe", "motion_input_foe.json"))}
    old = {side: load(ORIG / name) for side, name in
           (("player", "motion_input.json"),
            ("foe", "motion_input_foe.json"))}

    def expected_delta(card: str, frame: int, mode: str) -> dict:
        table = old["player"] if mode == "rolled_back" else cur["player"]
        if card == "stance":
            j = joints_of(table["stance"])
        else:
            j = joints_of(table["cards"][card]["track"][frame])
        return delta_and_root(j)[0]

    def expected_mf(card: str, frame: int, mode: str) -> float:
        table = old["player"] if mode == "rolled_back" else cur["player"]
        if card == "stance":
            return -1.0
        f = table["cards"][card]["track"][frame]
        st = table["stance"]["f_hand"]
        return math.hypot(float(f["f_hand"][0]) - float(st[0]),
                          float(f["f_hand"][1]) - float(st[1]))

    shutil.copyfile(SRC, DST)
    shutil.copyfile(SRC_2D, DST_2D)
    if SHOTS.exists():
        shutil.rmtree(SHOTS)
    SHOTS.mkdir(parents=True, exist_ok=True)
    DEF.mkdir(parents=True, exist_ok=True)
    for f in DEF.glob("*.png"):
        f.unlink()

    expect_mf = json.dumps({k: cfg["expected_mf_peaks"][k]
                            for k in ("wave", "cross", "jab")},
                           ensure_ascii=False, separators=(",", ":"))
    main_run = run_godot(
        "p5pose", "res://tests/p5_pose_probe.gd",
        {"CARD_BOXER_3D": "1", "P5_OUT": str(SHOTS),
         "P5_ORIG": str(ORIG), "P5_FRAMES": str(FRAMES_FILE)},
        MAIN_MARKER, 6000)
    def_run = run_godot(
        "p5default", "res://tests/display_stopgap_probe.gd",
        {"DISPLAY_DIR": str(DEF)}, DISPLAY_MARKER, 900)
    two_d = run_godot(
        "p5twod", "res://tests/p5_2d_readback.gd",
        {"P5_ORIG": str(ORIG), "P5_EXPECT_MF": expect_mf},
        TWOD_MARKER, 300, headless=True)

    payload = main_run["payload"]
    rows = payload.get("rows", [])
    by_key = {r["key"]: r for r in rows}
    shipped_mp = payload.get("shipped_marker_p", "")
    shipped_mf = payload.get("shipped_marker_f", "")
    legacy_mp = payload.get("legacy_marker_p", "")
    legacy_mf = payload.get("legacy_marker_f", "")

    marker_bad, delta_bad, mf_bad = [], [], []
    for r in rows:
        want_p = legacy_mp if r["mode"] == "rolled_back" else shipped_mp
        want_f = legacy_mf if r["mode"] == "rolled_back" else shipped_mf
        if (r.get("table_marker_player") != want_p
                or r.get("table_marker_foe") != want_f):
            marker_bad.append((r["key"], r.get("table_marker_player"),
                               r.get("table_marker_foe")))
        exp = expected_delta(r["card"], r["frame"], r["mode"])
        for side in ("player", "foe"):
            got = r.get(f"{side}_delta", {})
            if not got or not exp:
                delta_bad.append((r["key"], side, "missing"))
                continue
            worst = max(abs(float(got.get(k, 1e9)) - exp[k]) for k in exp)
            if worst > 1e-3:
                delta_bad.append((r["key"], side, round(worst, 5)))
        want_mf = expected_mf(r["card"], r["frame"], r["mode"])
        got_mf = float(r.get("mf_live", -999.0))
        if abs(got_mf - want_mf) > 1e-3:
            mf_bad.append((r["key"], round(got_mf, 4),
                           round(want_mf, 4)))

    # 数值判据：改动帧两版表的臂骨 delta 必须不同，未改动帧必须相同
    delta_same, unchanged_delta_bad = [], []
    for card, fr in edited + unchanged:
        a = by_key.get(f"shipped-{card}{fr:02d}", {}).get("player_delta", {})
        b = by_key.get(f"rolled_back-{card}{fr:02d}", {}).get(
            "player_delta", {})
        if not a or not b:
            delta_same.append((card, fr, "missing"))
            continue
        gap = max(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0)))
                  for k in ARM_BONES)
        is_unchanged = (card, fr) in unchanged
        if not is_unchanged and gap <= 1e-4:
            delta_same.append((card, fr, round(gap, 6)))
        if is_unchanged and gap > 1e-4:
            unchanged_delta_bad.append((card, fr, round(gap, 6)))

    diffs: dict[str, int] = {}
    for mode in ("rolled_back", "reapplied"):
        for card, fr, _role in frames:
            for side in ("player", "foe"):
                a = by_key.get(f"shipped-{card}{fr:02d}", {}).get(
                    f"{side}_sv", "")
                b = by_key.get(f"{mode}-{card}{fr:02d}", {}).get(
                    f"{side}_sv", "")
                diffs[f"shipped_vs_{mode}:{card}{fr:02d}:{side}"] = \
                    diff_px(a, b)

    def group(prefix: str) -> list[str]:
        return [k for k in diffs if k.startswith(prefix)]

    edited_keys = [k for k in group("shipped_vs_rolled_back")
                   if any(k.endswith(f":{c}{f:02d}:{s}")
                          for c, f in edited for s in ("player", "foe"))]
    unchanged_keys = [k for k in group("shipped_vs_rolled_back")
                     if any(k.endswith(f":{c}{f:02d}:{s}")
                            for c, f in unchanged for s in ("player", "foe"))]
    reapp = group("shipped_vs_reapplied")
    nonzero = [k for k in edited_keys if diffs[k] > 0]

    twod_payload = two_d["payload"]
    checks = {
        "frames_file_has_10_scenes_2_unchanged": (
            len(frames) == 10 and len(edited) == 8
            and len(unchanged) == 2),
        "main_marker_parsed": ("error" not in payload
                               and len(rows) == len(MODES) * len(frames)),
        "frames_loaded_in_engine": payload.get("frames_loaded") == len(frames),
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
            and shipped_mp != legacy_mp and shipped_mf != legacy_mf),
        "table_marker_matches_every_scene": not marker_bad,
        "hp_unchanged": payload.get("hp") == [100, 100],
        "delta_matches_python_formula_per_table": not delta_bad,
        "all_edited_frame_arm_deltas_differ_between_tables": not delta_same,
        "unchanged_frame_arm_deltas_identical": not unchanged_delta_bad,
        "mf_live_matches_independent_readback": not mf_bad,
        "edited_pixel_diffs_present": len(nonzero) >= 1,
        "edited_pixel_diffs_majority": len(nonzero) >= len(edited_keys) // 2,
        "stance_and_jab_pixel_identical": (
            len(unchanged_keys) == 4
            and all(diffs[k] == 0 for k in unchanged_keys)),
        "shipped_reapplied_identical_same_process": (
            len(reapp) == 2 * len(frames)
            and all(diffs[k] == 0 for k in reapp)),
        "all_sv_pngs_nonempty": all(
            Path(r[f"{side}_sv"]).is_file()
            and Path(r[f"{side}_sv"]).stat().st_size > 5000
            for r in rows for side in ("player", "foe")),
        "two_d_readback_ok": (
            "error" not in twod_payload
            and bool(twod_payload.get("checks"))
            and all(v is True for v in twod_payload["checks"].values())
            and twod_payload.get("ok") is True),
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
        "frames": [list(f) for f in frames], "modes": list(MODES),
        "marker": cfg["marker"],
        "main": main_run, "default": def_run, "two_d": two_d,
        "rows": rows, "diff_px": diffs,
        "edited_diff_max": max((diffs[k] for k in edited_keys), default=-1),
        "edited_diff_nonzero": len(nonzero),
        "edited_diff_total": len(edited_keys),
        "edited_diff_zero_keys": [k for k in edited_keys if diffs[k] == 0],
        "unchanged_diffs": {k: diffs[k] for k in unchanged_keys},
        "delta_mismatches": delta_bad, "mf_mismatches": mf_bad,
        "marker_mismatches": marker_bad,
        "edited_delta_same": delta_same,
        "unchanged_delta_changed": unchanged_delta_bad,
        "shipped_marker_p": shipped_mp, "legacy_marker_p": legacy_mp,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("MARKERS shipped", shipped_mp, "legacy", legacy_mp)
    print("ROWS", len(rows), "MARKER_BAD", len(marker_bad),
          "DELTA_BAD", len(delta_bad), "MF_BAD", len(mf_bad))
    print("EDITED_DIFF_MAX", report["edited_diff_max"],
          "NONZERO", len(nonzero), "/", len(edited_keys))
    print("UNCHANGED_DIFFS", report["unchanged_diffs"])
    print("REAPPLIED_NONZERO", [k for k in reapp if diffs[k] != 0])
    print("DELTA_SAME", delta_same, "UNCHANGED_DELTA_BAD",
          unchanged_delta_bad)
    print("TWO_D", json.dumps(twod_payload, ensure_ascii=False)[:600])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("P5_PROBE_OK" if report["ok"] else "P5_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
