"""对手怪 Blender 建模阶段的承重判据。

只证明：图生 3D 用的是已定稿的 2D 设计、产物结构被如实记录、
Blender 里真的建出了归一化模型 + 13 骨 + 100% 刚性权重 + 可编辑 .blend、
五张渲染与玩家 V4b 同相机、自动绑骨 0 覆盖与撕裂风险没有被包装成通过、
游戏源码没动。

不证明：模型好看、变形可用、能进 Godot、glTF 可导、228 帧图集成立。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
DESIGN = BAKE / "foe-2d-design-preview" / "foe-full-clean.png"
V4B_RENDER = BAKE / "3d-model-probe-v4b" / "render_v4b.json"
LOG = HERE / "verify_foe_build.log"
RESULT = HERE / "verify_foe_build_result.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jload(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def colors(p: Path) -> int:
    with Image.open(p) as f:
        small = f.convert("RGB").resize((120, 120), Image.Resampling.BILINEAR)
    px = list(small.get_flattened_data() if hasattr(small, "get_flattened_data")
              else small.getdata())
    return len(set(px))


def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    probe = jload(HERE / "probe_report.json")
    insp = jload(HERE / "model_inspection.json")
    build = jload(HERE / "blender_build.json")
    rig = jload(HERE / "rigfit_result.json")
    deform = jload(HERE / "deform_probe.json")
    sil = jload(HERE / "silhouette_stats.json")

    # 1 图生 3D 用的是定稿设计，且断连后只查原 job 没重提
    check("image_probe_no_resubmit_and_done",
          probe.get("mode") == "image-to-3D"
          and probe.get("status") == "DONE"
          and probe.get("resumed_after_connection_drop") is True
          and probe.get("transient_queries") == 0
          and len(probe.get("artifacts", [])) == 4
          and bool(probe.get("glb")),
          f"job={probe.get('job_id')} status={probe.get('status')} "
          f"artifacts={len(probe.get('artifacts', []))}")

    # 2 输入图就是工程师看过的那张（抹水印版），sha256 对得上
    check("input_image_is_approved_design",
          probe.get("input_image", {}).get("sha256") == sha(DESIGN)
          and probe.get("prompt") is None,
          f"sha={sha(DESIGN)[:12]} prompt={probe.get('prompt')}")

    glb = HERE / probe["glb"]
    check("glb_signature_and_structure_honest",
          glb.read_bytes()[:4] == b"glTF"
          and insp.get("vertices_total", 0) > 0
          and insp.get("triangles_total", 0) > 0
          and insp.get("counts", {}).get("skins") == 0
          and insp.get("counts", {}).get("animations") == 0
          and insp.get("connected_shells_unionfind", 0) > 0,
          f"{insp.get('vertices_total')} verts / {insp.get('triangles_total')} tris / "
          f"{insp.get('connected_shells_unionfind')} shells / 0 skins")

    tok = insp.get("fbx_token_counts", {})
    rig_tokens = ("LimbNode", "Deformer", "Skin", "Skeleton", "BindPose", "Animation")
    check("fbx_has_no_rig_data",
          all(tok.get(k, -1) == 0 for k in rig_tokens),
          f"tokens={{{', '.join(f'{k}:{tok.get(k)}' for k in rig_tokens)}}}")

    n = build["normalize"]
    check("blender_normalized_to_game_bridge",
          abs(n["bbox_min"][2]) < 1e-3 and abs(n["bbox_max"][2] - 1.72) < 1e-3
          and n["scale"] > 0
          and abs(build["raw"]["verts"] - insp["vertices_total"]) < 1,
          f"z=[{n['bbox_min'][2]}, {n['bbox_max'][2]}] scale={n['scale']}")

    a = build["armature"]
    check("armature_13_bones_full_rigid_coverage",
          a["bones"] == 13 and a["coverage"] == 1.0
          and a["assigned"] == a["total"] == insp["vertices_total"],
          f"bones={a['bones']} coverage={a['coverage']} "
          f"assigned={a['assigned']}/{a['total']}")

    blend = HERE / build["blend_file"]["file"]
    # Blender 5.2.3 默认把 .blend 存成 zstd 压缩：头 4 字节是 28 B5 2F FD，
    # 不是老格式的 b"BLENDER"。按老魔数判会红，但文件没坏 —— 更硬的证据是
    # probe_deform.py 真的 open_mainfile 打开过它并驱动骨架渲了一张图。
    head = blend.read_bytes()[:4] if blend.is_file() else b""
    reopened = (deform.get("blend") == blend.name
                and deform.get("vertices") == insp["vertices_total"]
                and (HERE / deform["render"]["file"]).is_file())
    check("blend_file_is_real_editable_asset",
          blend.is_file() and blend.stat().st_size > 1_000_000
          and head == b"\x28\xb5\x2f\xfd" and reopened,
          f"{blend.name} {blend.stat().st_size} B head={head.hex()} "
          f"reopened_by_blender={reopened}")

    shots = build["shots"]
    render_ok = True
    for s in shots:
        p = HERE / s["file"]
        render_ok &= (p.is_file()
                      and list(Image.open(p).size) == [s["resolution"]] * 2
                      and colors(p) > 300
                      and p.stat().st_size == s["bytes"])
    check("five_renders_valid_and_nonblank", len(shots) == 5 and render_ok,
          f"shots={len(shots)} files={[s['file'] for s in shots]}")

    v4b = {s["shot"]: s for s in jload(V4B_RENDER)["shots"]}
    keys = ("angle_deg", "target_z", "ortho_scale", "resolution")
    same = all(s["shot"] in v4b and all(s[k] == v4b[s["shot"]][k] for k in keys)
               for s in shots)
    check("camera_params_match_player_v4b", same,
          "; ".join(f"{s['shot']}:{s['angle_deg']}/{s['target_z']}/{s['ortho_scale']}"
                    for s in shots))

    auto = rig["automatic_weights"]
    check("auto_weights_honestly_zero",
          auto["coverage"] == 0.0 and auto["covered_vertices"] == 0
          and auto["total_vertices"] == insp["vertices_total"],
          f"covered={auto['covered_vertices']}/{auto['total_vertices']}")

    check("deform_probe_shows_motion_and_caveat",
          deform["moved_vertices_gt_0_1mm"] > 0
          and deform["max_displacement_m"] > 0
          and "不证明变形可用" in deform["caveat"]
          and (HERE / deform["render"]["file"]).is_file(),
          f"moved={deform['moved_vertices_gt_0_1mm']} "
          f"max={deform['max_displacement_m']} m")

    r = sil["ratios"]
    check("silhouette_measured_and_shortfall_not_hidden",
          all(isinstance(v, (int, float)) for v in r.values())
          and sil["goals"]["aspect_bulky_enough"] is False
          and sil["verdict"] == "SILHOUETTE_CONTRAST_SHORT",
          f"lum={r['luminance_foe_over_player']} "
          f"aspect={r['aspect_foe_over_player']} "
          f"shoulder={r['shoulder_foe_over_player']} verdict={sil['verdict']}")

    board = HERE / "player-V4b-foe-3D-comparison.png"
    check("compare_board_valid",
          board.is_file() and list(Image.open(board).size) == [1700, 1060]
          and colors(board) > 300,
          f"{board.name} {board.stat().st_size if board.is_file() else 0} B")

    marker = HERE.stat().st_ctime
    newer = [str(p.relative_to(GAME)) for p in GAME.rglob("*")
             if p.is_file() and ".godot" not in p.parts
             and p.stat().st_mtime > marker]
    no_engine = not list(HERE.glob("*.tscn")) and not list(HERE.glob("*.import"))
    check("game_sources_and_engine_untouched",
          not newer and no_engine, f"newer={newer[:8]} no_engine_files={no_engine}")

    passed = sum(1 for _, o, _ in checks if o)
    verdict = "FOE_BUILD_VERIFIED" if passed == len(checks) else "FOE_BUILD_CHECK_FAILED"
    text = "\n".join(f"{'PASS' if o else 'FAIL'}  {name}  {d}"
                     for name, o, d in checks)
    text += f"\n\n{passed}/{len(checks)} PASS  {verdict}\n"
    LOG.write_text(text, encoding="utf-8")
    RESULT.write_text(json.dumps(
        {"verdict": verdict, "passed": passed, "total": len(checks),
         "checks": [{"name": name, "ok": o, "detail": d}
                    for name, o, d in checks]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
