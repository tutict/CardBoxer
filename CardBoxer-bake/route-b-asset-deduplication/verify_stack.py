"""B 路线 P0 承重判据汇总。只读盘上四份报告 + 图 + 工程源码哈希。

不重跑 Godot / Blender，只做「读回来是为了决定」的对账：
  * 四份上游报告自身全绿；
  * 关键数值点名（不是只判 ok）；
  * 历史 SubViewport 取证的标签对调用 sha256 交叉钉死；
  * 工程 GLB / 贴图 / 玩法源码本轮零改动。
输出 data/verify_stack.json；任一红即退出码 1 并打印 FAIL <name>。

用法：python verify_stack.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
J = BAKE / "route-j-model-rework"
ORIENT = BAKE / "orientation-fix"

D = HERE / "data"
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"

GLB_SHA = "0edcfe9e455f3c8c9deb7034397c815fd701130ed9a10c2e08800fff789cba88"
TEX_SHA = "3c1076596ef22f2e45c6509e459f7e262053724ce05b803874ed53a927473d6a"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    diag = load(D / "stack_diagnosis.json")
    pix = load(D / "stack_pixels.json")
    probe = load(D / "stack_probe.json")
    pair = load(D / "current_pair.json")
    single = load(D / "single_layers.json")
    w3d = load(D / "world3d_probe.json")

    sr = {r["role"]: r for r in single["runs"]}
    wst = {s["tag"]: {r["label"]: r for r in s["layers"]}
           for s in w3d["payload"]["states"]}
    wb, wa = wst["before"], wst["after"]

    st = pix["states"]
    slots = probe["payload"]["material_slots"]
    p, f = pair["payload"]["player"], pair["payload"]["foe"]
    pm = p.get("meshes", [{}])[0] if p.get("meshes") else {}
    fm = f.get("meshes", [{}])[0] if f.get("meshes") else {}

    pair_foe = SHOTS / "current_pair" / "pair-sv-foe.png"
    pair_player = SHOTS / "current_pair" / "pair-sv-player.png"
    o_foe = ORIENT / "shots" / "o-sv-foe.png"
    o_player = ORIENT / "shots" / "o-sv-player.png"
    h = {k: sha256(v) for k, v in (
        ("pair_foe", pair_foe), ("pair_player", pair_player),
        ("o_foe", o_foe), ("o_player", o_player))}

    # 本轮工作区创建时间：晚于它的 .gd 改动才算本轮污染。
    round_start = min((HERE / n).stat().st_mtime for n in (
        "diag_stack.py", "analyze_stack.py", "verify_stack.py"))
    core_sources = [GAME / "scripts" / "arena.gd",
                    GAME / "scripts" / "fighter_3d_layer.gd",
                    GAME / "scripts" / "hud.gd",
                    GAME / "scripts" / "fighter.gd",
                    GAME / "project.godot"]

    checks = {
        # ── 上游四份报告 ────────────────────────────────
        # 不能只信每份报告自己写的 ok：把内部逐条 checks 也独立复核一遍，
        # 否则篡改 checks 里的具体布尔值不会让任何守卫报红（M4 实测）。
        "diag_report_ok": (diag["ok"] and not diag["failed"]
                           and all(diag["checks"].values())),
        "pixel_report_ok": (pix["ok"] and not pix["failed"]
                            and all(pix["checks"].values())),
        "probe_report_ok": (probe["ok"] and not probe["failed"]
                            and all(probe["checks"].values())),
        "pair_report_ok": (pair["ok"] and not pair["failed"]
                           and all(pair["checks"].values())),
        # ── GLB 逐面 UV 反查，点名具体值 ─────────────────
        "diag_shell_count_2809": diag["shell_count"] == 2809,
        "diag_deleted_shells_253": diag["deleted_shells"] == 253,
        "diag_deleted_verts_10495": diag["deleted_verts"] == 10495,
        "diag_cyan_faces_268": diag["cyan_faces"] == 268,
        "diag_cyan_on_deleted_258": diag["cyan_faces_on_deleted"] == 258,
        "diag_cyan_on_kept_10": diag["cyan_faces_on_kept"] == 10,
        "diag_white_faces_zero": diag["white_faces"] == 0,
        "diag_tall_strips_4_all_deleted": (
            diag["tall_strip_shells"] == 4
            and diag["tall_strip_deleted"] == 4),
        "diag_head_344_deleted_211": (
            diag["head_shells"] == 344
            and diag["head_shells_deleted"] == 211),
        "diag_baseline_sha": diag["hashes"]["i_glb"] == GLB_SHA,
        "diag_round2_sha": (
            diag["hashes"]["b_glb"]
            == "96d383eec6286efb1099e9fba617c67c8fefa47a4fb5ff69f0c9abb7933831c5"),
        "diag_uv_v_not_flipped": diag["uv_v_flip"] is False,
        # ── 引擎内五状态像素归因，点名具体值 ──────────────
        "pix_five_states": len(st) == 5,
        "pix_s0_white_725_cyan_424": (
            st["0-orig"]["near_white_px"] == 725
            and st["0-orig"]["cyan_px"] == 424),
        "pix_s1_all_zero": (
            st["1-lights0"]["near_white_px"] == 0
            and st["1-lights0"]["cyan_px"] == 0
            and st["1-lights0"]["bright_px"] == 0),
        "pix_s2_white_73": st["2-nometal"]["near_white_px"] == 73,
        "pix_s3_cyan_0_red_mean": (
            st["3-redalbedo"]["cyan_px"] == 0
            and st["3-redalbedo"]["mean_rgb"][0] > 150),
        "pix_s4_white_668_cyan_449": (
            st["4-neg55"]["near_white_px"] == 668
            and st["4-neg55"]["cyan_px"] == 449),
        "pix_yaw_not_the_cause": (
            st["4-neg55"]["near_white_px"] < 2 * st["0-orig"]["near_white_px"]
            and st["4-neg55"]["cyan_px"] < 2 * st["0-orig"]["cyan_px"]),
        # ── 材质槽位读回 ────────────────────────────────
        "material_one_mesh_one_surface": len(slots) == 1
                                         and slots[0]["surface"] == 0,
        "material_metallic_is_1": slots[0]["metallic"] == 1.0,
        "material_albedo_is_foe": slots[0]["albedo_texture"].endswith(
            "foe-rigged_texture_pbr_20250901.png"),
        "material_no_emission": slots[0]["emission_texture"] == "",
        "four_lights": probe["payload"]["lights"] == 4
                       and len(probe["payload"]["light_energy0"]) == 4,
        "final_yaw_neg55": abs(probe["payload"]["yaw"] + 55.0) < 0.01,
        # ── 用户实际运行路径 ────────────────────────────
        "pair_use_3d": pair["payload"]["use_3d"] is True,
        "pair_glb_paths_distinct": p["glb_path"] != f["glb_path"],
        "pair_foe_verts_64059": fm.get("verts") == 64059,
        "pair_player_verts_57934": pm.get("verts") == 57934,
        "pair_albedo_paths_distinct": pm.get("albedo") != fm.get("albedo"),
        "pair_foe_yaw_plus55": abs(f["yaw"] - 55.0) < 0.01,
        "pair_player_yaw_minus55": abs(p["yaw"] + 55.0) < 0.01,
        # ── 历史取证错位的硬证据 ────────────────────────
        "historical_sv_labels_swapped": (
            h["pair_foe"] == h["o_player"]
            and h["pair_player"] == h["o_foe"]),
        "historical_sv_not_selfequal": (
            h["pair_foe"] != h["o_foe"]
            and h["pair_player"] != h["o_player"]),
        # ── 工程只读 ────────────────────────────────────
        "game_glb_unchanged": sha256(
            GAME / "assets" / "3d" / "foe-rigged.glb") == GLB_SHA,
        "game_texture_unchanged": sha256(
            GAME / "assets" / "3d"
            / "foe-rigged_texture_pbr_20250901.png") == TEX_SHA,
        "game_sources_untouched": all(
            q.is_file() and q.stat().st_mtime < round_start
            for q in core_sources),
        # ── 单层对照（杜绝多 viewport 标签错位）───────────
        "single_report_ok": (single["ok"] and not single["failed"]
                             and all(single["checks"].values())),
        "single_foe_white_725_cyan_424": (
            sr["foe"]["pixels"]["near_white_px"] == 725
            and sr["foe"]["pixels"]["cyan_px"] == 424),
        "single_player_white_13902_cyan_2611": (
            sr["player"]["pixels"]["near_white_px"] == 13902
            and sr["player"]["pixels"]["cyan_px"] == 2611),
        "single_player_white_ratio_31pct": (
            sr["player"]["pixels"]["white_ratio"] > 0.30),
        "single_foe_sha_matches_5state_s0": (
            sr["foe"]["png_sha256"]
            == sha256(SHOTS / "stack_probe" / "s-0-orig.png")),
        "single_two_glbs_distinct": (
            sr["foe"]["png_sha256"] != sr["player"]["png_sha256"]),
        # ── World3D 共享 A/B：用户「两人重叠」的真因 ──────
        "w3d_report_ok": (w3d["ok"] and not w3d["failed"]
                          and all(w3d["checks"].values())),
        "w3d_before_both_world3d_null": all(
            wb[k]["world3d_id"] == 0 and wb[k]["own_world_3d"] is False
            for k in ("player", "foe")),
        "w3d_before_both_white": (
            wb["player"]["pixels"]["near_white_px"] == 17602
            and wb["foe"]["pixels"]["near_white_px"] == 14643),
        "w3d_after_world3d_distinct": (
            wa["player"]["world3d_id"] != wa["foe"]["world3d_id"]
            and 0 not in (wa["player"]["world3d_id"],
                          wa["foe"]["world3d_id"])),
        "w3d_after_foe_white_937": (
            wa["foe"]["pixels"]["near_white_px"] == 937),
        "w3d_after_player_white_13197": (
            wa["player"]["pixels"]["near_white_px"] == 13197),
        "w3d_after_foe_matches_single_foe": (
            abs(wa["foe"]["pixels"]["opaque_px"]
                - sr["foe"]["pixels"]["opaque_px"]) < 500),
        # P0 阶段不许偷改游戏源码；修复落地后本条要按设计转红并更新判据。
        "game_source_not_yet_patched": (
            "own_world_3d" not in
            (GAME / "scripts" / "fighter_3d_layer.gd").read_text(
                encoding="utf-8")),
        # ── 图板 ────────────────────────────────────────
        "board_diag_written": (BOARDS / "B-asset-layer-ownership.png").is_file(),
        "board_pixels_written": (BOARDS / "B-asset-layer-analysis.png").is_file(),
    }
    failed = [k for k, v in checks.items() if not v]
    report = {
        "checks": checks, "failed": failed,
        "total": len(checks), "passed": len(checks) - len(failed),
        "sha256_crosscheck": h,
        "conclusion": (
            "用户『两个人物重叠』的真因是接线层：两个 SubViewport 未设 "
            "own_world_3d，共用父 World3D，每个视口都把两个 GLB 角色画进去"
            "（before：两层近白 17,602 / 14,643）。各设独立 World3D 后"
            "foe 视口近白塌到 937、player 视口保持 13,197，与单层探针逐项吻合，"
            "视觉上重叠消失。J/B 路线一直改 foe GLB 是方向错误；"
            "B round2 删壳本身也做对了（253 壳 / 10,495 顶点，青面 96% 命中）。"
            "历史 o-sv-*.png 与 pair-sv-*.png 的 sha256 对调不是标签写反，"
            "而是「图内容由 yaw 决定、不由层决定」的必然结果。"),
        "ok": not failed,
    }
    (D / "verify_stack.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for k in failed:
        print("FAIL", k)
    print(f"VERIFY_STACK {report['passed']}/{report['total']} "
          + ("ALL GREEN" if report["ok"] else "FAILED"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
