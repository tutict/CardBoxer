"""H 路线承重判据：双方 3D 侧面战斗。

只读盘、只复算，不改任何文件。判据分六族：
零污染 / 源码形状 / 资产独立性 / 引擎内双侧 / 判据订正与退役 / 边界如实。

用法：python verify_h.py
退出码 0 且打印 H_VERIFIED 才算全绿。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
BACKUP = HERE / "orig" / "pre-3d-foe"
LIST = HERE / "文件清单.txt"
RECORD = HERE / "H路线-验证记录.txt"

C = {}


def rd(name: str):
    return json.loads((D / name).read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def all_true(d: dict, key: str = "checks") -> bool:
    v = d.get(key, {})
    return isinstance(v, dict) and len(v) > 0 and all(v.values())


def txt(rel: str) -> str:
    return (GAME / rel).read_text(encoding="utf-8")


def main() -> int:
    # ── 1. 关键文件在位 ────────────────────────────────────────
    must = [
        "foe-rigged.glb", "boards/H-双侧角色特写.png",
        "boards/H-单侧隔离对照.png", "boards/H-同进程单角色特写.png",
        "data/motion_input_foe.json", "data/two_side_ab.json",
        "data/vp_diag_h.json", "data/isolate_h.json",
        "data/static_ab_h.json", "data/all_checks_h.json",
        "data/cross_h.json", "data/cross_h_v1_retired.json",
        "data/identity_h.json", "tests/two_side_probe.gd",
        "tests/vp_diag_probe.gd", "H路线-验证记录.txt", "文件清单.txt",
    ]
    C["H01_required_files_present"] = all((HERE / m).is_file() for m in must)
    glb = HERE / "foe-rigged.glb"
    C["H02_glb_magic_and_size"] = (glb.is_file()
        and glb.stat().st_size > 40_000_000
        and glb.open("rb").read(4) == b"glTF")

    # ── 2. 零污染 ──────────────────────────────────────────────
    base = json.loads((HERE / "baseline_h.json").read_text(
        encoding="utf-8"))
    files = base["files"]
    C["H03_baseline_backup_verified"] = (
        base["count"] == 122 and base["backup_verified"] is True
        and base["backup_mismatch"] == [])
    C["H04_backup_bytes_match_baseline"] = all(
        (BACKUP / r["rel"]).is_file()
        and (BACKUP / r["rel"]).stat().st_size == r["size"]
        and sha(BACKUP / r["rel"]) == r["sha256"] for r in files)
    changed_ok = {"scripts/arena.gd", "scripts/fighter_3d_layer.gd"}
    untouched = [r for r in files if r["rel"] not in changed_ok]
    C["H05_game_tree_untouched_except_two_sources"] = (
        len(untouched) == 120 and all(
            (GAME / r["rel"]).is_file()
            and sha(GAME / r["rel"]) == r["sha256"] for r in untouched))
    patch = rd("patch_game_h.json")
    C["H06_patch_before_matches_backup"] = all(
        v["backup_matches"] is True
        and sha(BACKUP / k) == v["sha256"]
        for k, v in patch["before"].items())
    C["H07_patch_after_matches_live_sources"] = all(
        sha(GAME / k) == v for k, v in patch["after"].items())
    C["H08_fighter_gd_sha_unchanged"] = (
        patch["after"]["scripts/fighter.gd"]
        == patch["before"]["scripts/fighter.gd"]["sha256"])

    static = rd("static_ab_h.json")
    C["H09_static_ab_pixel_identical"] = (
        static["ok"] is True and static["changed_pixels"] == 0
        and all_true(static))
    checks_h = rd("all_checks_h.json")
    C["H10_all_15_checks_green"] = (
        checks_h["total"] == 15 and checks_h["result"] == "ALL GREEN"
        and checks_h["failed"] == []
        and len(checks_h["checks"]) == 15
        and all(r["ok"] for r in checks_h["checks"]))

    # ── 3. 源码形状 ────────────────────────────────────────────
    arena = txt("scripts/arena.gd")
    fighter = txt("scripts/fighter.gd")
    layer = txt("scripts/fighter_3d_layer.gd")
    C["H11_switch_default_off"] = (
        "var use_3d := false" in arena
        and 'use_3d = OS.get_environment("CARD_BOXER_3D") != ""' in arena)
    C["H12_override_default_false"] = (
        "var draw_3d_override := false" in fighter)
    C["H13_layer_parametrised"] = all(s in layer for s in [
        'const FOE_GLB_PATH := "res://assets/3d/foe-rigged.glb"',
        "const DEFAULT_FOE_YAW := -55.0",
        "func configure(", "var res := load(glb_path)",
        'var role_id := "player"'])
    C["H14_arena_two_layers_wired"] = all(s in arena for s in [
        "layer_3d_foe", "motion_3d_foe",
        "enemy.draw_3d_override = true",
        'tk_rhythm_winner == "enemy"',
        "Fighter3DLayerScript.FOE_GLB_PATH",
        "Fighter3DLayerScript.DEFAULT_FOE_YAW"])
    C["H15_patch_checks_all_true"] = all_true(patch) and patch["ok"] is True
    syn = (HERE / "logs" / "godot_syntax_h.out").read_text(
        encoding="utf-8", errors="replace")
    C["H16_no_syntax_errors"] = ("Parse Error" not in syn
        and "SCRIPT ERROR" not in syn and "first_scan_filesystem" in syn)

    # ── 4. 资产独立性 ──────────────────────────────────────────
    inst = rd("install_assets_h.json")
    C["H17_install_checks_all_true"] = all_true(inst) and inst["ok"] is True
    C["H18_two_copies_byte_identical"] = (
        len(inst["copies"]) == 2 and all(c["identical"] for c in inst["copies"]))
    C["H19_glb_in_game_matches_archive"] = (
        sha(GAME / "assets/3d/foe-rigged.glb") == sha(glb))
    C["H20_foe_motion_in_game_matches_archive"] = (
        sha(GAME / "data/motion_input_foe.json")
        == sha(D / "motion_input_foe.json"))
    pair = rd("glb_pair_h.json")["pair"]
    pbr_ingame = [g for g in inst["generated"]
                  if g["rel"].endswith(".png")
                  and not g["rel"].endswith(".png.import")]
    C["H21_three_pbr_4096_and_embedded_sha_match"] = (
        len(pbr_ingame) == 3
        and all(g.get("size") == [4096, 4096] for g in pbr_ingame)
        and {g["sha256"] for g in pbr_ingame}
        == {i["sha256"] for i in pair["foe"]["images"]})
    insp = rd("foe_gltf_inspection.json")
    C["H22_gltf_inspection_all_true"] = all_true(insp) and insp["ok"] is True
    C["H23_glb_static_with_14_joints"] = (
        insp["verdict"]["zero_animations"] is True
        and insp["verdict"]["skin_joints"] == 14
        and insp["verdict"]["highpoly_has_skin"] is True)
    gp = rd("glb_pair_h.json")
    C["H24_two_glbs_are_distinct_assets"] = (
        gp["image_sets_identical"] is False
        and gp["shared_image_count"] == 0
        and gp["verts_different"] is True
        and gp["bbox_different"] is True)
    ident = rd("identity_h.json")
    C["H25_assets_distinct_scope_not_overclaimed"] = (
        all_true(ident) and ident["ok"] is True
        and ident["basecolor_thumb_mae"] > 5.0
        and ident["roi_mirrored"]["ratio"] > 0.20
        and "背景" in ident.get("roi_scope_note", "")
        and "frames_not_identical_including_background" in ident["checks"])
    apose = rd("apose_crosscheck_h.json")
    C["H26_foe_apose_is_its_own_rest"] = (
        all_true(apose) and apose["ok"] is True
        and apose["player_worst_abs_diff"] < 1e-5
        and apose["keys_other_than_apose_identical"] is True)
    fm = rd("motion_input_foe.json")
    pm = json.loads((GAME / "data/motion_input.json").read_text(
        encoding="utf-8"))
    C["H27_only_three_attack_tracks_73_frames"] = (
        set(fm["cards"]) == {"jab", "cross", "wave"}
        and [fm["cards"][k]["frames"] for k in ("jab", "cross", "wave")]
        == [14, 22, 36]
        and sum(fm["cards"][k]["frames"]
                for k in ("jab", "cross", "wave")) == 72
        and fm["apose_points"] != pm["apose_points"])
    rest = rd("rest_diff_h.json")
    C["H28_rest_skeleton_differs_measurably"] = (
        len(rest) == 13
        and max(r["dhead_dist"] for r in rest) > 0.20)

    # ── 5. 引擎内双侧 ──────────────────────────────────────────
    ab = rd("two_side_ab.json")
    pay = ab["payload"]
    C["H29_two_side_ab_all_true"] = all_true(ab) and ab["ok"] is True
    C["H30_engine_run_clean"] = (
        ab["run"]["returncode"] == 0 and ab["run"]["has_opengl"] is True
        and ab["run"]["script_errors"] == 0
        and ab["run"]["headless"] is False)
    C["H31_five_shots_real_png"] = all(
        Path(r["path"]).is_file() and Path(r["path"]).stat().st_size > 10000
        and r["w"] == 1280 and r["h"] == 720 and r["save_error"] == 0
        for r in pay["shots"]) and len(pay["shots"]) == 5
    C["H32_both_layers_driven"] = (
        pay["bones"] == 13 and pay["foe_bones"] == 13
        and pay["player_frames_applied"] > 0
        and pay["foe_frames_applied"] > 0
        and pay["player_tex_drawn"] is True
        and pay["foe_tex_drawn"] is True)
    C["H33_mirrored_side_yaw"] = (
        pay["player_yaw"] == 55.0 and pay["foe_yaw"] == -55.0
        and pay["foe_role"] == "foe")
    C["H34_no_shared_viewport_or_texture"] = (
        pay["sv_same"] is False and pay["tex_same"] is False
        and pay["player_glb_path"] != pay["foe_glb_path"]
        and pay["player_mesh_sig"] != pay["foe_mesh_sig"])
    C["H35_prims_grew_when_3d_on"] = (
        ab["prims"]["both-stance"] > ab["prims"]["off"] * 2
        and ab["prims"]["off"] == 5136.0)
    vp = rd("vp_diag_h.json")
    diffs = vp["diffs"]
    C["H36_vp_diag_all_true"] = all_true(vp) and vp["ok"] is True
    C["H37_same_process_untouched_exactly_zero"] = (
        diffs["player-hidden_untouched"]["changed_px"] == 0
        and diffs["foe-hidden_untouched"]["changed_px"] == 0)
    C["H38_same_process_own_side_changed"] = (
        diffs["player-hidden_changed"]["ratio"] > 0.20
        and diffs["foe-hidden_changed"]["ratio"] > 0.20)
    iso = rd("isolate_h.json")
    C["H39_isolate_all_true"] = all_true(iso) and iso["ok"] is True
    roi = rd("roi_h.json")
    C["H40_roi_auto_two_regions"] = (
        roi["two_regions"] is True and len(roi["boxes"]) == 2
        and roi["peak_col_diff"] > roi["threshold"])
    zoom = rd("zoom_h.json")
    C["H41_zoom_board_distinct"] = (
        zoom["distinct"] is True and zoom["changed_ratio"] > 0.90)
    boards = [HERE / "boards" / n for n in (
        "H-双侧角色特写.png", "H-单侧隔离对照.png",
        "H-同进程单角色特写.png")]
    C["H42_three_boards_nonempty"] = all(
        p.is_file() and p.stat().st_size > 100_000 for p in boards)
    C["H43_probe_script_copied_into_game"] = (
        sha(GAME / "tests/two_side_probe.gd")
        == sha(HERE / "tests/two_side_probe.gd"))

    # ── 6. 判据订正与退役 ──────────────────────────────────────
    v1 = rd("cross_h_v1_retired.json")
    cross = rd("cross_h.json")
    C["H44_v1_negative_result_preserved"] = (
        v1["ok"] is False and v1["left_ok"] is False
        and v1["right_ok"] is False)
    C["H45_retired_metric_is_named"] = (
        "absolute ROI pixel identity" in cross.get("retired_metric", "")
        and "ratio < 0.20" in cross["retired_metric"])
    C["H46_v2_directional_checks_all_true"] = (
        all_true(cross) and cross["ok"] is True
        and min(cross["directional_margin"].values()) > 0.05)
    C["H47_primary_evidence_points_to_same_process"] = (
        "vp_diag_h.json" in cross["primary_evidence"])
    C["H48_absolute_identity_fields_removed"] = (
        "left_ok" not in cross and "right_ok" not in cross
        and "CROSS_H_OK" not in (HERE / "logs" / "diag_cross_h.out").read_text(
            encoding="utf-8", errors="replace"))
    C["H49_retired_claim_not_reused_as_pass"] = (
        v1["ok"] is False
        and cross["checks"]["no_absolute_identity_claim"] is True
        and C["H37_same_process_untouched_exactly_zero"])

    # ── 7. 边界如实 ────────────────────────────────────────────
    C["H50_zero_animations_declared"] = (
        insp["verdict"]["zero_animations"] is True)
    C["H51_not_full_228_frames"] = (
        sum(fm["cards"][k]["frames"] for k in fm["cards"]) == 72)
    C["H52_default_off_means_2d_game"] = C["H11_switch_default_off"]
    C["H53_no_bak_tmp_leftovers"] = not any(
        p.suffix in {".bak", ".tmp"} for p in HERE.rglob("*")
        if p.is_file() and "orig" not in p.parts and "logs" not in p.parts)
    # 清单自洽：逐行复算 size / sha256（与 make_filelist_h.py 同口径）
    rows = [ln for ln in LIST.read_bytes().decode("utf-8").splitlines()
            if ln and not ln.startswith("#")] if LIST.is_file() else []
    good = 0
    for ln in rows:
        parts = ln.split("\t")
        if len(parts) != 3:
            continue
        rel, size, digest = parts
        p = HERE / rel
        if p.is_file() and p.stat().st_size == int(size) and sha(p) == digest:
            good += 1
    C["H54_filelist_selfconsistent"] = (len(rows) > 40 and good == len(rows))
    C["H55_record_is_in_filelist"] = any(
        ln.startswith("H路线-验证记录.txt\t") for ln in rows)
    C["H56_record_nonempty"] = (RECORD.is_file()
        and RECORD.stat().st_size > 4000)

    failed = [k for k, v in C.items() if not v]
    for k, v in C.items():
        print(("OK   " if v else "FAIL ") + k)
    print(f"VERIFY_H {len(C) - len(failed)}/{len(C)} failed={len(failed)}")
    print("H_VERIFIED" if not failed else "H_NOT_VERIFIED")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
