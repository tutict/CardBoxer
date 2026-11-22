# -*- coding: utf-8 -*-
"""#213 承重判据：证明「招牌动作规格」不是一份自说自话的文档。

全部读真实动作表 / 真实 P0 规格 / 真实源码 sha 基线，并**独立复算**
pose_metrics 的 13 个指标，不写死「我以为」的数字。
不评好看、不宣称已接线、不宣称引擎内效果。
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pose_metrics as pm  # noqa: E402

GAME = pm.GAME
BAKE = HERE.parent
P0_SPEC = BAKE / "combat-motion-design" / "battle_motion_spec.json"

SPEC = json.loads((HERE / "signature-motion-spec.json").read_bytes().decode("utf-8-sig"))
SPEC_TXT = (HERE / "signature-motion-design-specification.txt").read_text(encoding="utf-8-sig")
CM = pm.load_json(GAME / "data" / "card_motion.json")
MI = pm.load_json(GAME / "data" / "motion_input.json")
MF = pm.load_json(GAME / "data" / "motion_input_foe.json")
GAP = json.loads((HERE / "data" / "pose_gap.json").read_text(encoding="utf-8-sig"))
PROBE = json.loads((HERE / "data" / "tables_probe.json").read_text(encoding="utf-8-sig"))
BASELINE = json.loads((HERE / "orig" / "spec-baseline.json").read_text(encoding="utf-8-sig"))
P0 = json.loads(P0_SPEC.read_bytes().decode("utf-8-sig"))

checks: list[dict] = []


def check(name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- 1 规格结构完整 ---------------------------------------------------------
needed = {
    "meta", "coordinate_system", "sources", "source_caveat", "language",
    "threshold_policy", "tiers", "conflicts", "boundaries",
    "cost_account", "provisional_findings",
}
check("spec_structure_complete", needed.issubset(SPEC),
      "missing=%s" % sorted(needed - set(SPEC)))

# ---- 2 来源齐全、唯一、每条有依据 -------------------------------------------
sources = SPEC.get("sources", [])
ids = [s.get("id") for s in sources]
src_ok = (
    len(sources) >= 8 and len(ids) == len(set(ids))
    and all(isinstance(s.get("key_claims"), list) and s["key_claims"]
            and s.get("url") and s.get("title") and s.get("kind")
            for s in sources)
)
check("sources_complete_and_unique", src_ok,
      "sources=%d unique=%d kinds=%s" % (
          len(sources), len(set(ids)),
          sorted({s.get("kind") for s in sources})))

# ---- 3 八条语言规则自洽，且每条指标真的存在 ---------------------------------
allowed = set(pm.METRIC_NAMES) | {"peak_pose_distance"}
lang = SPEC.get("language", [])
lang_ids = [r.get("id") for r in lang]
bad_rules = []
for r in lang:
    if not all(k in r for k in ("id", "name", "claims", "metrics",
                                "phase_scope", "applies_to", "target",
                                "source_ids")):
        bad_rules.append(r.get("id", "?") + ":missing_field")
        continue
    if not r["metrics"] or any(m not in allowed for m in r["metrics"]):
        bad_rules.append(r["id"] + ":bad_metric")
    if not r["source_ids"] or any(s not in ids for s in r["source_ids"]):
        bad_rules.append(r["id"] + ":bad_source_ref")
    if not isinstance(r["target"], dict) or not r["target"].get("basis"):
        bad_rules.append(r["id"] + ":no_basis")
rules_ok = (set(lang_ids) == {f"L{i}" for i in range(1, 9)}
            and len(lang_ids) == 8 and not bad_rules)
check("language_rules_complete_and_traceable", rules_ok,
      "rules=%d bad=%s" % (len(lang_ids), bad_rules))

# ---- 4 三条硬约束必须在规格里显式写死 ---------------------------------------
by_id = {r["id"]: r for r in lang}
l3 = str(by_id.get("L3", {}).get("target", {}).get("rule", ""))
l4 = str(by_id.get("L4", {}).get("target", {}).get("rule", ""))
l5 = str(by_id.get("L5", {}).get("target", {}).get("rule", ""))
hard_ok = (
    "peak_reach_phase == 'active'" in l3
    and "exact_hold_pairs 必须保持 0" in l4
    and "不得引入" in l4
    and "1.5px" in l5
)
check("hard_rules_are_explicit", hard_ok,
      "L3=%r L4=%r L5=%r" % (l3[:60], l4[:60], l5[:60]))

# ---- 5 坐标系与真实表逐字 / 逐值一致 ----------------------------------------
cs = SPEC.get("coordinate_system", {})
frame_keys = sorted(CM["cards"]["jab"]["track"][0].keys())
joint_fields = [k for k in frame_keys if k in pm.JOINTS]
stance_live = pm.joints_of(CM["stance"])
snapshot = cs.get("stance_snapshot", {})
snap_ok = all(
    k in snapshot and tuple(float(x) for x in snapshot[k]) == stance_live[k]
    for k in pm.JOINTS
) and len(snapshot) == len(pm.JOINTS)
coord_ok = (
    cs.get("units") == CM["units"]
    and cs.get("joints") == pm.JOINTS
    and sorted(joint_fields) == sorted(pm.JOINTS)
    and snap_ok
    and cs.get("metric_count") == len(pm.METRIC_NAMES)
)
check("coordinate_matches_live_table", coord_ok,
      "units_eq=%s joints_eq=%s stance_eq=%s metrics=%s" % (
          cs.get("units") == CM["units"], cs.get("joints") == pm.JOINTS,
          snap_ok, cs.get("metric_count")))

# ---- 6 13 指标对 15 轨全部可算且为有限值（防空集真空通过）-------------------
trs = pm.tracks_of(CM)
met = pm.all_metrics(CM)
finite = []
for name, m in met.items():
    for k, v in m.items():
        if isinstance(v, float) and not math.isfinite(v):
            finite.append(f"{name}/{k}")
        if k not in pm.METRIC_NAMES:
            finite.append(f"{name}/{k}:unknown")
attacks = len(GAP["attack_tracks"])
pairs = 0
for i, a in enumerate(GAP["attack_tracks"]):
    for b in GAP["attack_tracks"][i + 1:]:
        if math.isfinite(pm.peak_pose_distance(CM, a, b)):
            pairs += 1
metrics_ok = (
    len(trs) == 15 and len(met) == 15 and attacks == 6
    and all(len(m) == len(pm.METRIC_NAMES) for m in met.values())
    and not finite and pairs == 15
)
check("metrics_computable_on_all_tracks", metrics_ok,
      "tracks=%d metrics_each=%d attacks=%d pairs=%d bad=%s" % (
          len(trs), len(pm.METRIC_NAMES), attacks, pairs, finite[:5]))

# ---- 7 档位与 P0 已验收的牌型绑定一致 ---------------------------------------
binding = P0["card_type_binding"]
tiers = SPEC.get("tiers", {})
tier_ok = True
tier_detail = []
for t in ("triple", "sequence", "scatter"):
    want = binding[t]["winner_asset"].split(":")[-1]
    got = tiers.get(t, {}).get("winner_asset")
    tier_ok &= (want == got and got in trs)
    tier_detail.append(f"{t}:{want}/{got}")
tier_ok &= (tiers.get("draw", {}).get("winner_asset") is None)
check("tiers_match_p0_binding", tier_ok,
      "%s draw_null=%s" % (
          " ".join(tier_detail),
          tiers.get("draw", {}).get("winner_asset") is None))

# ---- 8 五条冲突全部点名，且 C1 不许退役 P4 ----------------------------------
confs = SPEC.get("conflicts", [])
conf_text = json.dumps(confs, ensure_ascii=False)
c1 = next((c for c in confs if c.get("id") == "C1"), {})
conf_ok = (
    len(confs) >= 4
    and all(w in conf_text for w in ("P4", "pose_probe", "三表同步", "历史"))
    and "不退役" in str(c1.get("resolution", ""))
)
check("conflicts_named_and_p4_not_retired", conf_ok,
      "conflicts=%d keywords_ok=%s c1=%r" % (
          len(confs), all(w in conf_text for w in
                          ("P4", "pose_probe", "三表同步", "历史")),
          str(c1.get("resolution", ""))[:50]))

# ---- 9 边界齐全 -------------------------------------------------------------
bounds = SPEC.get("boundaries", [])
btext = " ".join(bounds)
bound_ok = (
    len(bounds) >= 6
    and "不复刻" in btext
    and "不改玩法判定" in btext
    and "阶段时长" in btext
    and "不评" in btext
)
check("boundaries_declared", bound_ok,
      "boundaries=%d" % len(bounds))

# ---- 10 现状实测：独立重算，不信任产物 json ----------------------------------
pf = SPEC.get("provisional_findings", {})
tier_gain = {n: met[n]["peak_reach_gain_px"]
             for n in ("wave", "cross", "jab")}
inverted = tier_gain["wave"] < tier_gain["cross"] < tier_gain["jab"]
exact_total = sum(m["exact_hold_pairs"] for m in met.values())
overshoot_zero = all(met[n]["recover_overshoot_px"] == 0
                     for n in GAP["attack_tracks"])
worst_name, worst_val = max(
    ((n, m["end_drift_px"]) for n, m in met.items()), key=lambda kv: kv[1])

# 三表同步也自己重算，不只读 tables_probe.json
disagree, compared = 0, 0
for side, obj in (("player", MI), ("foe", MF)):
    for card, node in obj["cards"].items():
        tr = node["track"]
        ct = trs[card][1]
        if len(tr) != len(ct):
            disagree += 1
            continue
        for a, b in zip(ct, tr):
            ja, jb = pm.joints_of(a), pm.joints_of(b)
            for k in pm.JOINTS:
                compared += 1
                if ja[k] != jb[k]:
                    disagree += 1

recomputed = {
    "track_count": len(trs),
    "attack_track_count": len(GAP["attack_tracks"]),
    "three_tier_reach_gain_px": tier_gain,
    "three_tier_order_is_inverted": inverted,
    "cross_peak_reach_phase": met["cross"]["peak_reach_phase"],
    "cross_peak_reach_argmax": met["cross"]["peak_reach_argmax"],
    "wave_peak_bbox_gain_pct": met["wave"]["peak_bbox_gain_pct"],
    "exact_hold_total": exact_total,
    "attack_recover_overshoot_all_zero": overshoot_zero,
    "end_drift_worst_px": worst_val,
    "end_drift_worst_track": worst_name,
    "joint_sync_checked": compared,
    "joint_sync_disagreements": disagree,
}
find_bad = [k for k, v in recomputed.items()
            if k in pf and pf[k] != v]
# 产物 json 也要和独立重算对上，防止两套数字打架
gap_bad = (
    GAP["exact_hold_total"] != exact_total
    or GAP["metrics"]["wave"]["peak_reach_gain_px"] != tier_gain["wave"]
    or PROBE["sync"]["joint_values_checked"] != compared
)
find_ok = not find_bad and not gap_bad and len(find_bad) == 0
check("provisional_findings_independently_recomputed", find_ok,
      "recomputed=%s mismatched=%s gap_conflict=%s" % (
          json.dumps(recomputed, ensure_ascii=False)[:230],
          find_bad, gap_bad))

# ---- 11 规格说明存在、覆盖所有 L/S id、给复算命令 ----------------------------
txt_ok = (
    len(SPEC_TXT) > 2000
    and all(f" {lid} " in SPEC_TXT or f"{lid} " in SPEC_TXT
            for lid in lang_ids)
    and all(sid in SPEC_TXT for sid in ids)
    and "python -u verify_pose_spec.py" in SPEC_TXT
)
check("spec_text_covers_rules_and_sources", txt_ok,
      "bytes=%d lang=%d sources=%d" % (len(SPEC_TXT), len(lang_ids), len(ids)))

# ---- 12 游戏源码 0 改动（14 个受监控文件逐项 sha）---------------------------
mismatch = []
for rel, meta in BASELINE["files"].items():
    p = GAME / rel
    if not p.is_file() or sha(p) != meta["sha256"]:
        mismatch.append(rel)
check("game_sources_untouched", not mismatch and len(BASELINE["files"]) == 14,
      "files=%d mismatch=%s" % (len(BASELINE["files"]), mismatch))

# ---- 13 规格阶段不接引擎 -----------------------------------------------------
engine = [p.name for p in HERE.rglob("*")
          if p.suffix in {".gd", ".tscn", ".import", ".godot"}]
check("no_engine_wiring_in_spec_stage", not engine,
      "engine_files=%s" % engine[:6])

# ---- 14 二手帧数不作硬阈值、成本账点名仓内锚 --------------------------------
caveat = str(SPEC.get("source_caveat", ""))
cost = " ".join(SPEC.get("cost_account", []))
caveat_ok = (
    "二手" in caveat and "硬阈值" in caveat
    and "0.09365" in cost and "pose_probe" in cost
    and "1.5px" in cost
)
check("external_frame_numbers_not_used_as_thresholds", caveat_ok,
      "caveat_len=%d cost_items=%d" % (
          len(caveat), len(SPEC.get("cost_account", []))))

passed = sum(1 for c in checks if c["ok"])
for c in checks:
    print(f"{'PASS' if c['ok'] else 'FAIL'}  {c['name']}  {c['detail']}",
          flush=True)
verdict = "POSE_SPEC_VERIFIED" if passed == len(checks) else "POSE_SPEC_FAILED"
print(f"\n{passed}/{len(checks)} PASS  {verdict}", flush=True)
(HERE / "verify_pose_spec_result.json").write_text(
    json.dumps({"verdict": verdict, "passed": passed, "total": len(checks),
                "checks": checks, "recomputed": recomputed},
               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
sys.exit(0 if passed == len(checks) else 1)
