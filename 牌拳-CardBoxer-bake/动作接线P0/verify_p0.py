"""P0 动作接线 · 承重判据（18 条）。

只钉可复算事实，不评好看。四层证据：
  1) 跨工程规格对齐（battle_motion_spec.json <-> battle_motion_p0.gd）
  2) 源码接线形态（钉真实调用串，不钉注释里也会出现的词）
  3) 引擎内真实输出（11 套 Godot 自检 + 5 张 GL 截帧 + [TAIKOU] 日志）
  4) 像素取证重算（防止只信一份已经写好的 JSON）

与 战斗动作设计/verify_spec.py 的分工：后者评「规格层自洽」，
本文件评「规格有没有真的接进游戏」。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
BACKUP = BAKE / "orig" / "pre-motion-p0"
SPEC = BAKE / "战斗动作设计" / "battle_motion_spec.json"
BASELINE = BAKE / "战斗动作设计" / "源码基线.json"
MOTION_TABLE = GAME / "data" / "card_motion.json"

ARENA = GAME / "scripts" / "arena.gd"
HUD = GAME / "scripts" / "hud.gd"
P0 = GAME / "scripts" / "battle_motion_p0.gd"
P0_CHECK = GAME / "tests" / "battle_motion_p0_check.gd"

RESULT = HERE / "verify_p0_result.json"
FINGERPRINT = HERE / "源码指纹.json"

HINT_BOX = (44, 692, 1100, 720)
FRAME_FILES = {
    "reveal": "引擎帧-亮牌focus.png",
    "triple": "引擎帧-三同气功波.png",
    "sequence": "引擎帧-三连交叉反击.png",
    "scatter": "引擎帧-散牌刺拳.png",
    "draw": "引擎帧-平局对峙.png",
}

checks: list[dict] = []


def check(name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print("[%s] %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def diff_px(a: Image.Image, b: Image.Image, box, threshold=18) -> int:
    d = ImageChops.difference(a.crop(box).convert("RGB"),
                              b.crop(box).convert("RGB")).convert("L")
    return sum(d.histogram()[threshold + 1:])


def parse_bindings(src: str) -> dict:
    m = re.search(r"const BINDINGS := \{(.*?)\n\}", src, re.S)
    if not m:
        return {}
    out = {}
    for name, body in re.findall(r'"(\w+)":\s*\{(.*?)\}', m.group(1), re.S):
        out[name] = dict(re.findall(r'"(\w+)":\s*"([^"]*)"', body))
    return out


def main() -> int:
    spec, baseline = jload(SPEC), jload(BASELINE)
    all_checks = jload(HERE / "all_checks.json")
    capture = jload(HERE / "capture_result.json")
    evidence = jload(HERE / "evidence_p0.json")
    arena_src = ARENA.read_bytes().decode("utf-8")
    hud_src = HUD.read_bytes().decode("utf-8")
    p0_src = P0.read_bytes().decode("utf-8")
    table = jload(MOTION_TABLE)

    # ── 1. 变更范围 ──────────────────────────────────────────
    expected_backup = {
        "arena.gd", "card_data.gd", "card_motion.gd", "fighter.gd", "hud.gd",
        "project.godot", "run_all_checks.py", "taikou_flow_check.gd",
        "taikou_rage.gd", "taikou_rules.gd",
    }
    got_backup = {p.name for p in BACKUP.iterdir() if p.is_file()}
    rel_of = {
        "arena.gd": "scripts/arena.gd", "card_data.gd": "scripts/card_data.gd",
        "card_motion.gd": "scripts/card_motion.gd", "fighter.gd": "scripts/fighter.gd",
        "taikou_rules.gd": "scripts/taikou_rules.gd",
        "taikou_rage.gd": "scripts/taikou_rage.gd",
    }
    baseline_ok = all(
        sha(BACKUP / fn) == baseline["files"][rel]["sha256"]
        for fn, rel in rel_of.items() if rel in baseline["files"]
    )
    check("V01_backup_matches_pre_wiring_baseline",
          got_backup == expected_backup and baseline_ok,
          "backup=%d files baseline_match=%s" % (len(got_backup), baseline_ok))

    untouched = [fn for fn in sorted(expected_backup)
                 if fn not in ("arena.gd", "hud.gd")]
    # 显式路径映射，避免猜目录：taikou_flow_check.gd 在 tests/ 不在 scripts/
    path_map = {
        "card_data.gd": GAME / "scripts" / "card_data.gd",
        "card_motion.gd": GAME / "scripts" / "card_motion.gd",
        "fighter.gd": GAME / "scripts" / "fighter.gd",
        "taikou_flow_check.gd": GAME / "tests" / "taikou_flow_check.gd",
        "taikou_rage.gd": GAME / "scripts" / "taikou_rage.gd",
        "taikou_rules.gd": GAME / "scripts" / "taikou_rules.gd",
        "project.godot": GAME / "project.godot",
        "run_all_checks.py": BAKE / "外观层" / "run_all_checks.py",
    }
    unchanged = all(sha(BACKUP / fn) == sha(path_map[fn])
                    for fn in untouched if fn in path_map)
    check("V02_untouched_sources_byte_identical", unchanged and len(untouched) == 8,
          "checked=%d identical=%s" % (len(untouched), unchanged))

    changed = {fn for fn in ("arena.gd", "hud.gd")
               if sha(BACKUP / fn) != sha(path_map.get(fn, GAME / "scripts" / fn))}
    check("V03_exactly_two_existing_files_changed", changed == {"arena.gd", "hud.gd"},
          "changed=%s" % sorted(changed))

    new_ok = (P0.is_file() and P0_CHECK.is_file()
              and P0.stat().st_size > 1000 and P0_CHECK.stat().st_size > 1000
              and not (BACKUP / "battle_motion_p0.gd").exists()
              and not (BACKUP / "battle_motion_p0_check.gd").exists())
    check("V04_two_new_sources_present", new_ok,
          "p0=%dB check=%dB" % (P0.stat().st_size, P0_CHECK.stat().st_size))

    # ── 2. 规格 ↔ 接线常量 ───────────────────────────────────
    bindings = parse_bindings(p0_src)
    cbind = spec["card_type_binding"]
    wc_ok = all(bindings.get(t, {}).get("winner_card") == cbind[t]["winner_card"]
                for t in ("triple", "sequence", "scatter"))
    check("V05_spec_winner_card_matches_bindings", wc_ok,
          json.dumps({t: bindings.get(t, {}).get("winner_card") for t in cbind},
                     ensure_ascii=False))

    react_ok = all(
        bindings.get(t, {}).get("react") == cbind[t]["loser_react"]
        and bindings.get(t, {}).get("extra") == cbind[t]["damage_extra"]
        for t in ("triple", "sequence", "scatter"))
    check("V06_spec_react_and_extra_match_bindings", react_ok,
          json.dumps({t: [bindings.get(t, {}).get("react"), bindings.get(t, {}).get("extra")]
                      for t in cbind}, ensure_ascii=False))

    tiers = spec["damage_tiers"]
    tier_ok = all(
        tiers[t]["react"] == bindings[t]["react"]
        and tiers[t]["extra"] == bindings[t]["extra"]
        for t in ("triple", "sequence", "scatter"))
    draw_m = re.search(r'const DRAW := \{(.*?)\}', p0_src, re.S)
    draw = dict(re.findall(r'"(\w+)":\s*"([^"]*)"', draw_m.group(1))) if draw_m else {}
    tier_ok = tier_ok and draw.get("react") == tiers["draw"]["react"] \
        and draw.get("extra") == tiers["draw"]["extra"]
    check("V07_damage_tiers_match_bindings_and_draw", tier_ok,
          "tiers=%s draw=%s" % (sorted(tiers), json.dumps(draw, ensure_ascii=False)))

    reveal = re.search(r'const REVEAL_CARD := "([^"]+)"', p0_src)
    reuse = set(spec["asset_plan"]["reuse"])
    check("V08_reveal_card_and_reuse_origin",
          bool(reveal) and reveal.group(1) == "focus"
          and "reuse:card:focus" in reuse
          and "reuse:card:" + reveal.group(1) in reuse,
          "REVEAL_CARD=%s reuse:card:focus=%s" % (
              reveal.group(1) if reveal else None, "reuse:card:focus" in reuse))

    ra_m = re.search(r'static func reuse_assets\(\) -> Array:\s*return \[(.*?)\]', p0_src, re.S)
    ra = re.findall(r'"([^"]+)"', ra_m.group(1)) if ra_m else []
    expected_assets = {r.split(":")[-1] for r in reuse}
    check("V09_reuse_assets_exact_and_no_new_items",
          set(ra) == expected_assets and not any(a.startswith("new:") for a in ra),
          "got=%s expected=%s" % (sorted(ra), sorted(expected_assets)))

    cards = set(table.get("cards", {}))
    motions = set(table.get("motions", {}))
    check("V10_motion_table_assets_real_hit_crush_absent",
          {"focus", "jab", "cross", "wave"} <= cards
          and {"hit_light", "hit_heavy", "block"} <= motions
          and "hit_crush" not in motions and "stance" in table,
          "cards=%d motions=%s hit_crush_baked=%s" % (
              len(cards), sorted(motions), "hit_crush" in motions))

    # ── 3. 源码接线形态（钉串，不钉词） ──────────────────────
    retired = ["perform_visual(String(tk_player_ids[0]))",
               "perform_visual(String(tk_enemy_ids[0]))",
               'apply_hit(tk_damage, "taikou", "", false)',
               'apply_hit(3, "taikou", "", false)']
    check("V11_old_wiring_forms_retired",
          all(arena_src.count(s) == 0 for s in retired),
          json.dumps({s: arena_src.count(s) for s in retired}, ensure_ascii=False))

    wired = [
        "player.perform_visual(MotionP0.REVEAL_CARD)",
        "enemy.perform_visual(MotionP0.REVEAL_CARD)",
        "MotionP0.binding_for(winner_type)",
        "player.perform_visual(tk_motion_id)",
        "enemy.perform_visual(tk_motion_id)",
        "enemy.apply_hit(tk_damage, \"taikou\", tk_motion_extra, false)",
        "player.apply_hit(tk_damage, \"taikou\", tk_motion_extra, false)",
        "player.apply_hit(3, \"taikou\", tk_motion_extra, false)",
        "enemy.apply_hit(3, \"taikou\", tk_motion_extra, false)",
    ]
    check("V12_new_wiring_forms_all_present",
          all(arena_src.count(s) >= 1 for s in wired)
          and arena_src.count('tk_motion_id = ""') >= 2,
          json.dumps({s: arena_src.count(s) for s in wired}, ensure_ascii=False))

    # 「钉形态不钉词」：接线注释里也写了 Rules.damage_of()，裸 count 得 3
    # （2 次真调用 + 1 次注释）。改钉完整赋值形态，并与备份独立复算。
    backup_src = (BACKUP / "arena.gd").read_bytes().decode("utf-8")
    dmg_forms = ["tk_damage = Rules.damage_of(tk_player_result)",
                 "tk_damage = Rules.damage_of(tk_enemy_result)"]
    real_calls = [arena_src.count(s) == 1 for s in dmg_forms]
    check("V13_damage_formula_untouched",
          all(real_calls)
          and all(backup_src.count(s) == 1 for s in dmg_forms)
          and "tk_damage = 3" in arena_src
          and "MotionP0.label_of(winner_type)" in arena_src,
          "real_calls=%s raw_count_incl_comment=%d" % (
              real_calls, arena_src.count("Rules.damage_of(")))

    hud_forms = ["if String(arena.tk_motion_id) != \"\":",
                 "String(arena.tk_motion_label), String(arena.tk_react_id)",
                 "hint += "]
    check("V14_hud_wiring_form_present",
          all(hud_src.count(s) >= 1 for s in hud_forms),
          json.dumps({s: hud_src.count(s) for s in hud_forms}, ensure_ascii=False))

    check("V15_draw_banner_uses_label_variable",
          '"双方各受 3 点 · %s" % tk_motion_label' in arena_src
          and '"双方各受 3 点 · 对峙"' not in arena_src,
          "hardcoded_label_absent=%s" % ('"双方各受 3 点 · 对峙"' not in arena_src))

    # ── 4. 引擎内真实输出 ────────────────────────────────────
    recs = all_checks["checks"]
    p0_rec = next((r for r in recs if r["check"] == "tests/battle_motion_p0_check.gd"), {})
    check("V16_all_eleven_engine_checks_green",
          all_checks["result"] == "ALL GREEN" and all_checks["total"] == 11
          and len(recs) == 11 and all(r["ok"] and r["rc"] == 0 for r in recs)
          and "93/93 passed" in p0_rec.get("summary", ""),
          "result=%s total=%d p0=%s" % (all_checks["result"], all_checks["total"],
                                        p0_rec.get("summary")))

    crecs = {r["mode"]: r for r in capture["records"]}
    expected_marker = {
        "reveal": ["p_action=focus", "e_action=focus", "hp=100/100"],
        "triple": ["motion=wave", "label=气功波", "hp=100/77"],
        "sequence": ["motion=cross", "label=交叉反击", "hp=100/85"],
        "scatter": ["motion=jab", "label=刺拳", "hp=100/90"],
        "draw": ["motion= ", "label=对峙", "hp=97/97"],
    }
    marker_ok = all(
        m in crecs and crecs[m]["ok"] and crecs[m]["engine_errors"] == 0
        and crecs[m]["gl"] and crecs[m]["marker_ok"] and crecs[m]["marker"]
        and all(tok in crecs[m]["marker"][0] for tok in toks)
        for m, toks in expected_marker.items())
    taikou_ok = all(
        any(tok in line for line in crecs[m]["taikou"])
        for m, tok in {"triple": "motion=wave react=hit_crush extra=super",
                       "sequence": "motion=cross react=hit_heavy extra=launch",
                       "scatter": "motion=jab react=hit_light extra=",
                       "draw": "winner=draw dmg=3 motion= react=hit_light"}.items()
        if m in crecs)
    check("V17_five_engine_frames_and_taikou_log",
          capture["restore_ok"] and len(crecs) == 5 and marker_ok and taikou_ok,
          "restore=%s modes=%s marker_ok=%s taikou_ok=%s" % (
              capture["restore_ok"], sorted(crecs), marker_ok, taikou_ok))

    imgs = {k: Image.open(HERE / fn).convert("RGB") for k, fn in FRAME_FILES.items()}
    recalc = {}
    for a, b in (("triple", "sequence"), ("triple", "scatter"),
                 ("triple", "draw"), ("sequence", "scatter"),
                 ("sequence", "draw"), ("scatter", "draw")):
        recalc["%s_vs_%s" % (a, b)] = diff_px(imgs[a], imgs[b], HINT_BOX)
    ev_ok = (evidence["result"] == "EVIDENCE_P0_OK"
             and evidence["passed"] == evidence["total"] == 9
             and recalc == evidence["hint_diffs"]
             and min(recalc.values()) > 20)
    check("V18_pixel_evidence_recomputed_from_png",
          ev_ok, "recalc_min=%d json_min=%d identical=%s" % (
              min(recalc.values()), min(evidence["hint_diffs"].values()),
              recalc == evidence["hint_diffs"]))

    # 指纹落盘：给文件清单与后续复核用，不参与自证
    fps = {}
    for rel in ["scripts/arena.gd", "scripts/hud.gd", "scripts/battle_motion_p0.gd",
                "tests/battle_motion_p0_check.gd", "scripts/fighter.gd",
                "scripts/taikou_rules.gd", "data/card_motion.json",
                "scripts/taikou_flow_check.gd", "scripts/taikou_rage_check.gd"]:
        p = GAME / rel
        if p.is_file():
            fps[rel] = {"sha256": sha(p), "bytes": p.stat().st_size}
    FINGERPRINT.write_text(json.dumps(fps, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    passed = sum(1 for c in checks if c["ok"])
    RESULT.write_text(json.dumps({
        "checks": checks, "passed": passed, "total": len(checks),
        "result": "P0_WIRING_VERIFIED" if passed == len(checks) else "P0_WIRING_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %d/%d %s" % (passed, len(checks),
                                "P0_WIRING_VERIFIED" if passed == len(checks)
                                else "P0_WIRING_FAILED"))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
