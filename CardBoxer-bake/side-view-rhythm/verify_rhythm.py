"""KOF 式节奏接线 · 承重判据（20 条）。

四层证据：
  1) 变更范围（pre-side-rhythm 基线 + 生成物逐字节复现）
  2) 参数单一真相来源（离线 make_side_battle.py 的每个数字 ↔ JSON ↔ 生成的 GDScript）
  3) 判定零改动（apply_hit / 伤害公式 / 阶段时长 / 视觉字段只在 _draw 段）
  4) 引擎真实输出（12 套自检 + 8 张 GL 截帧日志 + 从 PNG 重算像素）

只钉可复算事实，不评好看；看图结论单写在验证记录里。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
BACKUP = BAKE / "orig" / "pre-side-rhythm"
OFFLINE = BAKE / "side-view-battle-demo" / "make_side_battle.py"
OFFLINE_MANIFEST = BAKE / "side-view-battle-demo" / "side-view-combat-file-list.txt"
SPEC = HERE / "battle_rhythm_spec.json"
MOTION_SPEC = BAKE / "combat-motion-design" / "battle_motion_spec.json"
GENERATED = GAME / "scripts" / "battle_rhythm.gd"
ARENA = GAME / "scripts" / "arena.gd"
FIGHTER = GAME / "scripts" / "fighter.gd"
RESULT = HERE / "verify_rhythm_result.json"
FINGERPRINT = HERE / "source-fingerprints.json"

HIT_LABEL_BOX = (630, 285, 790, 340)
FRAMES = {
    "t048": "rhythm-frame-t048-impact-HIT.png",
    "t180": "rhythm-frame-t180-reset.png",
}

# (标签, 离线源码里的锚点子串, 提取正则, JSON constants 键列表)
NUM_PAIRS = [
    ("press_px", "int(110 * pulse)", r"int\((\d+) \* pulse\)", ["press_px"]),
    ("press_shape", "abs(t - 0.45) / 0.30",
     r"abs\(t - ([\d.]+)\) / ([\d.]+)", ["press_center", "press_half_width"]),
    ("knock", "int(40 * max(0.0, 1 - t * 1.7))",
     r"int\((\d+) \* max\(0\.0, 1 - t \* ([\d.]+)\)\)", ["knock_px", "knock_decay"]),
    ("tilt_deg", "tilt = (9 if side", r"tilt = \((\d+) if side", ["tilt_deg"]),
    ("tilt_decay", "1 - t * 1.4)", r"1 - t \* ([\d.]+)\)", ["tilt_decay"]),
    ("shake_x", "3 * math.sin(f * 2.7)",
     r"(\d+) \* math\.sin\(f \* ([\d.]+)\)", ["shake_amp_px", "shake_freq_x_per_frame"]),
    ("shake_y", "3 * math.sin(f * 4.1)",
     r"(\d+) \* math\.sin\(f \* ([\d.]+)\)", ["shake_amp_px", "shake_freq_y_per_frame"]),
    ("flash_frames", "flash = 0.8 if f < ATTACK[0] + 3",
     r"ATTACK\[0\] \+ (\d+)", ["flash_first_frames"]),
    ("spark_core", "cx - 11, cy - 11", r"cx - (\d+),", ["spark_core_px"]),
    ("spark_rays", "for k in range(12)", r"range\((\d+)\)", ["spark_rays"]),
    ("spark_phase", "k / 12 + 0.22", r"\+ ([\d.]+)", ["spark_ray_phase"]),
    ("spark_radius", "r = 14 + 30 * t",
     r"r = (\d+) \+ (\d+) \* t", ["spark_radius_base_px", "spark_radius_growth_px"]),
    ("spark_inner", "r0, r1 = r * 0.42, r + 18",
     r"r \* ([\d.]+), r \+ (\d+)", ["spark_ray_inner_ratio", "spark_ray_ext_px"]),
    ("spark_alpha", "a = int(250 * max(0.0, 1 - t * 1.25))",
     r"int\((\d+) \* max\(0\.0, 1 - t \* ([\d.]+)\)\)",
     ["spark_alpha", "spark_alpha_decay"]),
    ("spark_width", "width=3 if k % 3 == 0 else 2",
     r"width=(\d+) if k % 3 == 0 else (\d+)",
     ["spark_ray_width_main", "spark_ray_width_sub"]),
    ("spark_tail", "if f <= HIT_FRAME + 3", r"HIT_FRAME \+ (\d+)", ["spark_tail_frames"]),
    ("speed_lines", "for k in range(4)", r"range\((\d+)\)", ["speed_line_count"]),
    ("speed_alpha", "a = int(84 * max(0.0, 1 - t * 2.0))",
     r"int\((\d+) \* max\(0\.0, 1 - t \* ([\d.]+)\)\)",
     ["speed_line_alpha", "speed_line_decay"]),
    ("speed_cutoff", "if t > 0.42", r"t > ([\d.]+)", ["speed_line_cutoff"]),
    ("speed_len", "length = 16 + 18 *",
     r"length = (\d+) \+ (\d+) \*", ["speed_line_len_base", "speed_line_len_amp"]),
    ("speed_phase", "t * 2.0 + k * 0.08", r"\+ k \* ([\d.]+)", ["speed_line_phase_step"]),
    ("speed_y_step", "y = 216 + k * 30", r"\+ k \* (\d+)", ["speed_line_y_step"]),
    ("speed_dy", "y - 2 * direction", r"y - (\d+) \* direction", ["speed_line_dy"]),
]

TIMING_PAIRS = [
    ("frame_ms", 'script["frame_ms"] == 80',
     r'script\["frame_ms"\] == (\d+)', "frame_ms"),
    ("attack", "ATTACK = (21, 35)", r"ATTACK = \((\d+), (\d+)\)", "attack_span"),
    ("settle", "SETTLE = (35, 42)", r"SETTLE = \((\d+), (\d+)\)", "settle_span"),
    ("hit_frame", "HIT_FRAME = 27", r"HIT_FRAME = (\d+)", "hit_offset"),
    ("hitstop", "HITSTOP = (28, 29)", r"HITSTOP = \((\d+), (\d+)\)", "hitstop_offsets"),
]

checks: list[dict] = []


def check(name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print("[%s] %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def diff_px(a, b, box, threshold=18):
    d = ImageChops.difference(a.crop(box).convert("RGB"),
                              b.crop(box).convert("RGB")).convert("L")
    return sum(d.histogram()[threshold + 1:])


def real_code_lines(src, form):
    """只认真实代码行：注释行、以及 form 之前已被 # 注释掉的一律不算。

    变异 M20 曾把 hitstop 分支里的 _maybe_capture() 换成 pass 却没报红，
    因为同分支的注释里也写着这个词。裸子串 / 裸 count 会假绿。
    """
    return [ln for ln in src.splitlines()
            if form in ln and not ln.lstrip().startswith("#")
            and "#" not in ln[:ln.index(form)]]


def main() -> int:
    spec = jload(SPEC)
    const, timing = spec["constants"], spec["timing"]
    baseline = jload(HERE / "backup-fingerprints.json")
    all_checks = jload(HERE / "all_checks.json")
    capture = jload(HERE / "capture_result.json")
    evidence = jload(HERE / "evidence_rhythm.json")
    offline = OFFLINE.read_text(encoding="utf-8")
    arena_src = ARENA.read_bytes().decode("utf-8")
    fighter_src = FIGHTER.read_bytes().decode("utf-8")
    backup_arena = (BACKUP / "arena.gd").read_bytes().decode("utf-8")
    backup_fighter = (BACKUP / "fighter.gd").read_bytes().decode("utf-8")

    # ── 1. 变更范围 ──────────────────────────────────────────
    path_map = {
        "scripts/hud.gd": GAME / "scripts" / "hud.gd",
        "scripts/fx_layer.gd": GAME / "scripts" / "fx_layer.gd",
        "scripts/fighter_skin.gd": GAME / "scripts" / "fighter_skin.gd",
        "scripts/card_data.gd": GAME / "scripts" / "card_data.gd",
        "scripts/card_motion.gd": GAME / "scripts" / "card_motion.gd",
        "scripts/taikou_rules.gd": GAME / "scripts" / "taikou_rules.gd",
        "scripts/taikou_rage.gd": GAME / "scripts" / "taikou_rage.gd",
        "scripts/taikou_ai.gd": GAME / "scripts" / "taikou_ai.gd",
        "scripts/battle_motion_p0.gd": GAME / "scripts" / "battle_motion_p0.gd",
        "scripts/combo_check.gd": GAME / "scripts" / "combo_check.gd",
        "tests/battle_motion_p0_check.gd": GAME / "tests" / "battle_motion_p0_check.gd",
        "tests/taikou_flow_check.gd": GAME / "tests" / "taikou_flow_check.gd",
        "project.godot": GAME / "project.godot",
    }
    for rel in ["scripts/arena.gd", "scripts/fighter.gd"]:
        path_map[rel] = GAME / rel
    untouched = [rel for rel in baseline if rel not in
                 ("scripts/arena.gd", "scripts/fighter.gd")]
    identical = all(sha(BACKUP / Path(baseline[rel]["backup_file"]).name)
                    == sha(path_map[rel]) for rel in untouched)
    hashes_ok = all(
        sha(BACKUP / baseline[rel]["backup_file"]) == baseline[rel]["sha256"]
        for rel in baseline)
    check("R01_backup_manifest_intact",
          len(baseline) == 15 and hashes_ok,
          "files=%d hashes_match=%s" % (len(baseline), hashes_ok))
    check("R02_thirteen_untouched_files_byte_identical",
          identical and len(untouched) == 13,
          "checked=%d identical=%s" % (len(untouched), identical))
    changed = {rel for rel in ("scripts/arena.gd", "scripts/fighter.gd")
               if sha(BACKUP / Path(baseline[rel]["backup_file"]).name)
               != sha(path_map[rel])}
    check("R03_exactly_two_existing_files_changed",
          changed == {"scripts/arena.gd", "scripts/fighter.gd"},
          "changed=%s" % sorted(changed))
    new_gd = GAME / "scripts" / "battle_rhythm.gd"
    new_check = GAME / "tests" / "battle_rhythm_check.gd"
    check("R04_two_new_sources_present",
          new_gd.is_file() and new_check.is_file()
          and new_gd.stat().st_size > 2000 and new_check.stat().st_size > 5000
          and not (BACKUP / "battle_rhythm.gd").exists(),
          "gd=%dB check=%dB" % (new_gd.stat().st_size, new_check.stat().st_size))

    # ── 2. 参数单一真相来源 ───────────────────────────────────
    sys.path.insert(0, str(HERE))
    import gen_rhythm_gd
    regenerated = gen_rhythm_gd.build()
    check("R05_generated_gd_reproducible_from_json",
          regenerated == new_gd.read_bytes().decode("utf-8"),
          "bytes=%d identical=%s" % (len(regenerated.encode("utf-8")),
                                     regenerated == new_gd.read_bytes().decode("utf-8")))
    ms = jload(MOTION_SPEC)["constants"]["resolve_seconds"]
    check("R06_timeline_self_consistent",
          abs(timing["attack_s"] + timing["settle_s"] + timing["recover_s"]
              - timing["total_s"]) < 1e-9
          and abs(timing["total_s"] - ms) < 1e-9
          and abs(timing["hit_at_s"] - 6 * timing["frame_s"]) < 1e-9
          and abs(timing["hitstop_s"] - 3 * timing["frame_s"]) < 1e-9
          and timing["frame_s"] == timing["frame_ms"] / 1000.0,
          "resolve_seconds=%s total_s=%s" % (ms, timing["total_s"]))

    mismatches, matched = [], 0
    for label, needle, pattern, keys in NUM_PAIRS:
        line = next((ln for ln in offline.splitlines() if needle in ln), None)
        if line is None:
            mismatches.append("%s:anchor_missing" % label)
            continue
        m = re.search(pattern, line)
        if not m or len(m.groups()) != len(keys):
            mismatches.append("%s:regex_miss" % label)
            continue
        for got, key in zip(m.groups(), keys):
            if abs(float(got) - float(const[key])) > 1e-9:
                mismatches.append("%s:%s=%s_vs_%s" % (label, key, got, const[key]))
            else:
                matched += 1
    check("R07_offline_numbers_match_json", not mismatches and matched >= 24,
          "matched=%d mismatches=%s" % (matched, mismatches[:5]))

    timing_bad = []
    for label, needle, pattern, kind in TIMING_PAIRS:
        line = next((ln for ln in offline.splitlines() if needle in ln), None)
        m = re.search(pattern, line) if line else None
        if not m:
            timing_bad.append(label + ":miss")
            continue
        g = [int(x) for x in m.groups()]
        if kind == "frame_ms" and g[0] != timing["frame_ms"]:
            timing_bad.append(label)
        elif kind == "attack_span" and g[1] - g[0] != timing["offline_attack_frames"]:
            timing_bad.append(label)
        elif kind == "settle_span" and g[1] - g[0] != timing["offline_settle_frames"]:
            timing_bad.append(label)
        elif kind == "hit_offset" and g[0] - 21 != timing["offline_hit_frame_offset"]:
            timing_bad.append(label)
        elif kind == "hitstop_offsets" and [x - 21 for x in g] != timing["offline_hitstop_offsets"]:
            timing_bad.append(label)
    check("R08_offline_timeline_matches_json",
          not timing_bad and '"HIT!"' in offline
          and const["hitstop_label"] == "HIT!",
          "bad=%s hitstop_label=%s" % (timing_bad, const["hitstop_label"]))

    manifest_sha = None
    for ln in OFFLINE_MANIFEST.read_text(encoding="utf-8").splitlines():
        if ln.startswith("make_side_battle.py |"):
            manifest_sha = ln.split("|")[-1].strip()
    check("R09_offline_script_not_modified_by_this_round",
          manifest_sha is not None and sha(OFFLINE) == manifest_sha,
          "manifest=%s disk=%s" % (manifest_sha, sha(OFFLINE)))

    # ── 3. 判定零改动 ────────────────────────────────────────
    def func_body(src, name, next_name):
        i, j = src.find(name), src.find(next_name)
        return src[i:j] if i >= 0 and j > i else ""
    apply_before = func_body(backup_fighter, "func apply_hit(", "func _check_ko()")
    apply_after = func_body(fighter_src, "func apply_hit(", "func _check_ko()")
    check("R10_apply_hit_body_untouched",
          apply_before and apply_before == apply_after,
          "bytes=%d identical=%s" % (len(apply_after), apply_before == apply_after))

    verdict_lines = lambda s: [ln.strip() for ln in s.splitlines()
                               if "apply_hit(" in ln or "Rules.damage_of(" in ln
                               or "tk_phase_time >=" in ln or "TK_MAX_TURNS :=" in ln
                               or "tk_damage = 3" in ln]
    check("R11_damage_and_phase_lines_untouched",
          verdict_lines(backup_arena) == verdict_lines(arena_src)
          and len(verdict_lines(arena_src)) >= 8,
          "lines=%d identical=%s" % (len(verdict_lines(arena_src)),
                                     verdict_lines(backup_arena) == verdict_lines(arena_src)))

    draw_at = fighter_src.find("func _draw() -> void:")
    pose_at = fighter_src.find("func _build_pose()")
    limb_at = fighter_src.find("func _draw_limb(")
    draw_zone = (draw_at, limb_at)
    visual_clean = True
    for word in ["visual_shift", "visual_tilt"]:
        positions = [m.start() for m in re.finditer(word, fighter_src)]
        if len(positions) < 2:
            visual_clean = False
            continue
        # 声明（第一处）允许在 _draw 之前；其余必须全在 _draw.._draw_limb 段内
        if any(not (draw_zone[0] <= p < draw_zone[1]) for p in positions[1:]):
            visual_clean = False
    check("R12_visual_fields_only_in_draw_zone",
          visual_clean and draw_at > 0 and pose_at > draw_at
          and "draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)" in fighter_src,
          "draw_zone=%s pose_after_draw=%s" % (draw_zone, pose_at > draw_at))

    wired = [
        'const Rhythm = preload("res://scripts/battle_rhythm.gd")',
        "func _tick_rhythm(dt: float) -> void:",
        "func _apply_rhythm_visuals() -> void:",
        "func _clear_rhythm_visuals() -> void:",
        "func _draw_rhythm_fx(canvas: CanvasItem) -> void:",
        "_tick_rhythm(dt)", "_apply_rhythm_visuals()",
        "_draw_rhythm_fx(canvas)",
        "tk_rhythm_t = 0.0", "tk_rhythm_t = -1.0",
        "Rhythm.press_px(t) * dir * fade",
        "Rhythm.knock_px(t) * dir + shake_x",
        "Rhythm.tilt_rad(t) * dir * fade",
        "Rhythm.speed_active(tk_rhythm_t)",
        "Rhythm.spark_active(tk_rhythm_t)",
        "Rhythm.hit_label_active(tk_rhythm_t)",
    ]
    missing = [s for s in wired if not real_code_lines(arena_src, s)]
    check("R13_rhythm_wiring_forms_all_present",
          not missing, "checked=%d missing=%s" % (len(wired), missing))

    hitstop_branch = arena_src[arena_src.find("if _global_hitstop > 0.0:"):
                               arena_src.find("var dt := delta")]
    capture_lines = real_code_lines(hitstop_branch, "_maybe_capture()")
    check("R14_hitstop_branch_allows_capture",
          len(capture_lines) == 1
          and capture_lines[0].strip() == "_maybe_capture()"
          and "_tick_taikou" not in hitstop_branch,
          "real_capture_calls=%d branch_bytes=%d" % (
              len(capture_lines), len(hitstop_branch)))
    check("R15_draw_does_not_start_rhythm",
          'if tk_winner == "draw":' in arena_src
          and 'tk_rhythm_t = -1.0\n\t\ttk_rhythm_winner = ""' in arena_src,
          "draw_guard_present=%s" % ('if tk_winner == "draw":' in arena_src))

    # ── 4. 引擎真实输出 ──────────────────────────────────────
    recs = all_checks["checks"]
    rhythm_rec = next((r for r in recs if r["check"] == "tests/battle_rhythm_check.gd"), {})
    check("R16_twelve_engine_checks_green",
          all_checks["result"] == "ALL GREEN" and all_checks["total"] == 12
          and len(recs) == 12 and all(r["ok"] and r["rc"] == 0 for r in recs)
          and "62/62 passed" in rhythm_rec.get("summary", ""),
          "result=%s rhythm=%s" % (all_checks["result"], rhythm_rec.get("summary")))

    crecs = {r["mode"]: r for r in capture["records"]}
    expected_modes = set(FRAMES) | {"t000", "t072", "t112", "t140", "draw", "foewin"}
    marker_ok = all(m in crecs and crecs[m]["ok"] and crecs[m]["engine_errors"] == 0
                    and crecs[m]["gl"] and crecs[m]["marker"]
                    and ("mode=%s" % m) in crecs[m]["marker"][0]
                    for m in expected_modes)
    def val(mode, key):
        line = crecs[mode]["marker"][0] if mode in crecs and crecs[mode]["marker"] else ""
        m = re.search(r"%s=([-\d.]+)" % re.escape(key), line)
        return float(m.group(1)) if m else None
    nums_ok = (
        val("t000", "t") == 0.0 and val("t000", "p_shift") == 0.0
        and abs((val("t000", "e_shift") or 0) - 40.0) < 0.01
        and (val("t048", "p_shift") or 0) > 100.0
        and val("t180", "p_shift") == 0.0 and val("t180", "e_shift") == 0.0
        and val("t180", "p_tilt") == 0.0 and val("t180", "e_tilt") == 0.0
        and val("draw", "t") == -1.0 and val("draw", "p_shift") == 0.0
        and (val("foewin", "e_shift") or 0) < -100.0
        and (val("foewin", "p_tilt") or 0) < 0.0)
    check("R17_eight_engine_frames_and_state_numbers",
          capture["restore_ok"] and len(crecs) == 8 and marker_ok and nums_ok,
          "restore=%s modes=%d marker_ok=%s nums_ok=%s" % (
              capture["restore_ok"], len(crecs), marker_ok, nums_ok))

    a = Image.open(HERE / FRAMES["t048"]).convert("RGB")
    b = Image.open(HERE / FRAMES["t180"]).convert("RGB")
    recalc = diff_px(a, b, HIT_LABEL_BOX)
    ev_ok = (evidence["result"] == "EVIDENCE_RHYTHM_OK"
             and evidence["passed"] == evidence["total"] == 13
             and recalc == evidence["region_diffs"]["E02_hit_label_present"]["diff_px"])
    check("R18_pixel_evidence_recomputed_from_png", ev_ok,
          "recalc=%d json=%d" % (
              recalc, evidence["region_diffs"]["E02_hit_label_present"]["diff_px"]))

    # 节奏层的 P0 接线不能被顶掉。
    # 计数不写死：期望值从 post-P0 基线（pre-side-rhythm/arena.gd）独立复算，
    # 因为 REVEAL_CARD 本来就是双方各播一次 = 2 处真实调用。
    # 同时逐行排除注释里的同名词，避免「注释还在、调用没了」假绿。
    p0_forms = ["MotionP0.binding_for(winner_type)", "MotionP0.REVEAL_CARD",
                "enemy.apply_hit(tk_damage, \"taikou\", tk_motion_extra, false)",
                "player.apply_hit(3, \"taikou\", tk_motion_extra, false)"]

    p0_now = {s: arena_src.count(s) for s in p0_forms}
    p0_base = {s: backup_arena.count(s) for s in p0_forms}
    p0_real = {s: len(real_code_lines(arena_src, s)) for s in p0_forms}
    p0_ok = (p0_now == p0_base and all(v > 0 for v in p0_now.values())
             and p0_now == p0_real)
    check("R19_p0_wiring_not_regressed", p0_ok,
          json.dumps({"now": p0_now, "baseline": p0_base, "real_lines": p0_real},
                     ensure_ascii=False))

    fps = {}
    for rel in ["scripts/arena.gd", "scripts/fighter.gd", "scripts/battle_rhythm.gd",
                "scripts/hud.gd", "scripts/fx_layer.gd", "scripts/battle_motion_p0.gd",
                "scripts/taikou_rules.gd", "tests/battle_rhythm_check.gd",
                "tests/battle_motion_p0_check.gd", "project.godot"]:
        p = GAME / rel
        if p.is_file():
            fps[rel] = {"sha256": sha(p), "bytes": p.stat().st_size}
    FINGERPRINT.write_text(json.dumps(fps, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    check("R20_source_fingerprints_written",
          len(fps) == 10 and all(sha(GAME / rel) == fps[rel]["sha256"] for rel in fps),
          "files=%d" % len(fps))

    passed = sum(1 for c in checks if c["ok"])
    RESULT.write_text(json.dumps({
        "checks": checks, "passed": passed, "total": len(checks),
        "result": "RHYTHM_VERIFIED" if passed == len(checks) else "RHYTHM_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %d/%d %s" % (passed, len(checks),
                                "RHYTHM_VERIFIED" if passed == len(checks) else "RHYTHM_FAILED"))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
