"""E 路线承重判据：玩家 V4b 的 13 骨 / Voxel 连续壳 / glTF-Godot 读回。

量的不是「好不好看」，是证据链是否成立：
  · 源资产与 UV/PBR 有没有被动过；
  · 2,035 壳是否真塌成 3 壳、SURFACE_DEFORM 是否真 bind 且重开仍能驱动；
  · 72 帧指标是否可从原始逐帧数据独立复算（含劣于对手怪的负结果）；
  · glTF 是否只是静态快照、Godot 里骨架是否只挂在代理壳上；
  · 全程对可运行游戏工程 / C / D 路线归档零污染。

输入解析失败不静默通过：顶层异常记 E-00 并写结果文件，变异脚本才读得到红。
"""
from __future__ import annotations

import ast
import hashlib
import json
import statistics
from pathlib import Path

from PIL import Image, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
C_ROUTE = BAKE / "C路线-glTF-Godot探针"
D_ROUTE = BAKE / "D路线-CreativeReview与引擎截帧"
FRAMES = HERE / "frames"
BOARDS = HERE / "boards"
LOGS = HERE / "logs"
OUT = HERE / "verify_e_result.json"

CHECKS: list[dict] = []


def expect(name: str, cond: bool, detail: str) -> None:
    CHECKS.append({"name": name, "ok": bool(cond), "detail": str(detail)})


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def img_info(p: Path):
    """图片读失败返回 None，绝不抛出去让整轮 verify 崩掉。"""
    try:
        with Image.open(p) as im:
            rgb = im.convert("RGB")
            st = ImageStat.Stat(rgb.resize((128, 128),
                                           Image.Resampling.LANCZOS))
            return {"w": im.width, "h": im.height, "mode": im.mode,
                    "stddev": round(sum(st.stddev) / 3, 3)}
    except Exception as exc:  # noqa: BLE001 - 变异体故意弄坏图片
        return {"error": repr(exc)}


def near(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) <= tol


def recompute_metrics(rows: list[dict]) -> dict:
    """独立重算 analyze_e.py 的口径，不 import 它。"""
    keys = ("tear_p999_m", "tear_gt5cm", "max_displacement_m",
            "moved_gt_1mm", "reach_f_m", "reach_b_m", "reach_max_m",
            "foot_gap_m", "penetration_pct")
    per_tag = {}
    for tag in ("E_x1", "E_x15", "A2_x15_foe"):
        per_tag[tag] = {}
        for k in keys:
            vals = [r[tag][k] for r in rows]
            per_tag[tag][k] = {
                "max": round(max(vals), 6),
                "mean": round(statistics.fmean(vals), 6),
                "min": round(min(vals), 6),
            }
    ratios = []
    for r in rows:
        e, a = r["E_x15"], r["A2_x15_foe"]
        ratios.append({
            "card": r["card"], "frame": r["frame"],
            "tear_ratio": round(e["tear_p999_m"] /
                                max(a["tear_p999_m"], 1e-9), 5),
            "tear_e": e["tear_p999_m"], "tear_a": a["tear_p999_m"],
            "reach_e": e["reach_max_m"], "reach_a": a["reach_max_m"],
        })
    worst = max(ratios, key=lambda x: x["tear_ratio"])
    return {
        "per_tag": per_tag,
        "worst": worst,
        "mean_ratio": round(statistics.fmean(
            x["tear_ratio"] for x in ratios), 5),
        "reach_not_less": sum(
            1 for x in ratios if x["reach_e"] >= x["reach_a"] - 1e-6),
        "tear_better": sum(1 for x in ratios if x["tear_ratio"] < 1.0),
    }


