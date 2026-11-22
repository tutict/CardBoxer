"""A 路线承重判据：26 条，全部从盘上产物复算，不读「应该是什么」的注释。

设计纪律（沿用本仓 harness）：
  · 关键倍率一律「汇总表 vs 逐帧 rows 双算」，两边不一致就是真信号；
  · 阈值尽量相对（V2 定稿 / A2 自身基线），不写死实测数字；
  · 两条负结果也要被判据钉住：A1 烘焙不是贴图转移；连续壳只是变形代理，
    不是说原模型 2,809 壳被修好了；
  · 图片「非空」用 PNG 头 + sha256 + 亮度标准差，不用「文件 >N 字节」；
  · 源码级守卫写「赋值 / 调用形态」，不写裸标识符。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")

CHECKS = []
VARIANTS = ("A2_x1", "A2_x15", "V2_V1_base", "V2_V1_gain")
KEYS = ("tear_p999_m", "tear_gt5cm", "max_displacement_m", "moved_gt_1mm",
        "reach_f_m", "reach_b_m", "reach_max_m", "foot_gap_m",
        "penetration_pct")
EXPECTED_LINKS = {
    ("Principled BSDF:BSDF", "Material Output:Surface"),
    ("Image Texture:Color", "Principled BSDF:Base Color"),
    ("Separate Color:Blue", "Principled BSDF:Metallic"),
    ("Separate Color:Green", "Principled BSDF:Roughness"),
    ("Image Texture.001:Color", "Separate Color:Color"),
    ("Normal Map:Normal", "Principled BSDF:Normal"),
    ("Image Texture.002:Color", "Normal Map:Color"),
}


def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expect(name: str, ok: bool, detail: str):
    CHECKS.append({"name": name, "ok": bool(ok), "detail": detail})


def mean(rows, variant, key):
    return sum(r[variant][key] for r in rows) / len(rows)


def worst(rows, variant, key):
    return max(r[variant][key] for r in rows)


def png_ok(rel: str, expected_sha=None, expected_bytes=None, min_bytes=10000):
    p = HERE / rel
    if not p.is_file() or p.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        return False, "header"
    if p.stat().st_size < min_bytes:
        return False, "tiny"
    if expected_bytes is not None and p.stat().st_size != expected_bytes:
        return False, "bytes"
    if expected_sha is not None and sha256(p) != expected_sha:
        return False, "sha"
    return True, "ok"


def nonblank(rel: str, min_stddev=5.0, min_side=600):
    p = HERE / rel
    if not p.is_file():
        return False, 0.0, (0, 0)
    with Image.open(p) as im:
        size = im.size
        sd = ImageStat.Stat(im.convert("L")).stddev[0]
    return (sd > min_stddev and size[0] >= min_side
            and size[1] >= min_side), sd, size


def main() -> int:
    base = load("baseline.json")
    mat = load("material_probe.json")
    bake = load("bake_probe.json")
    sd = load("surfdeform_probe.json")
    report = load("a_build.json")
    metrics = load("metrics_a.json")
    shard = load("shard_stats.json")
    rows = report["all_frames"]["rows"]
    decomp = metrics["decomposition"]

    # --- A. 输入与零污染 --------------------------------------------------
    drift = [k for k, m in base["inputs"].items()
             if not (BAKE / k).is_file() or sha256(BAKE / k) != m["sha256"]]
    expect("A-01_baseline_inputs_intact", not drift and not base["missing"],
           f"checked={len(base['inputs'])} drift={drift} missing={base['missing']}")

    gdrift = [k for k, m in base["game"].items()
              if not (GAME / k).is_file() or sha256(GAME / k) != m["sha256"]]
    expect("A-02_game_source_unchanged", not gdrift,
           f"checked={len(base['game'])} drift={gdrift}")

    # --- B. 源资产诊断与两条可行性探针 ------------------------------------
    mesh = mat["mesh"]
    imgs = [i for i in mat["images"] if i["source"] == "FILE"]
    mesh_ok = (mesh["verts"] == 64024 and mesh["faces"] > 79000
               and mesh["uv_layers"] == 1 and mesh["materials"] == 1
               and len(imgs) == 3 and all(i["packed"] for i in imgs)
               and all(i["size"] == [4096, 4096] for i in imgs)
               and "ARMATURE" in mesh["modifiers"])
    expect("A-03_source_mesh_diagnosis", mesh_ok,
           f"verts={mesh['verts']} faces={mesh['faces']} uv={mesh['uv_layers']} "
           f"packed4096={len(imgs)} mods={mesh['modifiers']}")

    links = {(x["from"], x["to"]) for x in mat["materials"][0]["links"]}
    expect("A-04_pbr_node_links", links == EXPECTED_LINKS,
           f"links={len(links)} missing={sorted(EXPECTED_LINKS - links)[:3]}")

    bi = mat["bake"]
    api_ok = (bi["has_render_bake"] and bi["surfacedeform_bind_poll"] is True
              and bi["smart_uv_poll"] is False
              and bi["use_selected_to_active_attr"] and bi["margin_attr"])
    expect("A-05_bake_api_available", api_ok,
           f"render_bake={bi['has_render_bake']} "
           f"surfacedeform_poll={bi['surfacedeform_bind_poll']} "
           f"smart_uv_poll={bi['smart_uv_poll']}")

    ok, why = png_ok("frames/a1-bake-probe.png", bake["png"]["sha256"],
                     bake["png"]["bytes"])
    nb, nb_sd, _ = nonblank("frames/a1-bake-probe.png", min_side=400)
    expect("A-06_bake_probe_nonblank",
           bool(bake["bake_ok"]) and bake["engine_before"] == "BLENDER_EEVEE"
           and bake["engine_used"] == "CYCLES"
           and bake["image_size"] == [512, 512] and bake["samples"] == 8
           and bake["error"] is None and ok and nb,
           f"bake_ok={bake['bake_ok']} engine={bake['engine_used']} "
           f"png={why} stddev={nb_sd:.2f}")

    chain = report["chain"]
    a1_neg = (bake["use_selected_to_active"] is False
              and chain["assets"]["uv_same"] and chain["assets"]["textures_same"])
    expect("A-07_a1_is_not_texture_transfer", a1_neg,
           f"selected_to_active={bake['use_selected_to_active']} "
           f"uv_same={chain['assets']['uv_same']} "
           f"textures_same={chain['assets']['textures_same']}")

    sh = sd["shell"]
    cov = sh["auto_weight_covered"] / sh["verts"]
    bind = sd["bind"]
    expect("A-08_surfdeform_probe_bind",
           bind["is_bound"] and bind["poll"] and bind["error"] is None
           and bind["rest_drift_m"] < 1e-5 and sh["shells"] <= 5
           and sh["verts"] > 10000 and cov > 0.999,
           f"bound={bind['is_bound']} drift={bind['rest_drift_m']} "
           f"shells={sh['shells']} coverage={cov:.5f}")

    aft = sd["assets_after"]
    expect("A-09_probe_assets_preserved",
           aft["uv_same"] and aft["textures_same"]
           and aft["uv_layers"] == 1 and aft["materials"] == 1
           and len(aft["textures"]) == 3
           and all(t["size"] == [4096, 4096] for t in aft["textures"]),
           f"uv={aft['uv_layers']} tex={len(aft['textures'])} "
           f"same={aft['uv_same']}/{aft['textures_same']}")

    probe_bad = []
    for fr in sd["frames"]:
        rel = "frames/" + fr["png"]["file"]
        o, why = png_ok(rel, fr["png"]["sha256"], fr["png"]["bytes"])
        if not o or fr["metrics"]["penetration_pct"] != 0.0 \
                or fr["metrics"]["moved_gt_1mm"] <= 60000:
            probe_bad.append((fr["png"]["file"], why))
    for key in ("rest_png", "side_png"):
        o, why = png_ok("frames/" + sd[key]["file"], sd[key]["sha256"],
                        sd[key]["bytes"])
        if not o:
            probe_bad.append((sd[key]["file"], why))
    expect("A-10_probe_frames_valid", len(sd["frames"]) == 3 and not probe_bad,
           f"frames={len(sd['frames'])} bad={probe_bad}")

    # --- C. 交付 .blend 与重开驱动 ----------------------------------------
    ex = report["export"]
    blend = HERE / ex["file"]
    expect("A-11_export_blend_intact",
           blend.is_file() and blend.stat().st_size == ex["bytes"]
           and sha256(blend) == ex["sha256"],
           f"bytes={blend.stat().st_size if blend.is_file() else -1} "
           f"expected={ex['bytes']}")

    ro = report["reopen"]
    expect("A-12_reopen_is_driveable",
           ro["surface_deform_is_bound"]
           and ro["surface_deform_target"] == "a_continuous_shell"
           and ro["rig_count"] == 1 and ro["rig_bones"] == 13
           and ro["high_poly_verts"] == chain["src"]["verts"]
           and ro["high_poly_uv_layers"] == 1
           and ro["packed_4096_textures"] == 3
           and ro["reopen_drive_max_displacement_m"] > 0.5,
           f"bound={ro['surface_deform_is_bound']} bones={ro['rig_bones']} "
           f"drive={ro['reopen_drive_max_displacement_m']}")

    # --- D. 全 72 帧变形质量门禁 ------------------------------------------
    shape_ok = (len(rows) == 72
                and report["all_frames"]["cards"]
                == {"jab": 14, "cross": 22, "wave": 36}
                and all(all(v in r and all(k in r[v] for k in KEYS)
                            for v in VARIANTS) for r in rows))
    expect("A-13_frame_shape", shape_ok,
           f"rows={len(rows)} cards={report['all_frames']['cards']}")

    expect("A-14_no_penetration", worst(rows, "A2_x15", "penetration_pct") == 0.0,
           f"worst={worst(rows, 'A2_x15', 'penetration_pct')}")

    fg = worst(rows, "A2_x15", "foot_gap_m")
    fb = worst(rows, "V2_V1_gain", "foot_gap_m")
    expect("A-15_foot_grounded", fg < 0.05 and fg <= fb * 1.05 + 1e-9,
           f"worst_a2={fg} worst_v2={fb} cap=0.05m")

    nn = sum(1 for r in rows
             if r["A2_x15"]["reach_max_m"] >= r["A2_x1"]["reach_max_m"])
    expect("A-16_reach_nonnegative_all_frames", nn == len(rows),
           f"non_negative={nn}/{len(rows)}")

    gain_recalc = (mean(rows, "A2_x15", "reach_max_m")
                   / mean(rows, "A2_x1", "reach_max_m"))
    gain_sum = decomp["reach_mean_A2x15_over_A2x1"]
    expect("A-17_gain_ratio_double_computed",
           abs(gain_recalc - gain_sum) < 0.002 and gain_recalc > 1.3,
           f"rows={gain_recalc:.4f} summary={gain_sum} threshold>1.3")

    tw_recalc = (worst(rows, "A2_x15", "tear_p999_m")
                 / worst(rows, "V2_V1_gain", "tear_p999_m"))
    tm_recalc = (mean(rows, "A2_x15", "tear_p999_m")
                 / mean(rows, "V2_V1_gain", "tear_p999_m"))
    expect("A-18_tear_improved_over_v2",
           abs(tw_recalc - decomp["tear_worst_A2x15_over_V2x15"]) < 0.002
           and abs(tm_recalc - decomp["tear_mean_A2x15_over_V2x15"]) < 0.002
           and 0.5 < tw_recalc < 1.0 and tm_recalc < 1.0,
           f"worst={tw_recalc:.4f} mean={tm_recalc:.4f} "
           f"summary={decomp['tear_worst_A2x15_over_V2x15']}")

    tw = sum(1 for r in rows
             if r["A2_x15"]["tear_p999_m"] <= r["V2_V1_gain"]["tear_p999_m"])
    fw = sum(1 for r in rows
             if r["A2_x15"]["foot_gap_m"] <= r["V2_V1_gain"]["foot_gap_m"])
    rk = sum(1 for r in rows
             if r["A2_x15"]["reach_max_m"]
             >= r["V2_V1_gain"]["reach_max_m"] * 0.95)
    expect("A-19_ab_counts_double_computed",
           tw == metrics["tear_wins_frames"] and fw == metrics["foot_wins_frames"]
           and rk == metrics["reach_kept_frames"]
           and tw >= 60 and fw == len(rows) and rk == len(rows),
           f"tear={tw}/{metrics['tear_wins_frames']} "
           f"foot={fw}/{metrics['foot_wins_frames']} "
           f"reach={rk}/{metrics['reach_kept_frames']}")

    parity_recalc = (mean(rows, "A2_x15", "reach_max_m")
                     / mean(rows, "V2_V1_gain", "reach_max_m"))
    expect("A-20_reach_parity_no_loss",
           abs(parity_recalc - decomp["reach_mean_A2x15_over_V2x15"]) < 0.002
           and 0.98 <= parity_recalc <= 1.02,
           f"rows={parity_recalc:.4f} "
           f"summary={decomp['reach_mean_A2x15_over_V2x15']}")

    # --- E. 图证与源码接线 ------------------------------------------------
    shot_bad = []
    for s in report["shots"]:
        o, why = png_ok("frames/" + s["file"], s["sha256"], s["bytes"])
        if not o:
            shot_bad.append((s["file"], why))
    names = {s["file"] for s in report["shots"]}
    required = {f"a-{n}-x15.png" for n in
                ("stance", "jab01", "jab07", "jab13", "cross01", "cross11",
                 "cross21", "wave01", "wave18", "wave35")}
    required |= {"a-jab07-x1.png", "a-cross11-x1.png", "a-wave18-x1.png",
                 "a-stance-angle55.png"}
    tags = {s["tag"] for s in report["shots"]}
    expect("A-21_shot_files_intact",
           not shot_bad and len(report["shots"]) == 14
           and required <= names and tags == {"A2_x1", "A2_x15"},
           f"shots={len(report['shots'])} bad={shot_bad} "
           f"missing={sorted(required - names)}")

    boards = ["A-original-vs-reworked-board.png", "A-keyframe-board.png",
              "A-single-variable-gain-comparison.png", "A-waist-panel-detail.png"]
    board_bad = []
    for name in boards:
        # 斜片特写是 1044x526 的横向裁切，不能套主板的 600px 方图下限。
        nb, sdv, size = nonblank(name, min_side=400 if "特写" in name else 600)
        if not nb or (HERE / name).stat().st_size < 50000:
            board_bad.append((name, round(sdv, 2), size))
    expect("A-22_boards_nonblank", not board_bad,
           f"boards={len(boards)} bad={board_bad}")

    src = (HERE / "a_build.py").read_text(encoding="utf-8")
    nums = {
        "voxel_size": float(re.search(r"^VOXEL\s*=\s*([\d.]+)", src, re.M).group(1)),
        "arm_only_gain": float(re.search(r"^ARM_GAIN\s*=\s*([\d.]+)", src, re.M).group(1)),
    }
    expect("A-23_params_match_source",
           all(abs(report["params"][k] - v) < 1e-9 for k, v in nums.items()),
           f"report={report['params']} source={nums}")

    bake_src = (HERE / "probe_bake.py").read_text(encoding="utf-8")
    sd_src = (HERE / "probe_surfdeform.py").read_text(encoding="utf-8")
    needles = [
        ('src.modifiers.new("follow_continuous_shell", "SURFACE_DEFORM")', src),
        ("bpy.ops.object.surfacedeform_bind(modifier=sd.name)", src),
        ("C.pose_frame(ch[\"rig\"]", src),
        ("bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND), compress=True)", src),
        ("scene.render.engine = \"CYCLES\"", bake_src),
        ("bpy.ops.object.surfacedeform_bind(modifier=sd.name)", sd_src),
        ('"variants": VARIANTS', (HERE / "analyze_a.py").read_text(encoding="utf-8")),
    ]
    miss = [n for n, text in needles if n not in text]
    expect("A-24_source_wiring", not miss,
           f"needles={len(needles)} missing={miss}")

    src_shells = chain["src"]["shells"]
    expect("A-25_original_topology_not_claimed_fixed",
           mat["mesh"]["shells"] == src_shells == 2809
           and chain["shell"]["shells"] == 3
           and ro["high_poly_verts"] == chain["src"]["verts"] == 64024,
           f"source_shells={mat['mesh']['shells']} "
           f"delivered_shells={src_shells} proxy_shells={chain['shell']['shells']} "
           f"high_poly_verts={ro['high_poly_verts']}")

    # 腰间斜片特写的裁剪统计只作定位证据，不是几何质量门禁；
    # 但仍要求它真的量到了两侧差异，防止「空裁剪框」冒充证据。
    expect("A-26_shard_closeup_measured",
           shard["bright_pixels_v2"] > shard["bright_pixels_a2"] > 0
           and len(shard["box"]) == 4,
           f"v2={shard['bright_pixels_v2']} a2={shard['bright_pixels_a2']}")

    passed = sum(c["ok"] for c in CHECKS)
    failed = [c["name"] for c in CHECKS if not c["ok"]]
    (HERE / "verify_a_result.json").write_text(
        json.dumps({"checks": CHECKS, "total": len(CHECKS),
                    "passed": passed, "failed": failed},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for c in CHECKS:
        print(f"{'OK  ' if c['ok'] else 'FAIL'} {c['name']} | {c['detail']}")
    print(f"TOTAL={len(CHECKS)} PASSED={passed} FAILED={failed}")
    print("A_VERIFIED" if passed == len(CHECKS) else "A_VERIFY_FAILED")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
