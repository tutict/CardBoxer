"""动作覆盖 P1 · 汇总承重判据（只读盘，不重跑 Godot / Blender）。

六层，任一 FAIL 即退出码 1：
  A 落盘边界   —— 14 个受监控文件逐 sha 对账；4 个改动、10 个零改动；
                   arena 改动只在 _sync_3d_layer 区块、layer 只有两处 hunk
  B 数据层     —— 15 卡 / 284 帧逐帧与 card_motion.json 对账；原 3 卡逐值不变；
                   两份 cards 完全一致；独立复算 13 骨 delta 不超 mapping 上限
  C 接线层     —— 白名单数据驱动、亮牌/输家/平局分支、HIT_AT_S、显式 bool；
                   四档硬直表与 fighter.gd 同口径；REVEAL_S 与阶段时长同值
  D 报告自洽   —— 每份上游报告独立复核 checks 布尔与 failed 名单，不信 ok 字段
  E 引擎取证   —— 六态 card/frame、A/B PNG 逐字节、12 张 PNG sha、8 组像素差、
                   日志里的默认关零污染与 HP，全部从盘上原始素材重算
  F 交付物     —— 两张对照板、18 张截帧、探针脚本落进游戏工程

用法：python verify_motion_p1.py
产出：data/verify_motion_p1.json
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
DIAG = BAKE / "动作优化诊断"
D = HERE / "data"
ORIG = HERE / "orig" / "pre-p1"
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"
LOGS = HERE / "logs"
OUT = D / "verify_motion_p1.json"

sys.path.insert(0, str(DIAG))
from diag_motion import make_points, retarget_delta  # noqa: E402

BACKUP_MAP = {
    "scripts/arena.gd": "arena.gd",
    "scripts/fighter_3d_layer.gd": "fighter_3d_layer.gd",
    "data/motion_input.json": "motion_input.json",
    "data/motion_input_foe.json": "motion_input_foe.json",
}
EXISTING = ("jab", "cross", "wave")
MIN_DIFF_PX = 500
P1_MARKER = "# ── P1 动作覆盖"
SYNC_MARKER = "func _sync_3d_layer() -> void:"
EXPECT_BINDINGS = {
    "stance": ("stance", "stance"),
    "reveal": ("focus", "focus"),
    "player_win": ("wave", "hit_heavy"),
    "enemy_win": ("hit_heavy", "cross"),
    "draw": ("hit_light", "hit_light"),
    "legacy_player_win": ("wave", "stance"),
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def diff_px(a: Path, b: Path) -> int:
    if not (Path(a).is_file() and Path(b).is_file()):
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


def func_span(src: str, marker: str) -> tuple[int, int]:
    """返回函数体起止下标；终止点为下一个顶层 func 声明。"""
    start = src.index(marker)
    nxt = src.find("\nfunc ", start + len(marker))
    return start, (len(src) if nxt < 0 else nxt + 1)


def norm(s: str) -> str:
    """忽略缩进/空行的逐行比较（arena 的赢家攻击块被 elif 包了一层）。"""
    return "\n".join(ln.strip() for ln in s.splitlines() if ln.strip())


def arena_const(src: str, name: str) -> dict:
    m = re.search(r"const " + name + r" := \{(.*?)\}", src, re.S)
    if m is None:
        return {}
    return {k: float(v) for k, v in
            re.findall(r'"([a-z_]*)":\s*([0-9.]+)', m.group(1))}


def fighter_react_tables(fg: str) -> tuple[dict, dict]:
    """从 fighter.gd 的 apply_hit 正文里读出四档硬直时长/倾角，不写死数值。"""
    m = re.search(r"state = State\.HITSTUN(.*?)hit_confirmed\.emit", fg, re.S)
    if m is None:
        return {}, {}
    blk = m.group(1)
    d0 = re.search(r"_stun_duration = ([0-9.]+)", blk)
    t0 = re.search(r"_stun_tilt = ([0-9.]+) \*", blk)
    if d0 is None or t0 is None:
        return {}, {}
    dur = {"": float(d0.group(1))}
    tilt = {"": float(t0.group(1))}
    for extra in ("launch", "stagger", "super"):
        mm = re.search(r'(?:if|elif) extra == "' + extra
                       + r'":(.*?)(?=(?:elif extra == )|add_meter\(0\.6\))',
                       blk, re.S)
        if mm is None:
            return {}, {}
        dm = re.search(r"_stun_duration = ([0-9.]+)", mm.group(1))
        tm = re.search(r"_stun_tilt = ([0-9.]+) \*", mm.group(1))
        if dm is None or tm is None:
            return {}, {}
        dur[extra] = float(dm.group(1))
        tilt[extra] = float(tm.group(1))
    return dur, tilt


def report_ok(rep: dict) -> bool:
    """独立复核内部 checks 布尔；不信任上游的 ok 字段。"""
    ck = rep.get("checks")
    if not isinstance(ck, dict) or not ck:
        return False
    if not all(v is True for v in ck.values()):
        return False
    if rep.get("failed"):
        return False
    return rep.get("ok", True) is True


def main() -> int:
    baseline = load(D / "baseline.json")
    build = load(D / "build_motion_p1.json")
    ampl = load(D / "amplitude_scan.json")
    probe = load(D / "motion_p1_probe.json")
    all_checks = load(D / "all_checks_local.json")
    cm = load(GAME / "data" / "card_motion.json")
    mi = load(GAME / "data" / "motion_input.json")
    mif = load(GAME / "data" / "motion_input_foe.json")
    mi_bak = load(ORIG / "motion_input.json")
    mif_bak = load(ORIG / "motion_input_foe.json")
    arena = (GAME / "scripts" / "arena.gd").read_text(encoding="utf-8")
    arena_bak = (ORIG / "arena.gd").read_text(encoding="utf-8")
    layer = (GAME / "scripts" / "fighter_3d_layer.gd").read_text(
        encoding="utf-8")
    layer_bak = (ORIG / "fighter_3d_layer.gd").read_text(encoding="utf-8")
    fighter_src = (GAME / "scripts" / "fighter.gd").read_text(
        encoding="utf-8")
    p1_log = (LOGS / "godot_p1.log").read_text(encoding="utf-8",
                                              errors="replace")
    def_log = (LOGS / "godot_default.log").read_text(encoding="utf-8",
                                                    errors="replace")
    checks_out = (LOGS / "all_checks_p1.out").read_text(encoding="utf-8")

    src_tracks = {k: v["track"] for k, v in cm["cards"].items()}
    src_tracks.update({k: v["track"] for k, v in cm["motions"].items()})
    keys = list(mi["joint_names"])
    rows = {r["id"]: r for r in probe["rows"]}
    watched = baseline["files"]
    changed = set(BACKUP_MAP)
    untouched = [k for k in watched if k not in changed]

    # 源码分块：arena 改动必须夹在 _sync_3d_layer 区块内
    a_beg, a_end = func_span(arena, SYNC_MARKER)
    b_beg, b_end = func_span(arena_bak, SYNC_MARKER)
    arena_sync = arena[a_beg:a_end]
    arena_sync_bak = arena_bak[b_beg:b_end]
    attack_start = arena_sync_bak.index("\tif tk_rhythm_t >= 0.0")
    attack_end = arena_sync_bak.index("\tif layer_3d != null:")
    attack_block = arena_sync_bak[attack_start:attack_end]

    # apply() 函数体（只在函数体内扫白名单，避免兜底 stance 混进来）
    la_beg, la_end = func_span(layer, "func apply(card: String, frame: int) -> void:")
    apply_body = layer[la_beg:la_end]

    # layer diff 形状
    layer_ops = [o for o in difflib.SequenceMatcher(
        None, layer_bak.splitlines(), layer.splitlines(),
        autojunk=False).get_opcodes() if o[0] != "equal"]
    layer_diff = list(difflib.unified_diff(
        layer_bak.splitlines(), layer.splitlines(), n=0))
    removed = [x[1:] for x in layer_diff
               if x.startswith("-") and not x.startswith("---")]
    added = [x[1:] for x in layer_diff
             if x.startswith("+") and not x.startswith("+++")]

    # 独立复算 13 骨峰值（不信 amplitude_scan.json 的 ok）
    limits = {
        "hips": 0.0, "spine": float(mi["mapping"]["torso_cap_deg"]),
        "chest": 0.0, "neck": 0.0,
        "head": float(mi["mapping"]["torso_cap_deg"])
                * float(mi["mapping"]["head_compensation"]),
        "upperarm_f": float(mi["mapping"]["arm_gain_deg"]["f_upper"]),
        "forearm_f": float(mi["mapping"]["arm_gain_deg"]["f_fore"]),
        "upperarm_b": float(mi["mapping"]["arm_gain_deg"]["b_upper"]),
        "forearm_b": float(mi["mapping"]["arm_gain_deg"]["b_fore"]),
        "thigh_f": float(mi["mapping"]["leg_cap_deg"]),
        "shin_f": float(mi["mapping"]["leg_cap_deg"]),
        "thigh_b": float(mi["mapping"]["leg_cap_deg"]),
        "shin_b": float(mi["mapping"]["leg_cap_deg"]),
    }
    stance_j = {k: tuple(v) for k, v in mi["stance"].items()}
    stance_points = make_points(stance_j)
    recomputed_peaks = {}
    amplitude_bad = []
    bone_shape_ok = True
    for name, card in mi["cards"].items():
        peaks = {n: 0.0 for n in limits}
        for frame in card["track"]:
            fj = {k: tuple(frame[k]) for k in keys}
            delta, _raw = retarget_delta(fj, stance_j, mi["chain"],
                                         mi["mapping"], stance_points)
            if set(delta) != set(limits):
                bone_shape_ok = False
                continue
            for n, v in delta.items():
                peaks[n] = max(peaks[n], abs(v))
        recomputed_peaks[name] = round(max(peaks.values()), 3)
        for n, v in peaks.items():
            if v > limits[n] + 1e-6:
                amplitude_bad.append((name, n, round(v, 3), limits[n]))

    # 引擎原始素材重算
    sha_now = {}
    for rid, row in rows.items():
        for side in ("player", "foe"):
            sha_now[f"{rid}_{side}"] = sha256(Path(row[f"{side}_sv"]))
    diffs_now = {}
    for scene in ("reveal", "player_win", "enemy_win", "draw"):
        for side in ("player", "foe"):
            diffs_now[f"{scene}_{side}"] = diff_px(
                Path(rows[scene][f"{side}_sv"]),
                Path(rows["stance"][f"{side}_sv"]))
    p1_line = next((l for l in p1_log.splitlines()
                    if l.startswith("MOTION_P1_JSON ")), "")
    def_line = next((l for l in def_log.splitlines()
                     if l.startswith("DISPLAY_JSON ")), "")
    try:
        p1_payload = json.loads(p1_line[len("MOTION_P1_JSON "):])
    except (ValueError, TypeError):
        p1_payload = {}
    try:
        def_payload = json.loads(def_line[len("DISPLAY_JSON "):])
    except (ValueError, TypeError):
        def_payload = {}
    ok_lines = [l for l in checks_out.splitlines()
                if l.startswith("OK   ")]
    fail_lines = [l for l in checks_out.splitlines()
                  if l.startswith("FAIL ")]
    last_line = checks_out.strip().splitlines()[-1] if checks_out.strip() else ""

    checks: dict[str, bool] = {}
    errors: dict[str, str] = {}

    def add(name: str, fn) -> None:
        try:
            checks[name] = bool(fn())
        except Exception as exc:  # 缺文件 / 坏 JSON 也是 FAIL，不是崩栈
            checks[name] = False
            errors[name] = f"{type(exc).__name__}: {exc}"

    # ── A 落盘边界 ───────────────────────────────────────────
    add("baseline_internal_ok", lambda: (
        all(v is True for v in baseline["checks"].values())
        and baseline["ok"] is True
        and len(watched) == 14
        and all(len(v["sha256"]) == 64 for v in watched.values())))
    add("backups_match_baseline", lambda: all(
        sha256(ORIG / BACKUP_MAP[k]) == v["sha256"]
        for k, v in watched.items() if k in changed))
    add("four_targets_changed", lambda: all(
        sha256(GAME / k) != v["sha256"]
        for k, v in watched.items() if k in changed))
    add("ten_untouched_unchanged", lambda: all(
        sha256(GAME / k) == v["sha256"]
        for k in untouched for v in [watched[k]]))
    add("world3d_fix_preserved", lambda: (
        layer.count("sv.own_world_3d = true") == 1))
    add("arena_prefix_unchanged", lambda: (
        arena[:arena.index(P1_MARKER)] == arena_bak[:b_beg]))
    add("arena_suffix_unchanged", lambda: arena[a_end:] == arena_bak[b_end:])
    add("layer_only_two_hunks", lambda: (
        len(layer_ops) == 2
        and len(removed) == 2
        and len(added) == 4
        and all(a.lstrip().startswith("##") for a in added[:3])
        and added[3].strip()
        == 'if c != "stance" and not motion["cards"].has(c):'
        and removed[1].strip()
        == 'if c != "jab" and c != "cross" and c != "wave":'))
    add("winner_attack_block_verbatim", lambda: (
        norm(attack_block) in norm(arena_sync)))

    # ── B 数据层 ─────────────────────────────────────────────
    add("cards_total_fifteen_both", lambda: (
        len(mi["cards"]) == 15 and len(mif["cards"]) == 15))
    add("total_frames_284_both", lambda: all(
        sum(len(c["track"]) for c in m["cards"].values()) == 284
        for m in (mi, mif)))
    add("declared_frames_match_track_len_both", lambda: all(
        c["frames"] == len(c["track"])
        for m in (mi, mif) for c in m["cards"].values()))
    add("cards_names_equal_source_union_both", lambda: all(
        set(m["cards"]) == set(src_tracks)
        for m in (mi, mif)))
    add("original_three_unchanged_both", lambda: all(
        m["cards"][k] == b["cards"][k]
        for m, b in ((mi, mi_bak), (mif, mif_bak)) for k in EXISTING))
    add("non_cards_fields_equal_backup_both", lambda: all(
        all(m[k] == b[k] for k in b if k != "cards")
        for m, b in ((mi, mi_bak), (mif, mif_bak))))
    add("added_tracks_equal_source_both", lambda: all(
        m["cards"][name]["track"] ==
        [{k: list(f[k]) for k in keys} for f in track]
        for m in (mi, mif) for name, track in src_tracks.items()
        if name not in EXISTING))
    add("all_frames_have_11_joints_both", lambda: all(
        set(f.keys()) == set(keys)
        for m in (mi, mif) for c in m["cards"].values()
        for f in c["track"]))
    add("stance_not_in_cards_both", lambda: all(
        "stance" not in m["cards"] and "stance" in m
        for m in (mi, mif)))
    add("two_files_cards_identical", lambda: mi["cards"] == mif["cards"])
    add("two_files_stance_and_mapping_identical", lambda: (
        mi["stance"] == mif["stance"]
        and mi["mapping"] == mif["mapping"]
        and mi["chain"] == mif["chain"]))
    add("two_files_apose_points_differ", lambda: (
        mi["apose_points"] != mif["apose_points"]))
    add("mapping_gains_unchanged_both", lambda: (
        mi["mapping"] == mi_bak["mapping"]
        and mif["mapping"] == mif_bak["mapping"]))
    add("amplitude_within_limits_recomputed", lambda: (
        len(recomputed_peaks) == 15 and not amplitude_bad
        and bone_shape_ok))

    # ── C 接线层 ─────────────────────────────────────────────
    add("apply_is_data_driven", lambda: (
        'if c != "stance" and not motion["cards"].has(c):' in apply_body))
    add("apply_has_no_hardcoded_three", lambda: all(
        '"%s"' % k not in apply_body for k in EXISTING))
    add("apply_keeps_stance_fallback", lambda: (
        'c = "stance"' in apply_body
        and 'drv.apply_frame(c, f)' in apply_body))
    add("arena_reveal_branch_present", lambda: all(
        s in arena_sync for s in (
            'if tk_phase == "reveal" and has_focus:',
            'var ff := _3d_frame_of("focus", tk_phase_time / REVEAL_S)',
            'card = "focus"', 'foe_card = "focus"')))
    add("arena_loser_react_branch_present", lambda: all(
        s in arena_sync for s in (
            'elif tk_phase == "resolve":',
            'if has_react and tk_winner != "":',
            'foe_card = react', 'card = react')))
    # 注意 "card = react" 是 "foe_card = react" 的子串，必须逐行精确比
    add("arena_draw_both_react_assigned", lambda: (
        sum(ln.strip() == "foe_card = react"
            for ln in arena_sync.splitlines()) == 2
        and sum(ln.strip() == "card = react"
                for ln in arena_sync.splitlines()) == 2))
    add("arena_react_starts_at_hit_at", lambda: (
        'at = tk_rhythm_t - Rhythm.HIT_AT_S' in arena_sync
        and 'if tk_winner != "draw":' in arena_sync
        and 'REACT_DURATION_S.get(tk_motion_extra, 0.26)' in arena_sync))
    add("arena_explicit_bool_types", lambda: (
        "var has_focus: bool =" in arena_sync
        and "var has_react: bool =" in arena_sync))
    add("react_tables_match_fighter_gd", lambda: (
        bool(fighter_react_tables(fighter_src)[0])
        and arena_const(arena, "REACT_DURATION_S")
        == fighter_react_tables(fighter_src)[0]
        and arena_const(arena, "REACT_STUN_TILT")
        == fighter_react_tables(fighter_src)[1]))
    add("react_threshold_matches_fighter_gd", lambda: (
        float(re.search(r"absf\(_stun_tilt\) >=\s*([0-9.]+)",
                        fighter_src).group(1))
        == float(re.search(r"absf\(tilt\) >=\s*([0-9.]+)",
                           arena).group(1))))
    add("reveal_s_matches_tick_taikou", lambda: (
        float(re.search(r'const REVEAL_S := ([0-9.]+)', arena).group(1))
        == float(re.search(r'"reveal":\s*\n\s*if tk_phase_time >=\s*'
                           r'([0-9.]+):', arena).group(1))))
    add("no_invented_hit_crush_track", lambda: (
        "hit_crush" not in mi["cards"]
        and "hit_crush" not in mif["cards"]
        and "hit_crush" not in arena_sync))

    # ── D 上游报告自洽 ───────────────────────────────────────
    add("build_report_all_checks_true", lambda: (
        all(all(v is True for v in r["checks"].values())
            and r["ok"] is True for r in build["targets"].values())
        and all(v is True for v in build["cross_file"].values())
        and build["ok"] is True))
    add("amplitude_report_all_checks_true", lambda: report_ok(ampl))
    add("probe_report_all_checks_true", lambda: report_ok(probe)
        and len(probe["checks"]) == 25)
    add("all_checks_report_selfconsistent", lambda: (
        all_checks["tag"] == "motion_p1"
        and all_checks["total"] == 15
        and all_checks["result"] == "ALL GREEN"
        and all_checks["failed"] == []
        and len(all_checks["checks"]) == 15
        and all(r["ok"] is True and r["rc"] == 0
                for r in all_checks["checks"])))

    # ── E 引擎取证（从原始 PNG / 日志重算） ──────────────────
    add("probe_rows_six_and_bindings", lambda: (
        len(rows) == 6
        and all(rows[k]["player_card"] == v[0]
                and rows[k]["foe_card"] == v[1]
                for k, v in EXPECT_BINDINGS.items())
        and all(rows[k]["cards_at_scene"] == 15
                for k in EXPECT_BINDINGS if k != "legacy_player_win")
        and rows["legacy_player_win"]["cards_at_scene"] == 3
        and rows["stance"]["player_frame"] == 0
        and rows["stance"]["foe_frame"] == 0
        and all(rows[k][s + "_frame"] > 0
                for k in ("reveal", "player_win", "enemy_win", "draw")
                for s in ("player", "foe"))
        and rows["legacy_player_win"]["foe_frame"] == 0))
    add("winner_ab_png_bytewise_identical", lambda: (
        Path(rows["player_win"]["player_sv"]).is_file()
        and Path(rows["legacy_player_win"]["player_sv"]).is_file()
        and sha256(rows["player_win"]["player_sv"]) != ""
        and sha256(rows["player_win"]["player_sv"])
        == sha256(rows["legacy_player_win"]["player_sv"])))
    add("winner_ab_frame_equal", lambda: (
        rows["player_win"]["player_frame"]
        == rows["legacy_player_win"]["player_frame"]))
    add("legacy_loser_back_to_stance", lambda: (
        rows["legacy_player_win"]["foe_card"] == "stance"))
    add("sv_sha_recomputed_matches_report", lambda: (
        len(sha_now) == 12 and sha_now == probe["sv_sha256"]))
    add("diff_px_recomputed_matches_report", lambda: (
        len(diffs_now) == 8
        and diffs_now == probe["diff_px"]
        and all(v > MIN_DIFF_PX for v in diffs_now.values())))
    add("probe_log_no_errors", lambda: (
        "SCRIPT ERROR" not in p1_log and "Parse Error" not in p1_log
        and 'Parameter "scenario" is null' not in p1_log
        and "SCRIPT ERROR" not in def_log
        and "Parse Error" not in def_log))
    add("default_zero_pollution_from_log", lambda: (
        bool(def_payload)
        and def_payload["use_3d"] is False
        and def_payload["layer_3d"] is False
        and def_payload["layer_3d_foe"] is False
        and def_payload["player_override"] is False
        and def_payload["enemy_override"] is False
        and def_payload["env_3d"] == ""
        and len(list((SHOTS / "default").glob("*.png"))) == 2))
    # payload 在 6 场跑完后打印，最后一场是 legacy A/B：两份表已被裁回 3 卡。
    # 15 卡由每行 rows[i]["cards_at_scene"] 证明（probe_rows_six_and_bindings）。
    add("hp_and_overrides_from_log", lambda: (
        bool(p1_payload)
        and p1_payload["hp"] == [100, 100]
        and p1_payload["use_3d"] is True
        and p1_payload["player_override"] is True
        and p1_payload["enemy_override"] is True
        and p1_payload["cards_player"] == 3
        and p1_payload["cards_foe"] == 3))
    add("all_checks_out_15_15", lambda: (
        len(ok_lines) == 15 and not fail_lines
        and last_line == "ALL_CHECKS_LOCAL 15/15 ALL GREEN"))

    # ── F 交付物 ─────────────────────────────────────────────
    add("two_boards_present_and_sized", lambda: all(
        p.is_file() and p.stat().st_size > 50000
        and Image.open(p).size[0] >= 1000
        and Image.open(p).size[1] >= 500
        for p in (BOARDS / "动作覆盖-六态视口对照.png",
                  BOARDS / "动作覆盖-战斗帧对照.png")))
    add("board_sources_all_present", lambda: all(
        Path(rows[k][f"{s}_sv"]).is_file() and Path(rows[k]["live"]).is_file()
        for k in EXPECT_BINDINGS for s in ("player", "foe")))
    add("probe_script_shipped_bytewise", lambda: (
        (GAME / "tests" / "motion_p1_probe.gd").is_file()
        and (GAME / "tests" / "motion_p1_probe.gd").read_bytes()
        == (HERE / "tests" / "motion_p1_probe.gd").read_bytes()))

    failed = [k for k, v in checks.items() if not v]
    report = {
        "checks": checks, "failed": failed, "errors": errors,
        "total": len(checks), "passed": len(checks) - len(failed),
        "recomputed": {
            "sv_sha256": sha_now, "diff_px": diffs_now,
            "peak_abs_deg_by_track": recomputed_peaks,
            "amplitude_over_limit": amplitude_bad,
            "react_duration_s": arena_const(arena, "REACT_DURATION_S"),
            "react_stun_tilt": arena_const(arena, "REACT_STUN_TILT"),
            "fighter_gd_react_duration_s": fighter_react_tables(fighter_src)[0],
            "fighter_gd_react_stun_tilt": fighter_react_tables(fighter_src)[1],
            "layer_diff_opcodes": len(layer_ops),
            "cards": sorted(mi["cards"]),
            "total_frames": sum(len(c["track"])
                                for c in mi["cards"].values()),
        },
        "ok": not failed,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    for k in failed:
        print("FAIL", k, errors.get(k, ""))
    print(f"MOTION_P1_VERIFY {report['passed']}/{report['total']} "
          + ("ALL GREEN" if report["ok"] else "FAILED"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