def run_checks() -> None:
    baseline = load(HERE / "baseline_e.json")
    src = load(HERE / "source_probe.json")
    probe = load(HERE / "e_probe.json")
    build = load(HERE / "e_build.json")
    metrics = load(HERE / "metrics_e.json")
    x1 = load(HERE / "x1_shots.json")
    export = load(HERE / "export_e.json")
    gltf = load(HERE / "gltf_e_inspection.json")
    godot = load(HERE / "godot_e_result.json")
    stats = load(HERE / "board_stats_e.json")
    conclusion = load(HERE / "e_conclusion.json")

    # E-01 输入基线：105 个游戏文件 + 10 个单点 + C/D 清单条目数
    drift = []
    for rel, meta in baseline["game"].items():
        p = GAME / rel
        if not p.is_file():
            drift.append("missing:" + rel)
        elif p.stat().st_size != meta["bytes"] or sha256(p) != meta["sha256"]:
            drift.append("changed:" + rel)
    for key, meta in baseline["singles"].items():
        p = Path(meta["path"])
        if not p.is_file():
            drift.append("missing-single:" + key)
        elif p.stat().st_size != meta["bytes"] or sha256(p) != meta["sha256"]:
            drift.append("changed-single:" + key)
    for name, p in (("C", C_ROUTE / "文件清单.txt"),
                    ("D", D_ROUTE / "文件清单.txt")):
        entries = sum(1 for line in p.read_text(encoding="utf-8").splitlines()
                      if line.startswith("WORK/"))
        key = "c_route_filelist" if name == "C" else "d_route_filelist"
        if entries != baseline["singles"][key]["entries"]:
            drift.append("entries:" + name)
    expect("E-01_baseline_inputs_intact", not drift,
           f"game={len(baseline['game'])} singles="
           f"{len(baseline['singles'])} drift={len(drift)} {drift[:3]}")

    # E-02 可运行游戏工程里一个 3D 资产都没有
    exts = ("*.glb", "*.gltf", "*.obj", "*.fbx", "*.blend", "*.dae", "*.vrm")
    found = [str(p.relative_to(GAME)) for e in exts for p in GAME.rglob(e)]
    expect("E-02_game_has_zero_3d_assets", not found,
           f"3d_assets_in_game={len(found)} {found[:3]}")

    # E-03 源 V4b GLB 结构
    s = src["structure"]
    v4b = baseline["singles"]["v4b_glb"]
    height = src["normalize"]["bbox_max"][2] - src["normalize"]["bbox_min"][2]
    expect("E-03_source_asset_structure",
           s["verts"] == 57901 and s["shells"] == 2035
           and s["uv_layers"] == 1 and s["materials"] == 1
           and s["packed_textures"] == 3
           and all(t["size"] == [4096, 4096] for t in s["textures"])
           and Path(src["glb"]["path"]).stat().st_size == v4b["bytes"]
           and sha256(Path(src["glb"]["path"])) == v4b["sha256"]
           and near(height, 1.72, 1e-5),
           f"verts={s['verts']} shells={s['shells']} "
           f"height={height:.5f} pbr={s['packed_textures']}")

    # E-04 链参数两处一致
    pb, pp = build["params"], probe["params"]
    expect("E-04_chain_params_recomputable",
           pb == pp and pb["voxel_size"] == 0.02
           and pb["arm_only_gain"] == 1.5
           and pb["apose_table"] == "player"
           and "SURFACE_DEFORM" in build["method"],
           f"build={pb} probe={pp} method={build['method']}")

    # E-05 Voxel 把 2,035 壳塌成 3 壳
    sh, sr = build["chain"]["shell"], build["chain"]["src"]
    expect("E-05_voxel_shell_collapses_2035_shells",
           sh["shells"] == 3 and sr["shells"] == 2035
           and sh["verts"] == 14070 and sh["faces"] == 28128
           and near(sh["tri_ratio"], 1.0)
           and sh["auto_weight_covered"] == 14062
           and sh["auto_weight_covered"] / sh["verts"] > 0.999,
           f"{sr['shells']} -> {sh['shells']} shells, "
           f"weights={sh['auto_weight_covered']}/{sh['verts']}")

    # E-06 UV / 材质 / 三张 4096² PBR 原样保留
    a, ro = build["chain"]["assets"], build["reopen"]
    packed = export["packed_images"]
    expect("E-06_uv_and_pbr_untouched",
           a["uv_same"] is True and a["textures_same"] is True
           and a["uv_layers"] == 1 and a["materials"] == 1
           and len(a["textures"]) == 3
           and all(t["size"] == [4096, 4096] for t in a["textures"])
           and ro["high_poly_uv_layers"] == 1
           and ro["packed_4096_textures"] == 3
           and ro["textures_4096"] == 3
           and len(packed) == 3
           and all(t["size"] == [4096, 4096] for t in packed),
           f"uv={a['uv_layers']} mats={a['materials']} "
           f"reopen_pbr={ro['textures_4096']}")

    # E-07 SURFACE_DEFORM 绑定且重开后仍在
    b = build["chain"]["bind"]
    expect("E-07_surface_deform_bound_and_reopened",
           b["is_bound"] is True and b["rest_drift_m"] < 1e-5
           and ro["surface_deform_is_bound"] is True
           and ro["surface_deform_target"] == "e_continuous_shell"
           and ro["rig_count"] == 1 and ro["rig_bones"] == 13
           and ro["high_poly_verts"] == 57901,
           f"bound={b['is_bound']} drift={b['rest_drift_m']} "
           f"reopen_target={ro['surface_deform_target']} "
           f"bones={ro['rig_bones']}")

    # E-08 站架恒等
    si, si2 = build["stance_identity"], probe["stance_identity"]
    expect("E-08_stance_is_identity",
           si["identical"] is True and si2["identical"] is True
           and si["max_vertex_delta_m"] < 1e-4
           and si2["max_vertex_delta_m"] < 1e-4,
           f"build={si['max_vertex_delta_m']} probe={si2['max_vertex_delta_m']}")

    # E-09 重开仍能驱动
    drv = ro["reopen_drive_max_displacement_m"]
    expect("E-09_reopen_still_drives",
           drv > 0.8 and drv < 1.0
           and near(drv,
                    max(r["E_x15"]["max_displacement_m"]
                        for r in build["all_frames"]["rows"]), 0.01),
           f"reopen_drive={drv}")

    # E-10 72 帧账本
    af = build["all_frames"]
    cards = af["cards"]
    expect("E-10_72_frames_ledger",
           af["count"] == 72 and len(af["rows"]) == 72
           and cards == {"jab": 14, "cross": 22, "wave": 36}
           and sum(cards.values()) == 72 and metrics["frames"] == 72,
           f"count={af['count']} rows={len(af['rows'])} cards={cards}")

    # E-11 独立重算 27 组统计 + 逐帧比值
    rc = recompute_metrics(af["rows"])
    diffs = []
    for tag, ks in rc["per_tag"].items():
        for k, vals in ks.items():
            for stat, v in vals.items():
                got = metrics["per_tag"][tag][k][stat]
                if not near(got, v):
                    diffs.append(f"{tag}.{k}.{stat}")
    expect("E-11_metrics_recomputed_from_raw_rows",
           not diffs
           and near(rc["mean_ratio"], metrics["mean_tear_ratio"])
           and rc["worst"] == metrics["worst_tear_ratio"]
           and rc["reach_not_less"]
           == metrics["frames_e_reach_not_less_than_foe"]
           and rc["tear_better"]
           == metrics["frames_e_tear_lower_than_foe"],
           f"stat_diffs={len(diffs)} {diffs[:3]} "
           f"worst={rc['worst']['tear_ratio']}")

    # E-12 x1.5 增益确实放大变形
    p1 = metrics["per_tag"]["E_x1"]
    p15 = metrics["per_tag"]["E_x15"]
    expect("E-12_gain_x15_amplifies_deformation",
           p15["max_displacement_m"]["max"]
           > p1["max_displacement_m"]["max"] > 0.5
           and p15["tear_p999_m"]["max"] > p1["tear_p999_m"]["max"]
           and p15["moved_gt_1mm"]["max"] > 57000
           and p15["reach_max_m"]["max"] > p1["reach_max_m"]["max"],
           f"disp x1={p1['max_displacement_m']['max']} "
           f"x15={p15['max_displacement_m']['max']}")

    # E-13 负结果如实保留（不许粉饰成「优于对手怪」）
    board_src = (HERE / "make_boards_e.py").read_text(encoding="utf-8")
    expect("E-13_negative_result_not_sugarcoated",
           metrics["mean_tear_ratio"] > 1.0
           and rc["worst"]["tear_ratio"] > 1.8
           and metrics["frames_e_tear_lower_than_foe"] == 4
           and metrics["frames_e_reach_not_less_than_foe"] == 22
           and conclusion["deformation_verdict"] == "WORSE_THAN_FOE"
           and conclusion["gltf_verdict"] == "static_snapshot_only"
           and "负结果如实保留" in board_src,
           f"mean={metrics['mean_tear_ratio']} "
           f"better={metrics['frames_e_tear_lower_than_foe']}/72 "
           f"verdict={conclusion['deformation_verdict']}")

    # E-14 结论可复算
    full = next(e for e in gltf["exports"] if e["name"] == "player-full")
    calc = ("small_sprite_sample_first"
            if metrics["mean_tear_ratio"] > 1.0
            and full["counts"]["animations"] == 0
            else "godot_rig_layer")
    reasons = conclusion["reasons"]
    expect("E-14_conclusion_recomputable",
           calc == conclusion["recommendation"] == stats["recommendation"]
           and len(reasons) == 4
           and any("SURFACE_DEFORM" in r for r in reasons)
           and any("skeleton_path" in r for r in reasons)
           and conclusion["game_source_changed"] is False
           and conclusion["frames"] == 72
           and conclusion["rig_bones"] == 13,
           f"calc={calc} listed={conclusion['recommendation']} "
           f"reasons={len(reasons)}")

    # E-15 16 张代表帧逐张 sha256 对账
    shots = list(build["shots"]) + list(x1["shots"]) + [
        {"file": src["front_render"]["file"],
         "bytes": src["front_render"]["bytes"],
         "sha256": src["front_render"]["sha256"]}]
    on_disk = sorted(p.name for p in FRAMES.glob("*.png"))
    bad = []
    for shot in shots:
        p = FRAMES / shot["file"]
        if not p.is_file() or p.stat().st_size != shot["bytes"] \
                or sha256(p) != shot["sha256"]:
            bad.append(shot["file"])
    digests = [sha256(FRAMES / n) for n in on_disk]
    expect("E-15_all_16_frames_sha_matched",
           len(shots) == 16 and len(on_disk) == 16 and not bad
           and sorted(s["file"] for s in shots) == on_disk
           and len(set(digests)) == len(digests)
           and all(Image.open(FRAMES / n).size == (768, 768)
                   for n in on_disk),
           f"shots={len(shots)} disk={len(on_disk)} bad={len(bad)} "
           f"distinct={len(set(digests))}")

    # E-16 四张板非空、两两不同、尺寸与清单一致
    infos, board_bad = {}, []
    for b in stats["boards"]:
        p = BOARDS / b["file"]
        info = img_info(p)
        infos[b["file"]] = info
        if (info.get("w") != b["w"] or info.get("h") != b["h"]
                or p.stat().st_size != b["bytes"]
                or info.get("stddev", 0) < 8):
            board_bad.append(b["file"])
    board_sha = [sha256(BOARDS / b["file"]) for b in stats["boards"]]
    expect("E-16_four_boards_shape_and_distinct",
           len(stats["boards"]) == 4 and not board_bad
           and len(set(board_sha)) == 4
           and all(v.get("mode") == "RGB" for v in infos.values()),
           f"bad={board_bad} distinct={len(set(board_sha))}")

    # E-17 板清单 / 磁盘 / 源码接线三方对账
    disk_boards = sorted(p.name for p in BOARDS.glob("E-*.png"))
    disk_frames = sorted(p.name for p in FRAMES.glob("*.png"))
    expect("E-17_board_ledger_and_source_wiring",
           sorted(stats["board_names"]) == disk_boards
           == sorted(b["file"] for b in stats["boards"])
           and stats["frame_files"] == disk_frames
           and "BOARD_LIST_MISMATCH" in board_src
           and "alpha_composite" in board_src,
           f"boards={len(disk_boards)} frames={len(disk_frames)} "
           f"ledger_match={stats['frame_files'] == disk_frames}")

    # E-18 四个 GLB 逐件完好，进 Godot 的三份是逐字节副本
    ex_bad = []
    for e in export["exports"]:
        p = HERE / e["file"]
        if not p.is_file() or p.stat().st_size != e["bytes"] \
                or sha256(p) != e["sha256"]:
            ex_bad.append(e["file"])
    ins = {e["file"]: e for e in gltf["exports"]}
    for c in godot["copies"]:
        p = HERE / c["file"]
        if c["identical"] is not True or sha256(p) != c["sha256"] \
                or p.stat().st_size != c["bytes"]:
            ex_bad.append("copy:" + c["file"])
    for e in export["exports"]:
        if ins[e["file"]]["sha256"] != e["sha256"]:
            ex_bad.append("inspect:" + e["file"])
    expect("E-18_four_glb_exports_intact",
           len(export["exports"]) == 4 and len(godot["copies"]) == 3
           and not ex_bad,
           f"exports={len(export['exports'])} bad={ex_bad}")

    # E-19 skin 只在代理壳，animation 全为 0
    byname = {e["name"]: e for e in gltf["exports"]}
    prims = byname["player-full"]["primitives"]
    skinned = [p for p in prims if "JOINTS_0" in p["attributes"]]
    unskinned = [p for p in prims if "JOINTS_0" not in p["attributes"]]
    expect("E-19_glb_structure_skin_and_animation",
           byname["player-full"]["counts"]["skins"] == 1
           and byname["player-full"]["skin_joints"] == [14]
           and all(e["counts"]["animations"] == 0
                   for e in gltf["exports"])
           and len(skinned) == 1 and skinned[0]["verts"] == 14070
           and len(unskinned) == 1 and unskinned[0]["verts"] == 57934
           and byname["player-proxy-rig"]["counts"]["skins"] == 1
           and byname["player-stance"]["counts"]["skins"] == 0
           and byname["player-cross"]["counts"]["skins"] == 0,
           f"full skins={byname['player-full']['counts']['skins']} "
           f"animations=all0 skinned_verts={skinned[0]['verts']}")

    # E-20 PBR 零重编码
    z = gltf["zero_reencode"]
    imgs = byname["player-full"]["images"]
    packed_sha = {p["sha256"] for p in export["packed_images"]}
    embedded_sha = {i["sha256"] for i in imgs}
    packed_bytes = sum(p["bytes"] for p in export["packed_images"])
    embedded_bytes = sum(i["bytes"] for i in imgs)
    expect("E-20_pbr_zero_reencode",
           z["all_match"] is True and z["full_images"] == 3
           and packed_bytes == embedded_bytes == z["source_bytes"]
           == z["glb_image_bytes"]
           and z["share_of_full_glb"] > 0.9
           and all(i["matches_packed_source"] for i in imgs)
           and embedded_sha == packed_sha
           and byname["player-full"]["pbr"]
           == {"baseColorTexture": 1, "metallicRoughnessTexture": 2,
               "normalTexture": 0},
           f"all_match={z['all_match']} bytes={z['source_bytes']} "
           f"share={z['share_of_full_glb']}")

    # E-21 导出只是当前帧的静态快照
    snap = gltf["static_snapshot"]
    delta = max(
        max(abs(a - b) for a, b in zip(snap["stance_" + side],
                                       snap["cross_" + side]))
        for side in ("pos_min", "pos_max"))
    expect("E-21_export_is_static_snapshot",
           near(delta, snap["max_component_delta_m"], 1e-6)
           and delta > 0.1 and snap["stance_skins"] == 0
           and snap["stance_animations"] == 0
           and byname["player-stance"]["sha256"]
           != byname["player-cross"]["sha256"],
           f"stance_vs_cross_delta={delta:.6f} "
           f"skins={snap['stance_skins']}")

    # E-22 Godot 导入与读回无错
    ei, ip = godot["editor_import"], godot["inspect_probe"]
    expect("E-22_godot_import_clean",
           ei["returncode"] == 0
           and len(ei["import_files"]) == 3
           and all(x["exists"] for x in ei["import_files"])
           and ei["imported_files"] == 12
           and ip["returncode"] == 0 and ip["script_errors"] == 0
           and (godot["engine"]["major"], godot["engine"]["minor"])
           == (4, 5)
           and godot["total_wall_seconds"] > 0,
           f"import_rc={ei['returncode']} imported={ei['imported_files']} "
           f"script_errors={ip['script_errors']}")

    # E-23 Godot 里骨架只挂代理壳，高模不带 skin
    tgt = {t["path"].split("/")[-1]: t for t in godot["targets"]}
    f = tgt["player-full.glb"]
    meshes = {m["name"]: m for m in f["mesh_instances"]}
    bones = f["skeletons"][0]["bone_names_head"] if f["skeletons"] else []
    expect("E-23_godot_skeleton_only_on_proxy",
           len(godot["targets"]) == 3
           and all(t["load_ok"] for t in godot["targets"])
           and all(not t["animation_players"] for t in godot["targets"])
           and "node_0" in meshes and meshes["node_0"]["skeleton_path"] == ""
           and "e_continuous_shell" in meshes
           and meshes["e_continuous_shell"]["skeleton_path"] != ""
           and len(bones) == 14 and "neutral_bone" in bones
           and tgt["player-proxy-rig.glb"]["mesh_instances"][0][
               "skeleton_path"] != "",
           f"targets={len(godot['targets'])} node_0_skeleton="
           f"'{meshes.get('node_0', {}).get('skeleton_path')}' "
           f"bones={len(bones)}")

    # E-24 流水线源码接线（Python 语法必须成立）
    py = {}
    for name in ("e_build.py", "render_e_x1.py", "export_e_gltf.py",
                 "inspect_e_gltf.py", "probe_v4b_source.py",
                 "make_boards_e.py", "analyze_e.py", "run_godot_e.py"):
        text = (HERE / name).read_text(encoding="utf-8")
        py[name] = text
        ast.parse(text)
    gd = (HERE / "probe_project_e" / "probes" /
          "inspect_e.gd").read_text(encoding="utf-8")
    wiring = (
        "SURFACE_DEFORM" in py["e_build.py"]
        and "voxel_remesh" in py["e_build.py"]
        and 'spec["player"]' in py["e_build.py"]
        and "C.pose_frame" in py["render_e_x1.py"]
        and "export_apply=" in py["export_e_gltf.py"]
        and "export_skins=True" in py["export_e_gltf.py"]
        and "--editor" in py["run_godot_e.py"]
        and "inspect_e.gd" in py["run_godot_e.py"]
        and "Skeleton3D" in gd and "AnimationPlayer" in gd)
    expect("E-24_pipeline_source_wiring", wiring,
           f"py_files={len(py)} ast_ok=True wiring={wiring}")

    # E-25 建链/导出/导入日志无错误且非空。
    # 验收自身 stdout 正在写入时是空文件，必须排除（否则判据自指假红）。
    self_logs = {"verify_e.log", "mutation_e.log",
                 "mutation_e_selftest.log", "make_filelist_e.log",
                 "crosscheck_filelist_e.log", "empty_marker_e.log"}
    log_files = sorted(p for p in LOGS.glob("*.log")
                       if p.name not in self_logs)
    noisy = []
    for p in log_files:
        t = p.read_text(encoding="utf-8", errors="replace")
        if not t.strip() or "Traceback" in t or "SCRIPT ERROR:" in t:
            noisy.append(p.name)
    expect("E-25_logs_have_no_errors",
           len(log_files) >= 7 and not noisy,
           f"pipeline_logs={len(log_files)} noisy={noisy}")

    # E-26 前序两条路线仍然绿
    cv = load(C_ROUTE / "verify_c_result.json")
    dv = load(D_ROUTE / "verify_d_result.json")
    expect("E-26_upstream_routes_still_green",
           cv["passed"] == cv["total"] == 25 and not cv["failed"]
           and dv["passed"] == dv["total"] == 18 and not dv["failed"],
           f"verify_c={cv['passed']}/{cv['total']} "
           f"verify_d={dv['passed']}/{dv['total']}")


def main() -> int:
    try:
        run_checks()
    except Exception as exc:  # noqa: BLE001 - 输入坏了也必须写出红结果
        expect("E-00_inputs_parseable", False, repr(exc))
    passed = sum(1 for c in CHECKS if c["ok"])
    failed = [c["name"] for c in CHECKS if not c["ok"]]
    out = {"route": "E", "total": len(CHECKS), "passed": passed,
           "failed": failed, "checks": CHECKS}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for c in CHECKS:
        print(f"{'OK ' if c['ok'] else 'RED'} {c['name']:<44} {c['detail']}")
    print(f"VERIFY_E {passed}/{len(CHECKS)} failed={failed}")
    ok = passed == len(CHECKS) == 26 and not failed
    print("E_VERIFIED" if ok else "E_VERIFY_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
