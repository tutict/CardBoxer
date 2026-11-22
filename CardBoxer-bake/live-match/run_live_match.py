"""B 路线 · 真实自动对局 A/B 取证（不冻结、不注入动作）。

两次独立 Godot 进程，同一个固定 RNG 种子：
  cap9 —— 完全使用落盘 leg_cap_deg=9.0，探针不覆盖任何 mapping；
  cap3 —— 运行时把两份 mapping 覆盖回 3.0，等价于 P2 上线前。
两局都由 CARD_BOXER_TAIKOU_BOT 自动打完三回。

判据在看结果之前钉死的是「采集健全性」：marker、rc、脚本错误、
三回跑完、阶段序列、cap 读回、delta 与 Python 同公式逐骨对账。
牌局指纹是否一致是**前提检验**，不是放行判据：不一致就如实记
framewise_ab_applicable=False，逐帧 A/B 降级为两局独立统计，
不硬比、不折进计数。

用法：python run_live_match.py [--only cap9|cap3]
产出：data/live_match.json、shots/cap9/**、shots/cap3/**、logs/godot_live_*.log
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
DIAG = BAKE / "motion-diagnostics"
sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "live_match_probe.gd"
DST = GAME / "tests" / "live_match_probe.gd"
SHOTS = HERE / "shots"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "live_match.json"
MARKER = "LIVE_MATCH_JSON "
SEED = "20261114"
FRAMES = 6000
CLEAR = (
    "CARD_BOXER_3D", "CARD_BOXER_BOT", "CARD_BOXER_TAIKOU_BOT",
    "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP", "CARD_BOXER_3D_STANCE",
    "CARD_BOXER_FOE_VISUAL", "CARD_BOXER_RAGE_START",
    "CARD_BOXER_TK_SHOT", "CARD_BOXER_P0_SHOT",
    "CARD_BOXER_CAPTURE", "CARD_BOXER_CAPTURE_AT",
    "CARD_BOXER_RHYTHM_SHOT",
    "AMPLITUDE_P2_OUT", "P2_SHIPPED_OUT",
    "LIVE_MATCH_OUT", "LIVE_MATCH_CAP", "LIVE_MATCH_SEED",
    "DISPLAY_DIR", "SHIPPED_OUT", "SHIPPED_MODE",
)
LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")
PHASE_ORDER = ("discard", "select", "reveal", "resolve")


def run_godot(tag: str, extra: dict) -> dict:
    env = os.environ.copy()
    for k in CLEAR:
        env.pop(k, None)
    env.update(extra)
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
             "--quit-after", str(FRAMES),
             "--script", "res://tests/live_match_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = p.returncode
        text = (p.stdout + b"\n--- STDERR ---\n"
                + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    (LOGDIR / f"godot_live_{tag}.log").write_text(text, encoding="utf-8")
    line = next((l for l in text.splitlines()
                 if l.startswith(MARKER)), None)
    payload = json.loads(line[len(MARKER):]) if line else {"error": "no marker"}
    return {"tag": tag, "seconds": round(time.perf_counter() - t0, 3),
            "rc": rc, "payload": payload,
            "script_errors": text.count("SCRIPT ERROR")
            + text.count("Parse Error"),
            "scenario_errors": text.count('Parameter "scenario" is null'),
            "extra": {k: v for k, v in extra.items()
                      if k.startswith("LIVE_MATCH")
                      or k.startswith("CARD_BOXER_3D")
                      or k.startswith("CARD_BOXER_TAIKOU")}}


def expected_delta(card: str, frame: int, cap: float) -> dict:
    """用落盘真值的 mapping，只覆盖 leg_cap_deg，与 rig_driver 同公式。"""
    mi = json.loads((GAME / "data" / "motion_input.json").read_text(
        encoding="utf-8"))
    cm = json.loads((GAME / "data" / "card_motion.json").read_text(
        encoding="utf-8"))
    keys = list(mi["joint_names"])
    if card == "stance":
        fj = {k: tuple(v) for k, v in mi["stance"].items()}
    else:
        body = cm["cards"].get(card) or cm["motions"].get(card)
        if body is None:
            return {}
        n = len(body["track"])
        if frame < 0 or frame >= n:
            return {}
        fj = {k: tuple(body["track"][frame][k]) for k in keys}
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    mapping = dict(mi["mapping"])
    mapping["leg_cap_deg"] = cap
    d, _raw = retarget_delta(fj, stance_j, mi["chain"], mapping,
                             make_points(stance_j))
    return {k: float(v) for k, v in d.items()}


def fingerprint(payload: dict) -> dict:
    """牌局指纹：每回 resolve 的动作卡 / 赢家 / 终局 HP。"""
    turns: dict[int, dict] = {}
    for r in payload.get("rows", []):
        if r.get("tk_phase") != "resolve":
            continue
        k = int(r["tk_turn"])
        t = turns.setdefault(k, {"motion_ids": set(), "winners": set(),
                                 "hp_end": None, "extras": set()})
        t["motion_ids"].add(str(r.get("tk_motion_id", "")))
        t["winners"].add(str(r.get("tk_winner", "")))
        t["extras"].add(str(r.get("tk_motion_extra", "")))
        t["hp_end"] = list(r.get("hp", []))
    return {str(k): {"motion_ids": sorted(v["motion_ids"]),
                     "winners": sorted(v["winners"]),
                     "extras": sorted(v["extras"]),
                     "hp_end": v["hp_end"]}
            for k, v in sorted(turns.items())}


def phase_sequence(payload: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in payload.get("phase_changes", []):
        if c["kind"] != "tk_phase":
            continue
        turn, ph = c["value"].split(":", 1)
        if turn not in out:
            out[turn] = []
        if ph not in out[turn][-1:]:
            out[turn].append(ph)
    return out


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    assert GODOT.is_file() and SRC.is_file()
    shutil.copyfile(SRC, DST)
    base = {"CARD_BOXER_3D": "1", "CARD_BOXER_TAIKOU_BOT": "1",
            "LIVE_MATCH_SEED": SEED}
    cases = [
        ("cap9", dict(base, LIVE_MATCH_OUT=str(SHOTS / "cap9")), 9.0),
        ("cap3", dict(base, LIVE_MATCH_OUT=str(SHOTS / "cap3"),
                      LIVE_MATCH_CAP="3.0"), 3.0),
    ]
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        want = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        cases = [c for c in cases if c[0] == want]
        if not cases:
            print("UNKNOWN_ONLY", want)
            return 1

    # 每次重跑前清空本局输出目录：否则上一局的 PNG 会残留，
    # 看图时把旧帧误当成当前局（第一次试跑就踩过这个）。
    for tag, _extra, _cap in cases:
        p = SHOTS / tag
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)

    runs, caps = {}, {}
    for tag, extra, cap in cases:
        runs[tag] = run_godot(tag, extra)
        caps[tag] = cap
        print("RUN", tag, "rc", runs[tag]["rc"],
              "seconds", runs[tag]["seconds"],
              "rows", len(runs[tag]["payload"].get("rows", [])),
              "end", runs[tag]["payload"].get("end_reason"))

    # delta 逐行对账（缓存公式结果，避免每行重读两个大 JSON）
    cache: dict[tuple, dict] = {}
    delta_bad = []

    def exp(card: str, frame: int, cap: float) -> dict:
        k = (card, frame, cap)
        if k not in cache:
            cache[k] = expected_delta(card, frame, cap)
        return cache[k]

    for tag, cap in caps.items():
        for r in runs[tag]["payload"].get("rows", []):
            for side in ("player", "foe"):
                st = r.get(side, {})
                got = st.get("delta", {})
                want = exp(str(st.get("card", "")),
                           int(st.get("frame", -1)), cap)
                if not want or not got:
                    delta_bad.append((tag, r["idx"], side, "missing"))
                    continue
                worst = max(abs(float(got.get(k, 1e9)) - want[k])
                            for k in want)
                if worst > 1e-3:
                    delta_bad.append((tag, r["idx"], side,
                                      round(worst, 5)))

    seqs = {tag: phase_sequence(r["payload"])
            for tag, r in runs.items()}
    fps = {tag: fingerprint(r["payload"]) for tag, r in runs.items()}
    same_seed = all(r["payload"].get("seed") == int(SEED)
                    for r in runs.values())
    fp_equal = (len(runs) == 2 and fps.get("cap9") == fps.get("cap3"))

    checks = {}
    for tag, cap in caps.items():
        p = runs[tag]["payload"]
        checks[f"{tag}_marker_parsed"] = (
            "error" not in p and len(p.get("rows", [])) >= 50)
        checks[f"{tag}_rc_and_no_script_errors"] = (
            runs[tag]["rc"] == 0 and runs[tag]["script_errors"] == 0)
        checks[f"{tag}_no_scenario_errors"] = (
            runs[tag]["scenario_errors"] == 0)
        checks[f"{tag}_round_over_not_timeout"] = (
            p.get("end_reason") == "round_over")
        checks[f"{tag}_use_3d_and_bot"] = (
            p.get("use_3d") is True and p.get("tk_bot") is True)
        checks[f"{tag}_15_cards_both"] = (
            p.get("cards_player") == 15 and p.get("cards_foe") == 15)
        checks[f"{tag}_cap_readback"] = (
            p.get("cap_readback") == cap)
        checks[f"{tag}_final_round_phase_over"] = (
            p.get("final_round_phase") in ("over", "match_over"))
        checks[f"{tag}_three_turns"] = (
            set(seqs[tag].keys()) == {"1", "2", "3"})
        checks[f"{tag}_phase_order_per_turn"] = all(
            tuple(v) == PHASE_ORDER for v in seqs[tag].values())
        checks[f"{tag}_all_rows_cap_live"] = all(
            r.get("cap_live") == cap for r in p.get("rows", []))
        checks[f"{tag}_frames_applied_growing"] = all(
            b["player"]["frames_applied"]
            > a["player"]["frames_applied"]
            for a, b in zip(p.get("rows", []),
                            p.get("rows", [])[1:]))
    checks["same_seed_both_runs"] = same_seed
    checks["all_rows_delta_match_python_formula"] = not delta_bad

    report = {
        "cases": {tag: {"extra": runs[tag]["extra"],
                        "rc": runs[tag]["rc"],
                        "seconds": runs[tag]["seconds"],
                        "script_errors": runs[tag]["script_errors"],
                        "scenario_errors": runs[tag]["scenario_errors"],
                        "cap": caps[tag],
                        "payload": runs[tag]["payload"]}
                  for tag in runs},
        "phase_sequences": seqs,
        "fingerprints": fps,
        "preconditions": {
            "same_seed": same_seed,
            "fingerprint_equal": fp_equal,
            "framewise_ab_applicable": fp_equal,
            "note": ("牌局指纹不一致时逐帧 A/B 前提不成立，"
                     "两局各自统计，不硬比、不折进判据计数。"),
        },
        "delta_mismatches": delta_bad,
        "sample_s": 0.12,
        "seed": int(SEED),
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for tag in runs:
        p = runs[tag]["payload"]
        print("SEQ", tag, seqs[tag])
        print("FP", tag, fps[tag])
        print("END", tag, p.get("end_reason"), "t", p.get("total_t"),
              "hp", p.get("final_hp"), "wins", p.get("final_wins"))
    print("FINGERPRINT_EQUAL", fp_equal)
    print("DELTA_MISMATCHES", len(delta_bad))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("LIVE_MATCH_OK" if report["ok"] else "LIVE_MATCH_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
