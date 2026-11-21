"""C 路线承重判据：25 条，全部从盘上产物复算。

纪律（沿用本仓 harness）：
  · 关键结论一律「Blender 结构 vs GLB JSON vs Godot 读回」三处对账；
  · 判空用 GLB magic/version/length + sha256 + 亮度标准差，不看文件后缀；
  · 负结果显式钉住（0 Action / 高模无 skin / headless global pose 未刷新 /
    未做 Creative Review / 资产未进可运行工程）；
  · 不把「导出器告警」当成「通道丢失」：三通道实测都在。
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

from PIL import Image, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
A_ROUTE = BAKE / "A路线-资产重做"
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
PROJECT = HERE / "probe_project"

CHECKS = []
GLB_MAGIC = 0x46546C67


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


def by_name(rows, name):
    return next(r for r in rows if r["name"] == name)


def main() -> int:
    base = load("基线.json")
    bs = load("blend_structure.json")
    exp = load("export_report.json")
    ins = load("gltf_inspection.json")
    godot = load("godot_import_result.json")
    pose = load("godot_pose_result.json")
    a_verify = json.loads(
        (A_ROUTE / "verify_a_result.json").read_text(encoding="utf-8"))
    a_build = json.loads(
        (A_ROUTE / "a_build.json").read_text(encoding="utf-8"))

    exports = {r["name"]: r for r in ins["exports"]}
    full = exports["foe-full"]
    stance = exports["foe-stance"]
    posed = exports["foe-posed"]
    proxy = exports["foe-proxy-rig"]

    # --- A. 输入与零污染 --------------------------------------------------
    drift = [k for k, m in base["inputs"].items()
             if not (BAKE / k).is_file() or sha256(BAKE / k) != m["sha256"]]
    expect("C-01_baseline_inputs_intact", not drift and not base["missing"],
           f"checked={len(base['inputs'])} drift={drift} "
           f"missing={base['missing']}")

    gdrift = [k for k, m in base["game"].items()
              if not (GAME / k).is_file() or sha256(GAME / k) != m["sha256"]]
    expect("C-02_game_source_unchanged", not gdrift,
           f"checked={len(base['game'])} drift={gdrift}")

    blend_hashes = {
        "baseline": base["inputs"]["A路线-资产重做/对手怪-可变形连续壳.blend"]["sha256"],
        "a_build": a_build["export"]["sha256"],
        "export_report": exp["blend_sha256"],
        "structure": bs["blend_sha256"],
        "inspection": ins["source_blend"]["sha256"],
    }
    expect("C-03_source_blend_single_truth",
           len(set(blend_hashes.values())) == 1,
           f"hashes={ {k: v[:12] for k, v in blend_hashes.items()} }")

    expect("C-04_a_route_guard_still_green",
           a_verify["total"] == 26 and a_verify["passed"] == 26
           and not a_verify["failed"],
           f"total={a_verify['total']} passed={a_verify['passed']} "
           f"failed={a_verify['failed']}")

    # --- B. 源资产结构 ----------------------------------------------------
    objs = {o["name"]: o for o in bs["objects"]}
    hi = next(o for o in bs["objects"]
              if any(m["type"] == "SURFACE_DEFORM" for m in o["modifiers"]))
    shell = next(o for o in bs["objects"]
                 if any(m["type"] == "ARMATURE" for m in o["modifiers"]))
    arm = next(o for o in bs["objects"] if o["type"] == "ARMATURE")
    struct_ok = (len(bs["objects"]) == 6 and arm["bones"] == 13
                 and bs["action_count"] == 0 and len(bs["images"]) == 3
                 and all(i["size"] == [4096, 4096] and i["packed"]
                         for i in bs["images"])
                 and hi["verts"] == 64024 and shell["verts"] == 20204)
    expect("C-05_blend_structure_diagnosis", struct_ok,
           f"objects={len(bs['objects'])} bones={arm['bones']} "
           f"actions={bs['action_count']} packed4096={len(bs['images'])} "
           f"hi={hi['verts']} shell={shell['verts']}")

    api = bs["gltf_export_props_available"]
    expect("C-06_gltf_exporter_available",
           bs["gltf_export_poll"] and len(api) == 16
           and all(api.values()),
           f"poll={bs['gltf_export_poll']} props={len(api)} "
           f"missing={[k for k, v in api.items() if not v]}")

    # --- C. GLB 文件与结构 ------------------------------------------------
    bad = []
    for r in exp["exports"]:
        p = HERE / r["file"]
        if not p.is_file():
            bad.append((r["file"], "missing"))
            continue
        data = p.read_bytes()
        magic, version, length = struct.unpack_from("<III", data, 0)
        if not (magic == GLB_MAGIC and version == 2 and length == len(data)):
            bad.append((r["file"], "header"))
        elif sha256(p) != r["sha256"]:
            bad.append((r["file"], "sha"))
        elif r["operator_result"] != ["FINISHED"]:
            bad.append((r["file"], "operator"))
    expect("C-07_glb_files_intact", len(exp["exports"]) == 4 and not bad,
           f"exports={len(exp['exports'])} bad={bad}")

    expect("C-08_foe_full_glb_shape",
           full["counts"]["meshes"] == 2 and full["counts"]["skins"] == 1
           and full["counts"]["animations"] == 0
           and full["counts"]["images"] == 3
           and full["skinned_primitives"] == 1
           and full["vertex_total"] > 80000,
           f"meshes={full['counts']['meshes']} skins={full['counts']['skins']} "
           f"anims={full['counts']['animations']} imgs={full['counts']['images']} "
           f"skinned={full['skinned_primitives']} verts={full['vertex_total']}")

    hi_p = [m for m in full["meshes"]
            if m["position"] and m["position"]["count"] > 60000]
    sh_p = [m for m in full["meshes"]
            if m["position"] and m["position"]["count"] < 30000]
    expect("C-09_highpoly_has_no_skin_attrs",
           len(hi_p) == 1 and len(sh_p) == 1
           and not hi_p[0]["has_skin_attrs"]
           and sh_p[0]["has_skin_attrs"]
           and "JOINTS_0" in sh_p[0]["attributes"],
           f"highpoly_attrs={hi_p[0]['attributes'] if hi_p else []} "
           f"shell_attrs={sh_p[0]['attributes'] if sh_p else []}")

    tc = ins["texture_cost"]
    expect("C-10_textures_not_reencoded",
           tc["glb_full_image_bytes_total"] == tc["source_packed_bytes_total"]
           and tc["glb_full_image_count"] == 3
           and 0.85 <= tc["image_share_of_glb"] <= 0.95,
           f"src={tc['source_packed_bytes_total']} "
           f"glb={tc['glb_full_image_bytes_total']} "
           f"share={tc['image_share_of_glb']}")

    mat0 = full["materials"][0]
    expect("C-11_pbr_channels_all_present",
           all(mat0[k] is not None for k in
               ("baseColorTexture", "metallicRoughnessTexture",
                "normalTexture")),
           f"material={mat0}")

    expect("C-12_skin_joint_count_accounting",
           full["skins"][0]["joints"] == arm["bones"] + 1 == 14
           and godot["targets"][0]["skeletons"][0]["bones"] == 14,
           f"glb_joints={full['skins'][0]['joints']} "
           f"blender_bones={arm['bones']} "
           f"godot_bones={godot['targets'][0]['skeletons'][0]['bones']}")

    zero_anims = all(r["counts"]["animations"] == 0
                     for r in ins["exports"])
    expect("C-13_animations_nowhere",
           zero_anims and bs["action_count"] == 0
           and all(len(t["animation_players"]) == 0
                   for t in godot["targets"]),
           f"blend_actions={bs['action_count']} "
           f"glb_anims={[r['counts']['animations'] for r in ins['exports']]} "
           f"godot_players={[len(t['animation_players']) for t in godot['targets']]}")

    pd = ins["pose_delta"]
    expect("C-14_gltf_is_static_snapshot",
           pd["max_abs_delta"] > 0.05
           and stance["counts"]["skins"] == 0
           and posed["counts"]["skins"] == 0
           and stance["counts"]["animations"] == 0
           and posed["counts"]["animations"] == 0,
           f"max_abs_delta={pd['max_abs_delta']} "
           f"vertex_count_equal={pd['vertex_count_equal']} "
           f"stance/posed skins&anims=0")

    # --- D. Godot 导入 ----------------------------------------------------
    ed = godot["editor_import"]
    expect("C-15_editor_import_succeeded",
           ed["returncode"] == 0 and ed["all_import_files_present"]
           and ed["imported_files"] > 0 and ed["imported_bytes"] > 0
           and ed["seconds"] > 0,
           f"rc={ed['returncode']} imports={ed['import_files']} "
           f"imported={ed['imported_files']} files / {ed['imported_bytes']} B "
           f"seconds={ed['seconds']}")

    targets = godot["targets"]
    expect("C-16_all_targets_load_as_packedscene",
           len(targets) == 3
           and all(t["load_ok"] and t["resource_class"] == "PackedScene"
                   for t in targets),
           f"classes={[t['resource_class'] for t in targets]} "
           f"ok={[t['load_ok'] for t in targets]}")

    t0 = targets[0]["types"]
    expect("C-17_foe_full_scene_tree",
           t0.get("MeshInstance3D") == 2 and t0.get("Skeleton3D") == 1
           and t0.get("AnimationPlayer") is None
           and len(targets[0]["mesh_instances"]) == 2,
           f"types={t0}")

    mats = [m["material"] for m in targets[0]["mesh_instances"]]
    tex_ok = all(
        all(m.get(k, {}).get("present")
            and m[k]["w"] == 4096 and m[k]["h"] == 4096
            for k in ("albedo", "normal", "metallic", "roughness"))
        for m in mats)
    expect("C-18_godot_material_textures_4096", tex_ok,
           f"materials={len(mats)} classes={[m.get('class') for m in mats]}")

    mis = targets[0]["mesh_instances"]
    bound = [m for m in mis if m["skeleton_path"] != ""]
    unbound = [m for m in mis if m["skeleton_path"] == ""]
    expect("C-19_skeleton_binding_split",
           len(bound) == 1 and len(unbound) == 1
           and "a_continuous_shell" in bound[0]["name"]
           and "node_0" in unbound[0]["name"],
           f"bound={[m['name'] for m in bound]} "
           f"unbound={[m['name'] for m in unbound]}")

    pmeshes = pose["meshes"]
    expect("C-20_pose_writable_but_highpoly_unbound",
           pose["pose_local_changed"] and pose["skeleton_found"]
           and pose["bone_count"] == 14
           and pose["bound_mesh_count"] == 1
           and pose["unbound_mesh_count"] == 1
           and any(m["skin_present"] for m in pmeshes)
           and any(not m["skin_present"] for m in pmeshes)
           and pose["global_pose_changed_in_headless"] is False,
           f"local_changed={pose['pose_local_changed']} "
           f"bound={pose['bound_mesh_count']} "
           f"unbound={pose['unbound_mesh_count']} "
           f"global_refresh={pose['global_pose_changed_in_headless']}")

    # --- E. 图证、源码与边界 ----------------------------------------------
    boards = ["C-链路成本账.png", "C-四口径对照.png"]
    board_bad = []
    for name in boards:
        p = HERE / name
        if not p.is_file() or p.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            board_bad.append((name, "header"))
            continue
        with Image.open(p) as im:
            sd = ImageStat.Stat(im.convert("L")).stddev[0]
            size = im.size
        if sd < 5 or size[0] < 1000 or size[1] < 750 \
                or p.stat().st_size < 50000:
            board_bad.append((name, round(sd, 2), size))
    expect("C-21_cost_boards_nonblank", not board_bad,
           f"boards={boards} bad={board_bad}")

    src_export = (HERE / "export_gltf.py").read_text(encoding="utf-8")
    src_inspect = (HERE / "inspect_gltf.py").read_text(encoding="utf-8")
    src_driver = (HERE / "run_godot_import.py").read_text(encoding="utf-8")
    src_pose = (PROJECT / "probes" / "pose_probe.gd").read_text(
        encoding="utf-8")
    src_import_gd = (PROJECT / "probes" / "inspect_import.gd").read_text(
        encoding="utf-8")
    needles = [
        ('export_format="GLB"', src_export),
        ("export_apply=apply_modifiers", src_export),
        ('drive_pose(rig, P, table, stance, "cross", 10, 1.5)', src_export),
        ("GLB_MAGIC = 0x46546C67", src_inspect),
        ("def parse_glb(path: Path):", src_inspect),
        ('"--headless", "--editor", "--quit",', src_driver),
        ("sk.set_bone_pose_rotation(idx,", src_pose),
        ("get_bone_pose_rotation(idx)", src_pose),
        ("extends SceneTree", src_import_gd),
    ]
    miss = [n for n, text in needles if n not in text]
    expect("C-22_source_wiring", not miss,
           f"needles={len(needles)} missing={miss}")

    logs = ["godot_editor_import.log", "godot_inspect_probe.log",
            "godot_pose_probe.log"]
    err_hits = [(n, (HERE / "logs" / n).read_text(
        encoding="utf-8", errors="replace").count("SCRIPT ERROR"))
        for n in logs]
    game_glb = [str(p) for p in GAME.rglob("*")
                if p.is_file() and p.suffix.lower() in (".glb", ".gltf")]
    expect("C-23_isolation_and_clean_logs",
           not game_glb and PROJECT.resolve() != GAME.resolve()
           and all(c == 0 for _, c in err_hits),
           f"game_glb={game_glb} err_hits={err_hits} "
           f"project={PROJECT.name}")

    # Creative Review 是主流水线进引擎的前置条件；本轮明确没做，
    # 用「游戏工程零 drift + 工程内无 glb + 探针工程独立」三件套钉住，
    # 防止后来者把这个成本探针误读成已验收的生产导入。
    expect("C-24_not_a_production_import",
           not gdrift and not game_glb
           and "probe_project" == PROJECT.name,
           f"game_drift={len(gdrift)} game_glb={len(game_glb)} "
           f"project={PROJECT.name}")

    three_glb_bytes = sum(c["bytes"] for c in godot["copies"])
    ratio = ed["imported_bytes"] / three_glb_bytes
    expect("C-25_import_volume_same_order",
           0.8 <= ratio <= 1.3 and godot["total_wall_seconds"] > 0,
           f"glb={three_glb_bytes} imported={ed['imported_bytes']} "
           f"ratio={ratio:.4f} wall={godot['total_wall_seconds']}s")

    passed = sum(c["ok"] for c in CHECKS)
    failed = [c["name"] for c in CHECKS if not c["ok"]]
    (HERE / "verify_c_result.json").write_text(
        json.dumps({"checks": CHECKS, "total": len(CHECKS),
                    "passed": passed, "failed": failed},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for c in CHECKS:
        print(f"{'OK  ' if c['ok'] else 'FAIL'} {c['name']} | {c['detail']}")
    print(f"TOTAL={len(CHECKS)} PASSED={passed} FAILED={failed}")
    print("C_VERIFIED" if passed == len(CHECKS) else "C_VERIFY_FAILED")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
