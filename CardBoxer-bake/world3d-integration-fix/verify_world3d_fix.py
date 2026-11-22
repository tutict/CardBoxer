"""World3D 接线修复 · 汇总承重判据（只读盘，不重跑 Godot / Blender）。

七层，任一 FAIL 即退出码 1：
  A 源码形状   —— own_world_3d 接线在 setup() 里、恰好一次、顺序正确、
                  与备份的 diff 只有插入、没有删除或改写
  B 零改动对账 —— 逐文件 sha256 对账 baseline，除本文件外 21 项全同
  C 报告自洽   —— 每份上游报告独立复核所有 checks 布尔 + failed 名单，
                  不只信 ok 字段（B 路线 P0 的 M4 教训）
  D 数值点名   —— 引擎读回 / 像素 / sha / 亮度归因逐项点名具体值
  E 证据存在   —— 三张对照板与四组截帧非空
  F 默认关     —— use_3d=false、两层 null、override 全 false
  G 历史债     —— 7 条红因全归类、止损绿、logs 还原

用法：python verify_world3d_fix.py
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
P0 = BAKE / "route-b-asset-deduplication"
D = HERE / "data"
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"
BACKUP = HERE / "orig" / "pre-world3d" / "fighter_3d_layer.gd"
SRC = GAME / "scripts" / "fighter_3d_layer.gd"
PRE_GLB = "0edcfe9e455f3c8c9deb7034397c815fd701130ed9a10c2e08800fff789cba88"
PRE_SRC = "6504139c6c81bd607379739b956dea90293e2f84cc5266e8bf4d44b02917a402"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def all_checks(rep: dict) -> bool:
    """独立复核内部 checks 布尔；不信任上游的 ok 字段。"""
    ck = rep.get("checks")
    if not isinstance(ck, dict) or not ck:
        return False
    if not all(v is True for v in ck.values()):
        return False
    failed = rep.get("failed", rep.get("failed_checks", []))
    if failed:
        return False
    return rep.get("ok", True) is True


def main() -> int:
    baseline = load(D / "baseline.json")
    min_pre = load(D / "world3d_min_pre.json")
    min_post = load(D / "world3d_min.json")
    prepost = load(D / "prepost.json")
    shipped = load(D / "shipped_check.json")
    review = load(D / "review_brightness.json")
    checks15 = load(D / "all_checks_local.json")
    legacy = load(D / "legacy_guard_state.json")
    truth = {r["role"]: r for r in
             load(P0 / "data" / "single_layers.json")["runs"]}

    src_text = SRC.read_text(encoding="utf-8")
    bak_text = BACKUP.read_text(encoding="utf-8")
    diff = list(difflib.unified_diff(
        bak_text.splitlines(), src_text.splitlines(), n=0))
    removed = [l for l in diff if l.startswith("-")
               and not l.startswith("---")]
    added = [l for l in diff if l.startswith("+")
             and not l.startswith("+++")]
    code_added = [l for l in added
                  if l[1:].strip() and not l[1:].strip().startswith("#")]
    setup = src_text.split("func setup(", 1)[-1].split("\nfunc ", 1)[0]

    # B：逐文件 sha256 对账
    after = {}
    for rel, row in baseline["files"].items():
        p = GAME / rel
        after[rel] = {"exists": p.is_file(),
                      "sha256": sha256(p) if p.is_file() else ""}
    changed = [rel for rel, row in baseline["files"].items()
               if after[rel]["sha256"] != row["sha256"]]

    sl = shipped["shipped_layers"]
    ll = shipped["legacy_layers"]
    sp = shipped["payloads"]["shipped"]
    dp = shipped["payloads"]["default"]
    npay = shipped["payloads"]["no_tint"]
    runs = shipped["runs"]
    attr = review["attribution"]
    foe_luma = attr["foe_roi_luma"]
    guard_reds = [n for g in legacy["guards"]
                  for n in g.get("failed", [])]

    boards = [BOARDS / "World3D-fix-before-after-comparison.png",
              BOARDS / "World3D-fix-character-brightness-comparison.png",
              BOARDS / "World3D-fix-foe-darkening-analysis.png"]
    frames = [SHOTS / "shipped" / "sh-shipped-live.png",
              SHOTS / "legacy" / "sh-legacy-live.png",
              SHOTS / "no_tint" / "sh-shipped-live.png",
              SHOTS / "default" / "display-live.png"]

    ck = {
        # A 源码形状
        "backup_sha_is_pre": sha256(BACKUP) == PRE_SRC,
        "source_sha_changed": sha256(SRC) != PRE_SRC,
        "own_world_3d_exactly_once": (
            src_text.count("sv.own_world_3d = true") == 1),
        "no_false_assignment": "own_world_3d = false" not in src_text,
        "assignment_inside_setup": "sv.own_world_3d = true" in setup,
        # 先判存在再取 index：接线被删/改值时不能崩栈，必须报红。
        # （变异 M1 抓到过这里抛 ValueError 导致守卫无 FAIL 行。）
        "assignment_before_add_child": (
            "sv.own_world_3d = true" in setup
            and setup.index("sv.own_world_3d = true")
            < setup.index("add_child(sv)")),
        "assignment_after_new_subviewport": (
            "sv.own_world_3d = true" in setup
            and setup.index("sv = SubViewport.new()")
            < setup.index("sv.own_world_3d = true")),
        "diff_has_no_removed_lines": removed == [],
        "diff_only_one_code_line": len(code_added) == 1
        and code_added[0].lstrip("+").strip() == "sv.own_world_3d = true",
        "comment_points_to_recompute": "run_world3d_min.py" in src_text,
        # B 零改动对账
        "baseline_was_green": all_checks(baseline),
        "all_baseline_files_still_exist": all(
            a["exists"] for a in after.values()),
        "only_layer_source_changed": changed == [
            "scripts/fighter_3d_layer.gd"],
        "foe_glb_sha_unchanged": (
            after["assets/3d/foe-rigged.glb"]["sha256"] == PRE_GLB),
        "player_glb_sha_unchanged": (
            after["assets/3d/player-rigged.glb"]["sha256"]
            == baseline["files"]["assets/3d/player-rigged.glb"]["sha256"]),
        "arena_unchanged": (
            after["scripts/arena.gd"]["sha256"]
            == baseline["files"]["scripts/arena.gd"]["sha256"]),
        "project_godot_unchanged": (
            after["project.godot"]["sha256"]
            == baseline["files"]["project.godot"]["sha256"]),
        # C 报告自洽（独立复核 checks，不只看 ok）
        "min_pre_all_green": all_checks(min_pre),
        "min_post_all_green": all_checks(min_post),
        "prepost_all_green": all_checks(prepost),
        "shipped_all_green": all_checks(shipped),
        "legacy_all_green": all_checks(legacy),
        "review_has_no_failed_key": not review.get("failed"),
        "checks15_all_green": (
            checks15["result"] == "ALL GREEN"
            and checks15["failed"] == []
            and len(checks15["checks"]) == 15
            and all(r["ok"] for r in checks15["checks"])),
        "shipped_checks_count_sane": len(shipped["checks"]) >= 25,
        # D 数值点名
        # pre 报告是「判据按前提重建」之前保存的落地前快照，
        # 等价判据名不带 pre_ 前缀；点名当时实际存在的两条核心判据。
        "min_pre_had_pre_premise": (
            min_pre["checks"].get("own_png_sha_equals_both") is True
            and min_pre["checks"].get(
                "world_only_png_sha_equals_own") is True
            and "premise" not in min_pre),
        "min_post_premise_is_post": (
            min_post.get("landed") is True
            and min_post.get("premise") == "post"
            and "sv.own_world_3d = true" in src_text),
        "min_post_na_named": (
            len(min_post.get("not_applicable", [])) == 4),
        "shipped_player_white_13902": (
            sl["player"]["pixels"]["near_white_px"] == 13902),
        "shipped_foe_white_725": (
            sl["foe"]["pixels"]["near_white_px"] == 725),
        "shipped_sha_vs_truth": all(
            sl[l]["png_sha256"] == truth[l]["png_sha256"] != ""
            for l in ("player", "foe")),
        "legacy_both_white": all(
            ll[l]["pixels"]["white_ratio"] > 0.10
            for l in ("player", "foe")),
        "shipped_own_true": all(
            sl[l]["own_world_3d"] is True for l in ("player", "foe")),
        "shipped_yaw_face_to_face": (
            sl["player"]["yaw"] == -55.0 and sl["foe"]["yaw"] == 55.0),
        "shipped_foe_visual_on": (
            sl["foe"]["visual_state"]["foe_visual"] is True
            and sl["player"]["visual_state"]["foe_visual"] is False),
        "shipped_scenario_zero": runs["shipped"]["scenario_errors"] == 0,
        "no_tint_sv_unchanged": (
            shipped["no_tint_layers"]["foe"]["png_sha256"]
            == sl["foe"]["png_sha256"]),
        "tint_effect_positive": attr["tint_effect"] > 0,
        "no_tint_brighter_than_legacy": (
            foe_luma["no_tint"] > foe_luma["legacy"]
            > foe_luma["shipped"]),
        "attribution_conclusion_mentions_tint": (
            "证伪" in attr["conclusion"] and "shader" in attr["conclusion"]),
        # E 证据存在
        "three_boards_nonempty": all(
            p.is_file() and p.stat().st_size > 20000 for p in boards),
        "four_frames_nonempty": all(
            p.is_file() and p.stat().st_size > 20000 for p in frames),
        # F 默认关
        "default_use_3d_false": dp.get("use_3d") is False,
        "default_no_layers": (dp.get("layer_3d") is False
                              and dp.get("layer_3d_foe") is False),
        "default_no_overrides": (dp.get("player_override") is False
                                 and dp.get("enemy_override") is False),
        "default_no_script_errors": (
            runs["default"]["script_errors"] == 0),
        "no_tint_foe_visual_off": (
            npay["state"]["layers"][1]["visual_state"]["foe_visual"]
            is False) if npay.get("state") else False,
        # G 历史债
        "legacy_reds_all_classified": (
            len(guard_reds) == 7
            and not legacy["unclassified_reds"]),
        "legacy_logs_restored": all(
            legacy["logs_restored"].values()),
        "stopgap_green": legacy["checks"]["stopgap_still_green"] is True,
        "legacy_source_sha_matches": (
            legacy["source_sha256"] == sha256(SRC)),
    }
    failed = [k for k, v in ck.items() if not v]
    report = {"checks": ck, "failed": failed,
              "ok": not failed,
              "changed_files": changed,
              "guard_reds": guard_reds,
              "source_sha256": sha256(SRC)}
    (D / "verify_world3d_fix.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for k, v in ck.items():
        if not v:
            print("FAIL", k)
    print(f"VERIFY_WORLD3D_FIX {len(ck) - len(failed)}/{len(ck)} "
          + ("ALL GREEN" if not failed else "FAILED"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
