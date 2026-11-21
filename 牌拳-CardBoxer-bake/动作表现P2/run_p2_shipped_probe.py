"""P2 上线态引擎内 A/B：读回落盘 cap + 同进程 shipped/rollback/reapply 取证。

承重判据在看结果之前钉死：
  * 落盘真值必须由引擎读回为 9.0（不是探针自己设的）；
  * shipped 与 rolled_back(3.0) 的每个非站架动作帧双侧都要有可见像素差；
  * 站架帧必须逐像素不变（cap 不该影响站立）；
  * shipped 与 reapplied 同进程逐像素相同（改动可逆且渲染可复现）；
  * delta 用 Python 同公式重算对账，不看上游 ok 字段。
跨进程与旧 cap9 探针图的比较只作 diagnostic，不进 checks（整帧跨进程
逐像素等价在本仓不成立，SubViewport 原图也不预设必然相同）。

用法：python run_p2_shipped_probe.py
产出：data/p2_shipped_probe.json、shots/shipped/**、logs/godot_p2shipped*.log
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
SRC = HERE / "tests" / "p2_shipped_probe.gd"
DST = GAME / "tests" / "p2_shipped_probe.gd"
SHOTS = HERE / "shots" / "shipped"
DEF = HERE / "shots" / "default_shipped"
CAPS_SHOTS = HERE / "shots" / "caps"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "p2_shipped_probe.json"
MAIN_MARKER = "P2_SHIPPED_JSON "
DISPLAY_MARKER = "DISPLAY_JSON "
CLEAR = ("CARD_BOXER_3D", "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP",
         "CARD_BOXER_3D_STANCE", "CARD_BOXER_FOE_VISUAL",
         "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_RAGE_START",
         "AMPLITUDE_P2_OUT", "P2_SHIPPED_OUT", "DISPLAY_DIR",
         "SHIPPED_OUT", "SHIPPED_MODE")
LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
MIN_DIFF_PX = 200
EXPECTED_CAP = 9.0
BASE_CAP = 3.0
MODE_CAP = {"shipped": EXPECTED_CAP, "rolled_back": BASE_CAP,
            "reapplied": EXPECTED_CAP}
FRAMES = (("stance", 0), ("jab", 1), ("sweep", 7), ("hit_heavy", 1))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def diff_px(a: Path, b: Path) -> int:
    if not (Path(a).is_file() and Path(b).is_file()):
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


def expected_delta(card: str, frame: int, cap: float) -> dict:
    """用落盘真值的 mapping，只显式覆盖 leg_cap_deg 做逐骨对账。"""
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
    SHOTS.mkdir(parents=True, exist_ok=True)
    DEF.mkdir(parents=True, exist_ok=True)

    main_run = run_godot("p2shipped", "res://tests/p2_shipped_probe.gd",
                         {"CARD_BOXER_3D": "1",
                          "P2_SHIPPED_OUT": str(SHOTS)},
                         MAIN_MARKER, 3000)
    def_run = run_godot("p2shipped_default",
                        "res://tests/display_stopgap_probe.gd",
                        {"DISPLAY_DIR": str(DEF)}, DISPLAY_MARKER, 900)
    payload = main_run["payload"]
    rows = payload.get("rows", [])
    by_key = {r["key"]: r for r in rows}

    # 逐行对账：mode cap 读回、delta 公式、腿骨不越界
    cap_bad, delta_bad = [], []
    for r in rows:
        mode = r["mode"]
        want = MODE_CAP.get(mode)
        if want is None:
            cap_bad.append((r["key"], "unknown mode"))
            continue
        for side in ("player", "foe"):
            if abs(float(r.get(f"cap_live_{side}", -1.0)) - want) > 1e-6:
                cap_bad.append((r["key"], side,
                                r.get(f"cap_live_{side}"), want))
        exp = expected_delta(r["card"], r["frame"], want)
        for side in ("player", "foe"):
            got = r.get(f"{side}_delta", {})
            if not got:
                delta_bad.append((r["key"], side, "missing"))
                continue
            worst = max(abs(float(got.get(k, 1e9)) - exp[k]) for k in exp)
            if worst > 1e-3:
                delta_bad.append((r["key"], side, round(worst, 5)))
            peak = max(abs(float(got.get(k, 0.0))) for k in LEG_BONES)
            if peak > want + 1e-3:
                delta_bad.append((r["key"], side, "over_cap",
                                  round(peak, 4)))

    # 同进程 A/B 像素差
    diffs: dict[str, int] = {}
    for mode in ("rolled_back", "reapplied"):
        for card, fr in FRAMES:
            for side in ("player", "foe"):
                a = by_key.get(f"shipped-{card}{fr:02d}", {}).get(
                    f"{side}_sv", "")
                b = by_key.get(f"{mode}-{card}{fr:02d}", {}).get(
                    f"{side}_sv", "")
                diffs[f"shipped_vs_{mode}:{card}{fr:02d}:{side}"] = diff_px(
                    Path(a), Path(b))

    non_stance = [k for k in diffs
                  if k.startswith("shipped_vs_rolled_back")
                  and "stance" not in k]
    stance = [k for k in diffs
              if k.startswith("shipped_vs_rolled_back")
              and "stance" in k]
    reapp = [k for k in diffs if k.startswith("shipped_vs_reapplied")]

    # 跨进程独立探针 cap9 图：只作 diagnostic，不进 checks
    cross: dict[str, dict] = {}
    for card, fr in FRAMES:
        for side in ("player", "foe"):
            a = by_key.get(f"shipped-{card}{fr:02d}", {}).get(
                f"{side}_sv", "")
            b = CAPS_SHOTS / f"ap2-cap09-{card}{fr:02d}-sv-{side}.png"
            cross[f"{card}{fr:02d}:{side}"] = {
                "diff_px": diff_px(Path(a), b),
                "shipped_sha": sha(Path(a)), "cap09_probe_sha": sha(b),
                "bytewise_equal": bool(a) and Path(a).is_file()
                and b.is_file() and sha(Path(a)) == sha(b),
            }

    sv_shas = {f"{r['key']}:{s}": sha(Path(r[f"{s}_sv"]))
               for r in rows for s in ("player", "foe")}

    checks = {
        "main_marker_parsed": "error" not in payload and len(rows) == 12,
        "main_no_script_errors": (main_run["rc"] == 0
                                  and main_run["script_errors"] == 0),
        "main_no_scenario_errors": main_run["scenario_errors"] == 0,
        "use_3d_and_15_cards": (payload.get("use_3d") is True
                                and payload.get("cards_player") == 15
                                and payload.get("cards_foe") == 15),
        "shipped_cap_readback_is_9_both_sides": (
            payload.get("mapping_cap_player") == EXPECTED_CAP
            and payload.get("mapping_cap_foe") == EXPECTED_CAP),
        "live_caps_match_each_mode": not cap_bad,
        "hp_unchanged": payload.get("hp") == [100, 100],
        "delta_matches_python_formula": not delta_bad,
        "shipped_changes_every_action_frame_both_sides": (
            len(non_stance) == 6
            and all(diffs[k] > MIN_DIFF_PX for k in non_stance)),
        "stance_untouched_by_cap": (len(stance) == 2
                                    and all(diffs[k] == 0
                                            for k in stance)),
        "shipped_reapplied_identical_same_process": (
            len(reapp) == 8 and all(diffs[k] == 0 for k in reapp)),
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
        "expected_cap_deg": EXPECTED_CAP, "base_cap_deg": BASE_CAP,
        "min_diff_threshold_px": MIN_DIFF_PX,
        "main": main_run, "default": def_run, "rows": rows,
        "diff_px": diffs, "sv_sha256": sv_shas,
        "cross_process_cap09_diagnostic_only": cross,
        "delta_mismatches": delta_bad, "cap_violations": cap_bad,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("READBACK_CAP", payload.get("mapping_cap_player"),
          payload.get("mapping_cap_foe"))
    for k, v in diffs.items():
        print("DIFF", k, v)
    print("CROSS_PROCESS_BYTEWISE_EQUAL",
          sum(1 for v in cross.values() if v["bytewise_equal"]),
          "/", len(cross))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("P2_SHIPPED_PROBE_OK" if report["ok"]
          else "P2_SHIPPED_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
