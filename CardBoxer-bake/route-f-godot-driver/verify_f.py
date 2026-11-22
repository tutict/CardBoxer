"""F 路线承重判据：Godot 侧 14 骨运行时驱动层。

四层判据，任一 FAIL 即整体验证失败：
  A 源码形状  —— 驱动层必须现算 retarget、不得读烘死 pose/动画
  B 资产      —— player-rigged.glb 带 skin / 14 joints / 0 animations
  C 数值      —— 73 帧三重对账（delta / calc-engine / engine-Blender）
  D 像素      —— 引擎内 9 帧 PNG 真实变化、重复帧确定性、非空白

另外三条边界：
  E 可运行游戏工程零改动（3D 资产数 0）
  F 交付文件清单稳定（不含自身日志/清单）
用法：python verify_f.py
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
DATA = HERE / "data"
PROBE = HERE / "probe_project_f"
SHOTS = HERE / "shots"
LOGS = HERE / "logs"
GAME = BAKE.parent / "CardBoxer"
GAME_BASELINE = BAKE / "route-e-player-3d-rigging" / "baseline_e.json"
# 结论写 logs/（清单已排除）——否则判据自己重写被清单钉住的文件，
# 会让「清单逐项 sha 自洽」永远假绿。
OUT = LOGS / "verify_f.json"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def j(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def changed_px(a: Image.Image, b: Image.Image, thr: int = 6) -> int:
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    m = d.convert("L").point(lambda x: 255 if x > thr else 0)
    return m.histogram()[255]


def mean_abs(a: Image.Image, b: Image.Image) -> float:
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    st = ImageStat.Stat(d)
    return round(sum(st.mean) / 3.0, 4)


def main() -> int:
    checks: dict[str, bool] = {}
    notes: dict = {}

    # ---------- A 源码形状 ----------
    drv = read(PROBE / "scenes" / "rig_driver.gd")
    scene = read(PROBE / "scenes" / "player_driven.gd")
    drive_probe = read(PROBE / "probes" / "probe_drive.gd")
    render_probe = read(PROBE / "probes" / "render_driven.gd")
    motion_in_probe = PROBE / "data" / "motion_input.json"

    checks["A01_driver_exists"] = len(drv) > 3000
    checks["A02_retarget_in_gdscript"] = all(
        k in drv for k in ("func retarget_delta", "func make_points",
                           "wrap_pi", "torso_gain", "arm_gain_deg",
                           "leg_cap_deg", "reach_norm_px"))
    checks["A03_no_baked_pose_in_driver"] = all(
        k not in drv for k in ("rig_frames", "quat_", "animation",
                               "AnimationPlayer", "get_bone_pose_rotation("))
    checks["A04_correct_pose_basis"] = (
        "gr_parent.affine_inverse() * local * gr" in drv
        and "pose_mat = c * gr" in drv)
    checks["A05_z_axis_neg_delta"] = (
        "Quaternion(Vector3(0.0, 0.0, 1.0), theta)" in drv
        and "var theta := -deg_to_rad" in drv)
    checks["A06_13_bones_only"] = (
        "bone_names.size() == 13 and chain.size() == 13" in drv
        and "neutral_bone" in drv)
    checks["A07_scene_preloads_driver"] = (
        'preload("res://scenes/rig_driver.gd")' in scene
        and "RigDriverScript.new()" in scene)
    checks["A08_scene_reads_motion_only"] = (
        'MOTION_PATH := "res://data/motion_input.json"' in scene
        and "rig_frames" not in scene and "AnimationPlayer" not in scene)
    checks["A09_scene_autoplay"] = (
        "auto_play" in scene and "PLAY_FPS" in scene
        and "func apply(index: int)" in scene)
    checks["A10_motion_copy_identical"] = (
        motion_in_probe.is_file()
        and sha256(motion_in_probe) == sha256(DATA / "motion_input.json"))
    checks["A11_drive_probe_has_73"] = (
        '["stance", 0]' in drive_probe
        and 'for card in ["jab", "cross", "wave"]' in drive_probe)
    checks["A12_render_uses_main_scene"] = (
        'SCENE_PATH := "res://scenes/player_driven.tscn"' in render_probe
        and "stage.set(\"auto_play\", false)" in render_probe)
    # 驱动层不得自己 import Blender 侧算法模块
    checks["A13_no_blender_import"] = (
        "import c_build" not in drv and "bpy" not in drv)

    # 独立复算 motion_input 自洽（内联实现，不写任何文件、不依赖
    # Godot / Blender / crosscheck_motion_input.py 的产物 JSON）。
    motion = j(DATA / "motion_input.json")
    frames_ref = j(DATA / "rig_frames.json")["frames"]
    chain, mp = motion["chain"], motion["mapping"]
    st = motion["stance"]

    def lerp2(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def ang(p, q):
        return math.atan2(q[1] - p[1], q[0] - p[0])

    def wrapi(a):
        return (a + math.pi) % (2 * math.pi) - math.pi

    def pts(x):
        hip, sh, hd = x["hip"], x["shoulder"], x["head"]
        return {"A": hip, "B": lerp2(hip, sh, 0.26),
                "C": lerp2(hip, sh, 0.60), "D": sh,
                "E": lerp2(sh, hd, 0.58), "F": hd,
                "f_elbow": x["f_elbow"], "f_hand": x["f_hand"],
                "b_elbow": x["b_elbow"], "b_hand": x["b_hand"],
                "f_knee": x["f_knee"], "f_foot": x["f_foot"],
                "b_knee": x["b_knee"], "b_foot": x["b_foot"],
                "tf_head": (hip[0] + 4.0, hip[1]),
                "tb_head": (hip[0] - 4.0, hip[1])}

    def retarget(fj):
        fp, sp = pts(fj), pts(st)
        raw = {n: math.degrees(wrapi(ang(fp[u], fp[v]) -
                                    ang(sp[u], sp[v])))
               for n, _p, u, v in chain}
        torso = math.degrees(wrapi(ang(fp["A"], fp["D"]) -
                                  ang(sp["A"], sp["D"])))
        used = max(-mp["torso_cap_deg"],
                   min(mp["torso_cap_deg"], torso * mp["torso_gain"]))
        mf = math.dist(fj["f_hand"], st["f_hand"])
        mb = math.dist(fj["b_hand"], st["b_hand"])
        tf = min(1.0, mf / mp["reach_norm_px"])
        tb = min(1.0, mb / mp["reach_norm_px"])
        tw = (min(1.0, min(mf, mb) / mp["wave_min_norm_px"])
              * mp["wave_arm_weight"])
        af, ab = max(tf, tw), max(tb, tw)
        g, cap = mp["arm_gain_deg"], mp["leg_cap_deg"]
        cl = lambda v: max(-cap, min(cap, v))
        return {"hips": 0.0, "spine": used, "chest": 0.0, "neck": 0.0,
                "head": -used * mp["head_compensation"],
                "upperarm_f": -g["f_upper"] * af,
                "forearm_f": -g["f_fore"] * af,
                "upperarm_b": g["b_upper"] * ab,
                "forearm_b": g["b_fore"] * ab,
                "thigh_f": cl(raw["thigh_f"]),
                "shin_f": cl(raw["shin_f"]),
                "thigh_b": cl(raw["thigh_b"]),
                "shin_b": cl(raw["shin_b"])}

    worst_motion = 0.0
    for ref in frames_ref:
        card = ref["card"]
        if card == "stance":
            fj = st
        else:
            fj = motion["cards"][card]["track"][ref["frame"]]
        calc = retarget(fj)
        worst_motion = max(worst_motion, max(
            abs(calc[n] - ref["bones"][n]["delta_deg"])
            for n in motion["bones"]))
    checks["A14_motion_input_recompute"] = worst_motion < 1e-4
    notes["motion_recompute_worst_deg"] = round(worst_motion, 7)

    # ---------- B 资产 ----------
    insp = j(DATA / "rigged_gltf_inspection.json")
    rig = insp["rigged"]
    checks["B01_glb_exists"] = (HERE / "player-rigged.glb").is_file()
    checks["B02_glb_sha_matches_export"] = (
        sha256(HERE / "player-rigged.glb") == rig["sha256"])
    checks["B03_highpoly_has_skin"] = insp["verdict"]["highpoly_has_skin"] is True
    checks["B04_skin_14_joints"] = insp["verdict"]["skin_joints"] == 14
    checks["B05_zero_animations"] = rig["counts"]["animations"] == 0
    checks["B06_images_not_reencoded"] = insp["verdict"]["images_zero_reencode"] is True
    checks["B07_old_glb_highpoly_unskinned"] = (
        insp["verdict"]["reference_highpoly_has_skin"] is False)
    rig_probe = j(DATA / "godot_rig_probe.json")
    checks["B08_godot_import_ok"] = rig_probe["ok"] is True
    checks["B09_godot_14_bones"] = rig_probe["rig"]["bone_count"] == 14
    checks["B10_godot_mesh_skinned"] = all(
        m["skin_present"] and m["skeleton_path"] != ""
        for m in rig_probe["rig"]["meshes"])
    checks["B11_neutral_bone_present"] = any(
        b["name"] == "neutral_bone" for b in rig_probe["rig"]["bones"])

    # ---------- C 数值 ----------
    drive = j(DATA / "godot_drive_probe.json")
    cc_pose = j(DATA / "godot_pose_crosscheck.json")
    checks["C01_drive_probe_ok"] = drive["ok"] is True
    checks["C02_windowed"] = (drive["probe"]["headless"] is False
                              and drive["probe"]["has_opengl"] is True)
    checks["C03_no_script_errors"] = drive["probe"]["script_errors"] == 0
    checks["C04_73_frames"] = drive["result"]["frame_count"] == 73
    checks["C05_73_applied"] = drive["result"]["frames_applied"] == 73
    checks["C06_crosscheck_all_green"] = cc_pose["ok"] is True
    worst = cc_pose["worst"]
    checks["C07_delta_tolerance"] = worst["delta_deg"] < 1e-4
    checks["C08_calc_engine_tolerance"] = worst["calc_vs_engine_m"] < 2e-4
    checks["C09_engine_blender_tolerance"] = worst["engine_vs_blender_m"] < 2e-4
    checks["C10_neutral_untouched"] = (
        cc_pose["checks"]["neutral_bone_untouched"] is True)
    checks["C11_pose_written"] = (
        cc_pose["checks"]["pose_actually_written"] is True)
    checks["C12_root_matches"] = worst["root_m"] < 1e-6
    # 驱动层要真的驱动三卡，不是只跑 stance
    cards = {f["card"] for f in drive["result"]["frames"]}
    checks["C13_three_cards_driven"] = cards == {"stance", "jab", "cross", "wave"}
    nonzero = sum(1 for f in drive["result"]["frames"]
                  if any(abs(v) > 1e-6 for v in f["delta_deg"].values()))
    checks["C14_nonzero_motion_frames"] = nonzero >= 60
    notes["nonzero_motion_frames"] = nonzero

    # ---------- D 像素 ----------
    render = j(DATA / "godot_render_f.json")
    checks["D01_render_ok"] = render["ok"] is True
    checks["D02_no_script_errors"] = render["render"]["script_errors"] == 0
    checks["D03_stage_ready"] = render["stage_ready"] is True
    pngs = render["pngs"]
    checks["D04_nine_shots"] = len(pngs) == 9
    checks["D05_all_png_valid"] = all(
        p["exists"] and p["bytes"] > 20000 and p["save_error"] == 0
        and p["w"] == 900 and p["h"] == 1100 for p in pngs)
    by = {p["name"]: p for p in pngs}
    checks["D06_repeat_byte_identical"] = (
        by["stance-front"]["sha256"] == by["stance-front-repeat"]["sha256"])
    imgs = {name: Image.open(Path(row["path"])) for name, row in by.items()}
    # 每张图都不是纯色 / 空白
    checks["D07_all_nonblank"] = all(
        len(im.convert("RGB").getcolors(maxcolors=1_000_000) or []) > 500
        for im in imgs.values())
    stance = imgs["stance-front"]
    diffs = {}
    for name in ("jab06-front", "cross07-front", "wave17-front",
                 "wave35-front"):
        diffs[name] = {"changed_px": changed_px(stance, imgs[name]),
                       "mean_abs": mean_abs(stance, imgs[name])}
    notes["attack_vs_stance"] = diffs
    checks["D08_attack_pixels_changed"] = all(
        d["changed_px"] > 12000 and d["mean_abs"] > 1.0
        for d in diffs.values())
    yaw_diffs = {}
    for name in ("jab06", "cross07", "wave17"):
        yaw_diffs[name] = changed_px(imgs[name + "-front"],
                                     imgs[name + "-angle35"])
    notes["yaw_changed_px"] = yaw_diffs
    checks["D09_yaw_pixels_changed"] = all(v > 20000 for v in yaw_diffs.values())
    # 三卡互相不同（不是同一帧复制三次）
    pair = {
        "jab_vs_cross": changed_px(imgs["jab06-front"], imgs["cross07-front"]),
        "jab_vs_wave": changed_px(imgs["jab06-front"], imgs["wave17-front"]),
        "cross_vs_wave": changed_px(imgs["cross07-front"], imgs["wave17-front"]),
    }
    notes["card_pair_changed_px"] = pair
    checks["D10_cards_mutually_distinct"] = all(v > 12000 for v in pair.values())
    # 收势帧应回到接近 stance
    back = changed_px(stance, imgs["wave35-front"])
    notes["wave35_vs_stance_changed_px"] = back
    checks["D11_last_frame_returns"] = back < max(
        d["changed_px"] for d in diffs.values())

    # ---------- E 游戏工程零改动 ----------
    game_files = []
    if GAME.is_dir():
        for p in sorted(GAME.rglob("*")):
            if p.is_file() and not any(x in p.parts for x in (".godot", ".git")):
                rel = str(p.relative_to(GAME)).replace("\\", "/")
                game_files.append((rel, sha256(p)))
    notes["game_file_count"] = len(game_files)
    if GAME_BASELINE.is_file():
        base = j(GAME_BASELINE)
        # E 路线基线格式：{"game": {rel_path: {"bytes", "sha256"}}, ...}
        base_map = {k: v["sha256"] for k, v in base["game"].items()}
        cur = dict(game_files)
        drift = sorted(k for k in base_map if cur.get(k) != base_map[k])
        extra = sorted(set(cur) - set(base_map))
        checks["E01_game_unchanged"] = (not drift and not extra
                                        and len(base_map) == 105)
        notes["game_drift"] = drift[:10]
        notes["game_extra"] = extra[:10]
        notes["game_baseline_count"] = len(base_map)
    else:
        checks["E01_game_unchanged"] = False
        notes["game_baseline"] = "absent"
    three_d = [p for p in GAME.rglob("*")
               if p.is_file() and p.suffix.lower() in
               (".glb", ".gltf", ".obj", ".fbx", ".blend", ".dae", ".vrm")]
    checks["E02_game_has_no_3d_asset"] = len(three_d) == 0
    notes["game_3d_asset_count"] = len(three_d)

    # ---------- F 清单稳定 ----------
    fl = HERE / "file-list.txt"
    checks["F01_filelist_exists"] = fl.is_file()
    data_rows = []
    if fl.is_file():
        rows = [l for l in read(fl).splitlines() if l.strip()]
        data_rows = [l for l in rows if not l.startswith("#")]
        checks["F02_filelist_nonempty"] = len(data_rows) >= 20
        notes["filelist_rows"] = len(data_rows)
        # 清单逐项自洽：路径 / 字节 / sha256 都必须与盘上一致。
        bad = []
        for line in data_rows:
            parts = line.split("\t")
            if len(parts) != 3:
                bad.append(line)
                continue
            rel, size, digest = parts
            p = HERE / rel
            if (not p.is_file() or p.stat().st_size != int(size)
                    or sha256(p) != digest):
                bad.append(rel)
        checks["F03_filelist_sha_selfconsistent"] = not bad
        notes["filelist_bad"] = bad[:10]
        # 实际交付文件不能漏进清单（排除项与 make_filelist_f.py 同口径）。
        exclude_names = {"file-list.txt", "new-files.diff"}
        exclude_dirs = {"logs", ".godot", "__pycache__"}
        actual = set()
        for p in HERE.rglob("*"):
            if not p.is_file():
                continue
            relp = p.relative_to(HERE)
            if p.name in exclude_names:
                continue
            if any(x in exclude_dirs for x in relp.parts):
                continue
            actual.add(str(relp).replace("\\", "/"))
        listed = {l.split("\t")[0] for l in data_rows}
        missing = sorted(actual - listed)
        extra_files = sorted(listed - actual)
        checks["F04_filelist_covers_all"] = not missing and not extra_files
        notes["filelist_missing"] = missing[:10]
        notes["filelist_extra"] = extra_files[:10]
    else:
        checks["F02_filelist_nonempty"] = False
        notes["filelist_rows"] = 0
        checks["F03_filelist_sha_selfconsistent"] = False
        checks["F04_filelist_covers_all"] = False
    diff = HERE / "new-files.diff"
    checks["F05_diff_nonempty"] = diff.is_file() and diff.stat().st_size > 10000
    notes["diff_bytes"] = diff.stat().st_size if diff.is_file() else 0

    ok = all(checks.values())
    LOGS.mkdir(parents=True, exist_ok=True)
    failed = [k for k, v in checks.items() if not v]
    OUT.write_text(json.dumps({
        "checks": checks, "failed": failed,
        "total": len(checks), "passed": len(checks) - len(failed),
        "notes": notes, "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k, v in checks.items():
        if not v:
            print(f"  FAIL  {k}")
    print(f"VERIFY_F {len(checks) - len(failed)}/{len(checks)} "
          f"failed={len(failed)}")
    print("F_VERIFIED" if ok else "F_VERIFY_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
