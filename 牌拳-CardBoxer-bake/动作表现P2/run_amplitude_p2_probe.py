"""P2 引擎内 A/B 取证：4 档 leg_cap × 4 帧，读回 delta 与 SubViewport 原图。

主探针 CARD_BOXER_3D=1，运行时切两份 mapping 的 leg_cap_deg；
默认关另起一个进程用 display_stopgap_probe.gd 复核零污染。
判据不看上游 ok 字段：delta 用 Python 同公式重算对账，像素差从 PNG 重算。

用法：python run_amplitude_p2_probe.py
产出：data/amplitude_p2_probe.json、shots/**、logs/godot_*.log
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
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
DIAG = BAKE / "动作优化诊断"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "amplitude_p2_probe.gd"
DST = GAME / "tests" / "amplitude_p2_probe.gd"
SHOTS = HERE / "shots"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "amplitude_p2_probe.json"
MAIN_MARKER = "AMPLITUDE_P2_JSON "
DISPLAY_MARKER = "DISPLAY_JSON "
CLEAR = ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
         "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
         "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_RAGE_START",
         "AMPLITUDE_P2_OUT", "DISPLAY_DIR", "SHIPPED_OUT", "SHIPPED_MODE")
LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
MIN_DIFF_PX = 200


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def diff_px(a: Path, b: Path) -> int:
    if not (Path(a).is_file() and Path(b).is_file()):
        return 0
    ia, ib = Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")
    if ia.size != ib.size:
        return 0
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


def expected_delta(card: str, frame: int, cap: float) -> dict:
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    keys = list(mi["joint_names"])
    if card == "stance":
        fj = {k: tuple(v) for k, v in mi["stance"].items()}
    else:
        body = cm["cards"].get(card) or cm["motions"].get(card)
        fj = {k: tuple(body["track"][frame][k]) for k in keys}
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    mapping = dict(mi["mapping"])
    mapping["leg_cap_deg"] = cap
    d, _raw = retarget_delta(fj, stance_j, mi["chain"], mapping,
                             make_points(stance_j))
    return {k: float(v) for k, v in d.items()}


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    assert GODOT.is_file() and SRC.is_file()
    shutil.copyfile(SRC, DST)
    main_dir = SHOTS / "caps"
    def_dir = SHOTS / "default"
    main_dir.mkdir(parents=True, exist_ok=True)
    def_dir.mkdir(parents=True, exist_ok=True)

    main_run = run_godot("p2caps", "res://tests/amplitude_p2_probe.gd",
                         {"CARD_BOXER_3D": "1",
                          "AMPLITUDE_P2_OUT": str(main_dir)},
                         MAIN_MARKER, 3000)
    def_run = run_godot("p2default", "res://tests/display_stopgap_probe.gd",
                        {"DISPLAY_DIR": str(def_dir)}, DISPLAY_MARKER, 900)
    payload = main_run["payload"]
    rows = payload.get("rows", [])

    # delta 与 Python 同公式逐骨对账
    delta_bad, cap_bad = [], []
    for r in rows:
        exp = expected_delta(r["card"], r["frame"], r["cap"])
        for side in ("player", "foe"):
            got = r.get(f"{side}_delta", {})
            if not got:
                delta_bad.append((r["key"], side, "missing"))
                continue
            worst = max(abs(float(got.get(k, 1e9)) - exp[k]) for k in exp)
            if worst > 1e-3:
                delta_bad.append((r["key"], side, round(worst, 5)))
        for side in ("player", "foe"):
            got = r.get(f"{side}_delta", {})
            peak = max(abs(float(got.get(k, 0.0))) for k in LEG_BONES)
            if peak > r["cap"] + 1e-3:
                cap_bad.append((r["key"], side, round(peak, 4)))

    by_key = {r["key"]: r for r in rows}
    diffs, shas = {}, {}
    for cap in (6, 9, 12):
        for card, fr in (("stance", 0), ("jab", 1), ("sweep", 7),
                         ("hit_heavy", 1)):
            k0 = f"cap03-{card}{fr:02d}"
            k1 = f"cap{cap:02d}-{card}{fr:02d}"
            for side in ("player", "foe"):
                diffs[f"{k1}_{side}"] = diff_px(
                    Path(by_key.get(k0, {}).get(f"{side}_sv", "")),
                    Path(by_key.get(k1, {}).get(f"{side}_sv", "")))
    for r in rows:
        for side in ("player", "foe"):
            shas[f"{r['key']}_{side}"] = sha(Path(r[f"{side}_sv"]))

    # 腿部幅度随 cap 单调（逐帧、逐侧）
    leg_mean = {}
    for cap in (3, 6, 9, 12):
        vals = []
        for r in rows:
            if int(r["cap"]) != cap:
                continue
            d = r.get("player_delta", {})
            vals.append(max(abs(float(d.get(k, 0.0))) for k in LEG_BONES))
        leg_mean[str(cap)] = round(sum(vals) / max(1, len(vals)), 4)
    monotonic = all(leg_mean[str(a)] < leg_mean[str(b)]
                    for a, b in ((3, 6), (6, 9), (9, 12)))

    checks = {
        "main_marker_parsed": "error" not in payload and len(rows) == 16,
        "main_no_script_errors": (main_run["rc"] == 0
                                  and main_run["script_errors"] == 0),
        "main_no_scenario_errors": main_run["scenario_errors"] == 0,
        "use_3d_and_15_cards": (payload.get("use_3d") is True
                                and payload.get("cards_player") == 15
                                and payload.get("cards_foe") == 15),
        "hp_unchanged": payload.get("hp") == [100, 100],
        "delta_matches_python_formula": not delta_bad,
        "leg_delta_never_exceeds_cap": not cap_bad,
        "leg_amplitude_monotonic_in_cap": monotonic,
        "cap09_changes_pixels": any(
            v > MIN_DIFF_PX for k, v in diffs.items()
            if k.startswith("cap09-") and "stance" not in k),
        "cap12_changes_pixels": any(
            v > MIN_DIFF_PX for k, v in diffs.items()
            if k.startswith("cap12-") and "stance" not in k),
        "stance_unchanged_by_cap": all(
            v == 0 for k, v in diffs.items() if "stance" in k),
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
        "default_two_pngs": len(list(def_dir.glob("*.png"))) == 2,
    }
    report = {"main": main_run, "default": def_run, "rows": rows,
              "diff_px_vs_cap03": diffs, "sv_sha256": shas,
              "leg_peak_mean_deg_by_cap": leg_mean,
              "delta_mismatches": delta_bad, "cap_violations": cap_bad,
              "min_diff_threshold_px": MIN_DIFF_PX,
              "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        d = r.get("player_delta", {})
        peak = max(abs(float(d.get(k, 0.0))) for k in LEG_BONES)
        print("SCENE", r["key"], "leg_peak", round(peak, 3))
    print("LEG_MEAN", leg_mean)
    for k, v in diffs.items():
        print("DIFF", k, v)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("AMPLITUDE_P2_PROBE_OK" if report["ok"]
          else "AMPLITUDE_P2_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
