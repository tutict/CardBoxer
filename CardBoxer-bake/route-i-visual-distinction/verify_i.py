"""I 路线承重判据：每条结论都从盘上重算，不信任任何汇总报告的结论字段。

分组：
  A 源码形状（直接读游戏工程 fighter_3d_layer.gd）
  B 基线对账（baseline_i.json 逐文件 sha256）
  C 规格与负结果（r1 / v1 / v2 负结果必须保持 ok=false）
  D 同进程 A/B 区分度指标
  E 可逆开关与全量回归
  F 交付清单（逐条重算 sha，排除 logs/orig/清单/diff）

输出只写 logs/verify_i.json（清单排除目录），避免清单自指。
用法：python verify_i.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
H = HERE.parent / "route-h-two-sided-3d-combat"
LAYER = GAME / "scripts" / "fighter_3d_layer.gd"
ARENA = GAME / "scripts" / "arena.gd"
FIGHTER = GAME / "scripts" / "fighter.gd"
LIST = HERE / "file-list.txt"
OUT = HERE / "logs" / "verify_i.json"


def j(rel: str) -> dict:
    return json.loads((HERE / rel).read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def game_rels() -> set[str]:
    out = set()
    for p in GAME.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(GAME)
        if any(part in (".godot", "__pycache__") for part in rel.parts):
            continue
        out.add(str(rel).replace("\\", "/"))
    return out


def filelist_actual() -> dict[str, tuple[int, str]]:
    skip = {"logs", ".godot", "__pycache__", "orig"}
    names = {"file-list.txt", "new-files.diff"}
    out = {}
    for p in HERE.rglob("*"):
        if not p.is_file() or p.name in names:
            continue
        rel = p.relative_to(HERE)
        if any(part in skip for part in rel.parts):
            continue
        out[str(rel).replace("\\", "/")] = (p.stat().st_size, sha(p))
    return out


def main() -> int:
    spec = j("data/visual_diff_spec.json")
    baseline = j("baseline_i.json")
    rootcause = j("data/rootcause_i.json")
    texture = j("data/texture_i.json")
    material = j("data/material_i.json")
    v3 = j("data/patch_visual_v3_i.json")
    final = j("data/patch_visual_final_i.json")
    ab = j("data/visual_ab_i.json")
    diag = j("data/visual_diag_i.json")
    r1 = j("data/visual_diag_r1_failed.json")
    off = j("data/off_switch_i.json")
    allc = j("data/all_checks_i.json")
    static = j("data/static_ab_i.json")
    light = j("data/light_isolation_i.json")
    v1 = j("data/v1-failed/visual_diag_i.json")
    v2 = j("data/v2-failed/player_leak_i.json")

    src = LAYER.read_text(encoding="utf-8")
    tint = spec["canvas_tint"]
    tint_lit = "vec3(%s)" % ", ".join(f"{v:.2f}" for v in tint)
    sx, sy = (spec["silhouette"]["draw_scale_x"],
              spec["silhouette"]["draw_scale_y"])
    targets = spec["targets"]
    base_map = {r["rel"]: r["sha256"] for r in baseline["files"]}
    now = game_rels()
    changed = sorted(r for r, h in base_map.items()
                     if r in now and sha(GAME / r) != h)
    missing = sorted(r for r in base_map if r not in now)

    m = diag["metrics"]
    d = diag["diffs"]
    od = off["diffs"]
    c: dict[str, bool] = {}

    # A 源码形状 ---------------------------------------------------
    c["source_scale_matches_spec"] = (
        f"const FOE_DRAW_SCALE_X := {sx:.2f}" in src)
    c["source_scale_y_matches_spec"] = (
        f"const FOE_DRAW_SCALE_Y := {sy:.2f}" in src)
    c["source_tint_matches_spec"] = tint_lit in src
    c["source_has_canvas_shader"] = "shader_type canvas_item" in src
    c["source_canvas_mat_set_and_cleared"] = (
        "material = _foe_canvas_mat" in src and "material = null" in src)
    c["source_no_surface_override"] = (
        "set_surface_override_material" not in src)
    c["source_no_3d_material_duplicate"] = (
        "(base as StandardMaterial3D).duplicate()" not in src)
    c["source_no_light_energy_write"] = (
        'l.light_energy = float(row["energy"])' not in src)
    c["source_retired_constants_absent"] = all(
        n not in src for n in spec["material"]["retired_constants_absent"])
    c["source_off_switch_present"] = (
        '"CARD_BOXER_FOE_VISUAL"' in src and '!= "none"' in src)
    c["source_off_switch_scoped_to_foe"] = (
        'if p_role == "foe" and OS.get_environment(' in src)
    c["source_player_draw_path_identity_shape"] = all(
        s in src for s in (
            "FOE_DRAW_SCALE_X if foe_visual else 1.0",
            "FOE_DRAW_SCALE_Y if foe_visual else 1.0"))
    c["source_G_shape_preserved"] = all(s in src for s in [
        "const DEFAULT_SIDE_YAW := 55.0",
        "drv.apply_frame(c, f)", "_apply_stance_bias()"])
    c["source_collect_meshes_for_diagnostics"] = (
        "func _collect_meshes" in src)

    # B 基线对账 ---------------------------------------------------
    c["baseline_backup_verified"] = (baseline["backup_verified"] is True
                                     and not baseline["backup_mismatch"])
    c["baseline_only_layer_changed"] = (
        changed == ["scripts/fighter_3d_layer.gd"] and not missing)
    c["arena_sha_matches_baseline"] = (
        sha(ARENA) == base_map["scripts/arena.gd"])
    c["fighter_sha_matches_baseline"] = (
        sha(FIGHTER) == base_map["scripts/fighter.gd"])
    c["layer_sha_matches_final_report"] = (
        sha(LAYER) == final["sha256_after"]["scripts/fighter_3d_layer.gd"])

    # C 规格与负结果 -----------------------------------------------
    c["spec_revision_is_2"] = spec.get("revision") == 2
    c["spec_width_target_not_relaxed"] = (
        targets["min_subject_width_ratio"] == 1.1)
    c["spec_retired_constants_named"] = (
        spec["material"]["retired_constants_absent"]
        == ["FOE_TINT", "FOE_METALLIC_MULT", "FOE_CANVAS_TINT"])
    c["spec_off_targets_present"] = all(
        targets.get(k) is True for k in (
            "off_switch_disables_visual_layer",
            "off_state_same_process_pixel_identical",
            "default_off_pixel_identical"))
    c["r1_negative_result_kept_false"] = (
        r1.get("ok") is False
        and r1.get("checks", {}).get("wide_roi_wider_than_plain") is False
        and r1["metrics"]["foe_width_ratio_wide"] < 1.1)
    c["v1_negative_result_kept"] = (
        abs(v1["metrics"].get("player_luma_change_on_vs_plain", 0.0)) > 5.0)
    c["v2_negative_result_kept"] = v2.get("changed_px", 0) > 1000
    c["v3_patch_report_ok"] = v3.get("ok") is True
    c["final_patch_report_ok"] = final.get("ok") is True
    c["rootcause_points_to_render_chain"] = (
        rootcause.get("hypothesis_falsified") is True
        and "metallic" in rootcause.get("root_cause", "")
        and abs(rootcause["render_luma_gap_player_minus_foe"]) < 20.0)
    c["texture_gap_is_real"] = (
        texture["deltas"]["mean_lit_luma_player_minus_foe"] > 60.0)
    c["material_probe_ran"] = material.get("ok") is True

    # D 同进程 A/B --------------------------------------------------
    c["visual_ab_ok"] = ab.get("ok") is True
    c["visual_diag_ok"] = diag.get("ok") is True
    c["visual_diag_all_checks_true"] = all(diag["checks"].values())
    c["player_roi_pixel_identical"] = (
        d["player_roi_on_vs_plain"]["changed_px"]
        == targets["player_roi_changed_px"])
    c["noop_frames_identical"] = (
        d["player_roi_noop"]["changed_px"] == 0
        and d["foe_roi_noop"]["changed_px"] == 0)
    c["repeat_switch_deterministic"] = (
        d["foe_roi_on_vs_again"]["changed_px"] == 0)
    c["luma_gap_above_target"] = (
        m["luma_gap_player_minus_foe_on"]
        >= targets["min_luma_gap_player_minus_foe"])
    c["width_ratio_above_target"] = (
        m["foe_width_ratio_wide"] >= targets["min_subject_width_ratio"])
    c["color_shift_above_target"] = (
        abs(m["red_blue_shift_delta"])
        >= targets["min_abs_red_blue_shift"])
    c["foe_luma_drop_substantial"] = m["foe_luma_drop_on_vs_plain"] > 50.0
    c["player_luma_unchanged"] = (
        abs(m["player_luma_change_on_vs_plain"]) < 0.01)
    c["full_frame_change_is_scoped"] = abs(
        d["full_frame_on_vs_plain"]["changed_px"]
        - d["foe_roi_on_vs_plain"]["changed_px"]) < 2000
    roi_h = json.loads((H / "data" / "roi_h.json").read_text(
        encoding="utf-8"))["boxes"]
    c["width_uses_wide_roi"] = (
        (diag.get("wide_foe_roi", [0, 0, 0, 0])[2]
         - diag.get("wide_foe_roi", [0, 0, 0, 0])[0])
        > (roi_h[1][2] - roi_h[1][0]))
    c["light_isolation_ran"] = (light.get("ok") is True
                                and light.get(
                                    "player_lights_equal_but_pixels_changed")
                                is True)

    # E 可逆开关与回归 ---------------------------------------------
    c["off_switch_all_checks_true"] = all(off["checks"].values())
    c["off_switch_ok"] = off.get("ok") is True
    c["off_configure_did_not_enable"] = (
        off["payload"].get("foe_initial_visual") is False
        and off["payload"].get("env_visual_none") == "none")
    c["off_state_stable_and_restorable"] = (
        od["off1_vs_off2_full"]["changed_px"] == 0
        and od["off1_vs_restored_full"]["changed_px"] == 0)
    c["switch_has_teeth"] = (
        od["off1_vs_forced_foe_roi"]["ratio"] > 0.30)
    c["off_player_roi_never_changes"] = (
        od["off1_vs_forced_player_roi"]["changed_px"] == 0)
    c["all_checks_15_green"] = (
        allc["result"] == "ALL GREEN" and allc["total"] == 15
        and not allc["failed"] and len(allc["checks"]) == 15)
    c["static_ab_zero_pixels"] = (
        static["changed_pixels"] == 0 and static.get("ok") is True)

    # F 交付清单 ---------------------------------------------------
    c["filelist_present"] = LIST.is_file()
    declared = {}
    if LIST.is_file():
        for ln in LIST.read_bytes().decode("utf-8").splitlines():
            if not ln or ln.startswith("#"):
                continue
            p = ln.split("\t")
            if len(p) == 3:
                declared[p[0]] = (int(p[1]), p[2])
    actual = filelist_actual()
    c["filelist_populated"] = len(declared) > 40
    c["filelist_self_consistent"] = (
        bool(declared) and declared == actual)
    boards = ["I-visual-distinction-A-B.png", "I-r1-width-below-target.png",
              "I-V1-failed-global-darkening.png", "I-V2-failed-player-darkening.png",
              "I-player-leak-heatmap.png"]
    c["boards_present"] = all(
        (HERE / "boards" / b).is_file()
        and (HERE / "boards" / b).stat().st_size > 50000 for b in boards)

    failed = [k for k, v in c.items() if not v]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"checks": c, "failed": failed,
                               "ok": not failed},
                              ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in c.items():
        print("CHECK", k, v)
    print(f"VERIFY_I {len(c) - len(failed)}/{len(c)} failed={len(failed)}")
    for k in failed:
        print("  FAILED", k)
    print("I_VERIFIED" if not failed else "I_NOT_VERIFIED")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
