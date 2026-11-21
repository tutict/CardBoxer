"""P4 · 实机验收 · 真实自动对局取证（不冻结、不注入、不覆盖 mapping）。

两次独立 Godot 进程，同一个固定 RNG 种子：
  three_d      CARD_BOXER_3D=1：3D 层参与绘制，读回 13 骨 delta / 表标记。
  default_off  不设 3D：motion_3d 为空字典，2D 关节表才参与绘制。

P4 改的是 card_motion.json；3D 开态 fighter.gd::_draw() 画完影子就
early return，2D 关节表不参与绘制，所以**必须**两种状态都真跑一局。
探针只采样与截帧，不碰判定、动作表、阶段时长、paused。

跨 Godot 进程整局 RNG 会漂移（B 路线实测三种牌局指纹），因此本脚本
不做跨进程逐帧像素 A/B；A/B 交给 analyze_live_p4.py 用同源帧序列
在 Python 侧按 P3 原表 / P4 落地表复算。

判据在看结果之前钉死的是「采集健全性」：marker、rc、脚本错误、
paused 永不为真、三回跑完、阶段序列、表标记、delta 逐骨对账、
PNG 非空且整帧 sha 全不同、跑前后 14 个受监控文件 sha 全同。

用法：python run_live_p4.py [--only three_d|default_off]
产出：data/live_p4.json、data/sha_baseline.json、shots/<tag>/**、logs/
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

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
P4 = BAKE / "原生平台P4"
sys.path.insert(0, str(P4))
from p4_math import expected_delta  # noqa: E402

GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "p4_live_probe.gd"
DST = GAME / "tests" / "p4_live_probe.gd"
SHOTS = HERE / "shots"
LOGDIR = HERE / "logs"
OUT = HERE / "data" / "live_p4.json"
SHA_OUT = HERE / "data" / "sha_baseline.json"
MARKER = "P4_LIVE_JSON "
SEED = "20261114"
FRAMES = 6000
CLEAR = (
    "CARD_BOXER_3D", "CARD_BOXER_BOT", "CARD_BOXER_TAIKOU_BOT",
    "CARD_BOXER_3D_YAW", "CARD_BOXER_3D_FLIP", "CARD_BOXER_3D_STANCE",
    "CARD_BOXER_FOE_VISUAL", "CARD_BOXER_RAGE_START",
    "CARD_BOXER_TK_SHOT", "CARD_BOXER_P0_SHOT",
    "CARD_BOXER_CAPTURE", "CARD_BOXER_CAPTURE_AT",
    "CARD_BOXER_RHYTHM_SHOT", "AMPLITUDE_P2_OUT", "P2_SHIPPED_OUT",
    "LIVE_MATCH_OUT", "LIVE_MATCH_CAP", "LIVE_MATCH_SEED",
    "P4_OUT", "P4_ORIG", "P4_LIVE_OUT", "P4_LIVE_SEED",
    "DISPLAY_DIR", "SHIPPED_OUT", "SHIPPED_MODE",
)
PHASE_ORDER = ("discard", "select", "reveal", "resolve")


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def watched_files() -> list[str]:
    """受监控文件清单沿用 P4 基线，sha 一律按当前工作树重算。"""
    return list(load(P4 / "data" / "baseline_p4.json")["files"].keys())


def sha_tree() -> dict:
    out = {}
    for rel in watched_files():
        p = GAME / rel
        out[rel] = {"exists": p.is_file(),
                    "size": p.stat().st_size if p.is_file() else 0,
                    "sha256": sha(p) if p.is_file() else ""}
    return out


def marker_of(mi: dict, card: str, frame: int) -> str:
    """与 p4_live_probe.gd::_marker_3d 同口径，按 (card, frame) 取 f_knee。"""
    if card in ("stance", ""):
        kn = mi["stance"]["f_knee"]
    else:
        cards = mi.get("cards", {})
        if card not in cards:
            return "<no_card>"
        tr = cards[card]["track"]
        if frame < 0 or frame >= len(tr):
            return "<bad_frame>"
        kn = tr[frame]["f_knee"]
    return "%.6f|%.6f" % (float(kn[0]), float(kn[1]))


def marker_2d_of(cm: dict) -> str:
    kn = cm["cards"]["focus"]["track"][8]["f_knee"]
    return "%.6f|%.6f" % (float(kn[0]), float(kn[1]))


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
             "--script", "res://tests/p4_live_probe.gd"],
            env=env, capture_output=True, timeout=300, cwd=str(GAME))
        rc = p.returncode
        text = (p.stdout + b"\n--- STDERR ---\n"
                + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc = -1
        text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
            "utf-8", "replace")
    (LOGDIR / f"godot_p4_live_{tag}.log").write_text(
        text, encoding="utf-8")
    line = next((l for l in text.splitlines()
                 if l.startswith(MARKER)), None)
    payload = json.loads(line[len(MARKER):]) if line else {"error": "no marker"}
    return {"tag": tag, "seconds": round(time.perf_counter() - t0, 3),
            "rc": rc, "payload": payload,
            "script_errors": text.count("SCRIPT ERROR")
            + text.count("Parse Error"),
            "scenario_errors": text.count('Parameter "scenario" is null'),
            "extra": {k: v for k, v in extra.items()
                      if k.startswith("P4_LIVE")
                      or k.startswith("CARD_BOXER_3D")
                      or k.startswith("CARD_BOXER_TAIKOU")}}


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


def png_stats(payload: dict, key: str) -> dict:
    paths = [Path(r[key]) for r in payload.get("rows", [])
             if r.get(key) and Path(r[key]).is_file()]
    return {"total": len(paths),
            "nonempty": sum(1 for p in paths if p.stat().st_size > 0),
            "unique_sha": len({sha(p) for p in paths})}


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    assert GODOT.is_file() and SRC.is_file()
    before = sha_tree()
    SHA_OUT.write_text(json.dumps(
        {"game": str(GAME), "before": before},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(SRC, DST)

    shipped_mi = load(GAME / "data" / "motion_input.json")
    shipped_mif = load(GAME / "data" / "motion_input_foe.json")
    shipped_cm = load(GAME / "data" / "card_motion.json")
    legacy_mi = load(P4 / "orig" / "pre-p4" / "motion_input.json")
    legacy_mif = load(P4 / "orig" / "pre-p4" / "motion_input_foe.json")
    legacy_cm = load(P4 / "orig" / "pre-p4" / "card_motion.json")
    want_2d = marker_2d_of(shipped_cm)
    p3_2d = marker_2d_of(legacy_cm)
    want_mp = marker_of(shipped_mi, "focus", 8)
    want_mf = marker_of(shipped_mif, "focus", 8)
    p3_mp = marker_of(legacy_mi, "focus", 8)
    p3_mf = marker_of(legacy_mif, "focus", 8)

    base = {"CARD_BOXER_TAIKOU_BOT": "1", "P4_LIVE_SEED": SEED}
    cases = [
        ("three_d", dict(base, CARD_BOXER_3D="1",
                         P4_LIVE_OUT=str(SHOTS / "three_d"))),
        ("default_off", dict(base, P4_LIVE_OUT=str(SHOTS / "default_off"))),
    ]
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        want = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        cases = [c for c in cases if c[0] == want]
        if not cases:
            print("UNKNOWN_ONLY", want)
            return 1

    # 跑前精确清掉本 tag 目录里的旧 PNG；不递归删目录，避免把上一局
    # 的帧误当成当前局（B 路线第一次试跑踩过这个）。
    for tag, _extra in cases:
        p = SHOTS / tag
        p.mkdir(parents=True, exist_ok=True)
        for old in sorted(p.glob("*.png")):
            old.unlink()

    runs: dict[str, dict] = {}
    for tag, extra in cases:
        runs[tag] = run_godot(tag, extra)
        print("RUN", tag, "rc", runs[tag]["rc"],
              "seconds", runs[tag]["seconds"],
              "rows", len(runs[tag]["payload"].get("rows", [])),
              "end", runs[tag]["payload"].get("end_reason"), flush=True)

    after = sha_tree()
    sha_unchanged = {rel: before[rel]["sha256"] == after[rel]["sha256"]
                     for rel in before}

    # ── 逐行表标记 / delta 对账（缓存公式结果）──
    cache: dict[tuple, dict] = {}

    def exp(card: str, frame: int) -> dict:
        k = (card, frame)
        if k not in cache:
            cache[k] = expected_delta(card, frame, "shipped")
        return cache[k]

    marker_bad, delta_bad = [], []
    for tag in runs:
        p = runs[tag]["payload"]
        if tag != "three_d":
            continue
        for r in p.get("rows", []):
            for side, mi in (("player", shipped_mi), ("foe", shipped_mif)):
                st = r.get(side, {})
                card, frame = str(st.get("card", "")), int(st.get("frame", -1))
                want = marker_of(mi, card, frame)
                if r.get(f"marker_{'player' if side == 'player' else 'foe'}") != want:
                    marker_bad.append((r["idx"], side, "marker"))
                got = st.get("delta", {})
                exp_d = exp(card, frame)
                if not exp_d or not got:
                    delta_bad.append((r["idx"], side, "missing"))
                    continue
                worst = max(abs(float(got.get(k, 1e9)) - exp_d[k])
                            for k in exp_d)
                if worst > 1e-3:
                    delta_bad.append((r["idx"], side, round(worst, 5)))

    checks: dict[str, bool] = {}
    seqs, pngs, svs = {}, {}, {}
    for tag in runs:
        p = runs[tag]["payload"]
        rows = p.get("rows", [])
        seqs[tag] = phase_sequence(p)
        pngs[tag] = png_stats(p, "live")
        svs[tag] = png_stats(p, "player_sv")
        is3 = (tag == "three_d")
        checks[f"{tag}_marker_parsed"] = (
            "error" not in p and len(rows) >= 50)
        checks[f"{tag}_rc_and_no_script_errors"] = (
            runs[tag]["rc"] == 0 and runs[tag]["script_errors"] == 0)
        checks[f"{tag}_no_scenario_errors"] = (
            runs[tag]["scenario_errors"] == 0)
        checks[f"{tag}_round_over_not_timeout"] = (
            p.get("end_reason") == "round_over")
        checks[f"{tag}_tk_bot_true"] = p.get("tk_bot") is True
        checks[f"{tag}_use_3d_matches_tag"] = (
            p.get("use_3d") is is3)
        checks[f"{tag}_paused_never_true"] = (
            p.get("paused_violations") == 0
            and all(r.get("paused_live") is False for r in rows))
        checks[f"{tag}_three_turns"] = (
            set(seqs[tag].keys()) == {"1", "2", "3"})
        checks[f"{tag}_phase_order_per_turn"] = all(
            tuple(v) == PHASE_ORDER for v in seqs[tag].values())
        checks[f"{tag}_final_round_phase_over"] = (
            p.get("final_round_phase") in ("over", "match_over"))
        checks[f"{tag}_seed_matches"] = p.get("seed") == int(SEED)
        checks[f"{tag}_marker_2d_is_shipped"] = (
            p.get("marker_2d") == want_2d)
        checks[f"{tag}_cards_2d_positive"] = (
            p.get("cards_2d", 0) > 0 and p.get("frames_2d", 0) > 0)
        checks[f"{tag}_live_pngs_all_nonzero"] = (
            pngs[tag]["total"] > 0
            and pngs[tag]["total"] == pngs[tag]["nonempty"])
        checks[f"{tag}_live_pngs_all_unique"] = (
            pngs[tag]["total"] > 0
            and pngs[tag]["total"] == pngs[tag]["unique_sha"])
        checks[f"{tag}_live_png_saves_ok"] = all(
            r.get("live_error", -1) == 0 for r in rows if r.get("live"))
        if is3:
            checks["three_d_15_cards_both"] = (
                p.get("cards_player") == 15 and p.get("cards_foe") == 15)
            checks["three_d_cap_mode_readback"] = (
                p.get("cap_readback") == 12.0
                and p.get("mode_readback") == "atan"
                and all(r.get("cap_live") == "12.0000"
                        and r.get("mode_live") == "atan" for r in rows))
            checks["three_d_marker_3d_is_shipped_both"] = (
                p.get("marker_3d_player") == want_mp
                and p.get("marker_3d_foe") == want_mf)
            checks["three_d_marker_3d_differs_from_p3_both"] = (
                want_mp != p3_mp and want_mf != p3_mf
                and p.get("marker_3d_player") == want_mp
                and p.get("marker_3d_foe") == want_mf)
            checks["three_d_all_rows_marker_match_shipped"] = not marker_bad
            checks["three_d_all_rows_delta_match_python"] = not delta_bad
            checks["three_d_frames_applied_growing"] = all(
                b["player"]["frames_applied"]
                > a["player"]["frames_applied"]
                for a, b in zip(rows, rows[1:]))
            checks["three_d_sv_pngs_all_nonzero"] = (
                svs[tag]["total"] > 0
                and svs[tag]["total"] == svs[tag]["nonempty"])
            checks["three_d_action_rows_have_sv"] = all(
                bool(r.get("player_sv")) and bool(r.get("foe_sv"))
                for r in rows if r.get("tk_phase") in ("reveal", "resolve"))

    checks["marker_2d_differs_from_p3"] = want_2d != p3_2d
    checks["no_monitored_game_file_modified"] = all(sha_unchanged.values())
    checks["two_independent_processes"] = len(runs) == 2

    report = {
        "cases": {tag: {"extra": r["extra"], "rc": r["rc"],
                        "seconds": r["seconds"],
                        "script_errors": r["script_errors"],
                        "scenario_errors": r["scenario_errors"],
                        "payload": r["payload"]}
                  for tag, r in runs.items()},
        "phase_sequences": seqs,
        "png_stats": {"live": pngs, "player_sv": svs},
        "table_markers": {
            "want_2d_shipped": want_2d, "p3_2d": p3_2d,
            "want_3d_player": want_mp, "want_3d_foe": want_mf,
            "p3_3d_player": p3_mp, "p3_3d_foe": p3_mf,
        },
        "marker_mismatches": marker_bad,
        "delta_mismatches": delta_bad,
        "sha_unchanged": sha_unchanged,
        "sha_before": before, "sha_after": after,
        "preconditions": {
            "framewise_pixel_ab_applicable": False,
            "note": ("跨 Godot 进程整局 RNG 漂移（B 路线实测三种牌局指纹），"
                     "两次真跑各自统计，不做跨进程逐帧像素 A/B；"
                     "P3/P4 对照用同源帧序列的 Python 公式复算。"),
        },
        "sample_s": 0.12, "seed": int(SEED),
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for tag in runs:
        p = runs[tag]["payload"]
        print("SEQ", tag, seqs[tag])
        print("END", tag, p.get("end_reason"), "t", p.get("total_t"),
              "hp", p.get("final_hp"), "wins", p.get("final_wins"))
        print("PNG", tag, pngs[tag], "SV", svs[tag])
    print("MARKER_MISMATCHES", len(marker_bad),
          "DELTA_MISMATCHES", len(delta_bad))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("LIVE_P4_OK" if report["ok"] else "LIVE_P4_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
