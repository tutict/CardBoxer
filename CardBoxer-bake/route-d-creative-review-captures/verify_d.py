"""D 路线承重判据：Creative Review + 引擎内 3D 截帧。

量的是「证据链是否成立」，不评审美：
  · 渲染必须带窗口（headless 无 frame_post_draw）
  · 六视角必须真有内容且两两不同（不是同一张复制）
  · 六视角只是转相机，不是摆姿势（0 animation 三处对账）
  · 尺度损失用独立重算的 MAE 严格递增来证明
  · D 全程对游戏工程 / C 路线归档零污染
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
C_ROUTE = BAKE / "route-c-gltf-godot-probe"
PROBE = HERE / "probe_project_d"
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"
OUT = HERE / "verify_d_result.json"

CHECKS: list[dict] = []


def expect(name: str, cond: bool, detail: str) -> None:
    CHECKS.append({"name": name, "ok": bool(cond), "detail": detail})


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def img_metrics(p: Path) -> dict:
    im = Image.open(p).convert("RGB")
    st = ImageStat.Stat(im)
    small = im.resize((128, 128), Image.Resampling.LANCZOS)
    raw = small.tobytes()
    colorful = sum(
        1 for i in range(0, len(raw), 3)
        if (max(raw[i], raw[i + 1], raw[i + 2])
            - min(raw[i], raw[i + 1], raw[i + 2])) > 25
    ) / (len(raw) // 3)
    return {
        "w": im.width, "h": im.height,
        "stddev": round(sum(st.stddev) / 3, 3),
        "mean": round(sum(st.mean) / 3, 3),
        "colorful_pct": round(colorful * 100, 3),
    }


def lowfreq(p: Path) -> Image.Image:
    return Image.open(p).convert("RGB").resize(
        (24, 24), Image.Resampling.LANCZOS)


def mae(a: Image.Image, b: Image.Image) -> float:
    return round(sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3, 4)


def fit_h(img: Image.Image, h: int) -> Image.Image:
    return img.resize((max(1, round(img.width * h / img.height)), max(1, h)),
                      Image.Resampling.LANCZOS)


def main() -> int:
    baseline = load(HERE / "baseline_d.json")
    render = load(HERE / "godot_render_result.json")
    stats = load(HERE / "board_stats.json")
    scale = load(HERE / "scale_metrics.json")
    conclusion = load(HERE / "review_conclusion.json")
    baked = load(BAKE / "baked2.json")
    gltf = load(C_ROUTE / "gltf_inspection.json")
    imp = load(C_ROUTE / "godot_import_result.json")
    c_verify = load(C_ROUTE / "verify_c_result.json")
    c_list_bytes = (C_ROUTE / "file-list.txt").read_bytes()
    c_entries = sum(1 for line in c_list_bytes.decode("utf-8").splitlines()
                    if line.startswith("WORK/"))

    # D-01 三处输入指纹
    game_drift = []
    for rel, meta in baseline["game"].items():
        p = GAME / rel
        if not p.is_file():
            game_drift.append("missing:" + rel)
        elif p.stat().st_size != meta["bytes"] or sha256(p) != meta["sha256"]:
            game_drift.append("changed:" + rel)
    clist_ok = (hashlib.sha256(c_list_bytes).hexdigest()
                == baseline["c_route_filelist"]["sha256"]
                and c_entries == baseline["c_route_filelist"]["entries"])
    src_glb = Path(baseline["source_glb"]["path"])
    glb_ok = (src_glb.stat().st_size == baseline["source_glb"]["bytes"]
              and sha256(src_glb) == baseline["source_glb"]["sha256"])
    expect("D-01_baseline_inputs_intact",
           not game_drift and clist_ok and glb_ok,
           f"game_drift={len(game_drift)} clist={clist_ok} glb={glb_ok}")

    # D-02 零污染 + C 路线仍绿
    expect("D-02_game_and_c_route_zero_drift",
           not game_drift and c_verify["total"] == 25
           and c_verify["passed"] == 25 and not c_verify["failed"],
           f"game_drift={len(game_drift)} verify_c="
           f"{c_verify['passed']}/{c_verify['total']}")

    # D-03 渲染通道：必须带窗口 + OpenGL + 零脚本错误
    r = render["render"]
    expect("D-03_render_channel_windowed_opengl",
           r["headless"] is False and r["has_opengl"] is True
           and r["script_errors"] == 0 and r["returncode"] == 0,
           f"headless={r['headless']} gl={r['has_opengl']} "
           f"errs={r['script_errors']} rc={r['returncode']}")

    # D-04 六视角形状
    pngs = render["pngs"]
    expect("D-04_six_views_shape",
           len(pngs) == len(stats["views"]) and render["ok"] is True
           and all(x["exists"] and x["w"] == 900 and x["h"] == 1100
                   and x["save_error"] == 0 and x["bytes"] > 20000
                   for x in pngs),
           f"views={len(pngs)} stats={len(stats['views'])} ok={render['ok']}")

    # D-05 截帧非空且有贴图内容（纯色/空白图会被打红）
    metrics = {}
    for x in pngs:
        p = Path(x["path"])
        metrics[x["name"]] = img_metrics(p) if p.is_file() else {}
    expect("D-05_frames_nonblank_and_textured",
           all(m and m["stddev"] > 8 and m["colorful_pct"] > 0.2
               for m in metrics.values()),
           "min_stddev=%.2f min_colorful=%.3f%%" % (
               min(m.get("stddev", 0) for m in metrics.values()),
               min(m.get("colorful_pct", 0) for m in metrics.values())))

    # D-06 六视角两两不同（复制同一张会被打红）
    lf = {name: lowfreq(HERE / "shots" / f"godot-{name}.png")
          for name in stats["views"]
          if (HERE / "shots" / f"godot-{name}.png").is_file()}
    pairs = []
    names = sorted(lf)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pairs.append((a, b, mae(lf[a], lf[b])))
    min_pair = min((p[2] for p in pairs), default=0.0)
    expect("D-06_views_are_distinct",
           len(pairs) == 15 and min_pair > 0.5,
           f"pairs={len(pairs)} min_lowfreq_mae={min_pair}")

    # D-07 渲染命令里绝不能有 --headless（用 AST 精确定位，不靠子串）
    driver_src = (HERE / "run_godot_render.py").read_text(encoding="utf-8")
    render_cmd = []
    for node in ast.walk(ast.parse(driver_src)):
        if isinstance(node, ast.List):
            vals = [e.value for e in node.elts
                    if isinstance(e, ast.Constant)
                    and isinstance(e.value, str)]
            if "res://probes/render_3d.gd" in vals:
                render_cmd.append(vals)
    expect("D-07_capture_wiring_no_headless",
           len(render_cmd) == 1 and "--headless" not in render_cmd[0]
           and "--resolution" in render_cmd[0]
           and "--quit-after" in render_cmd[0],
           f"render_cmds={len(render_cmd)} "
           f"headless_in_cmd={any('--headless' in c for c in render_cmd)}")

    # D-08 六视角只是转相机（0 animation 三处对账）
    full = next((e for e in gltf["exports"] if e.get("name") == "foe-full"), {})
    # gltf_inspection.json 里 animations 有两种表示：counts.animations 是计数 0，
    # 顶层 animations 是空列表。第一版取错口径把判据判红，这里两处都对账。
    anim_count = full.get("counts", {}).get("animations")
    anim_list = full.get("animations")
    gd_src = (PROBE / "probes" / "render_3d.gd").read_text(encoding="utf-8")
    expect("D-08_camera_only_not_posed",
           anim_count == 0 and anim_list == []
           and conclusion["glb_animations"] == anim_count
           and "set_bone_pose_rotation" not in gd_src
           and "AnimationPlayer" not in gd_src
           and conclusion["six_views_are_camera_only"] is True,
           f"count={anim_count} list={anim_list} "
           f"conclusion={conclusion['glb_animations']} posed_api_in_script="
           f"{'set_bone_pose_rotation' in gd_src}")

    # D-09 PBR 在引擎内可见（灰模会被打红）
    target = next((t for t in imp["targets"]
                   if t["path"].endswith("foe-full.glb")), {})
    tex_ok = all(
        all(mesh["material"][k]["present"]
            and mesh["material"][k]["w"] == 4096
            and mesh["material"][k]["h"] == 4096
            for k in ("albedo", "normal", "metallic", "roughness"))
        for mesh in target.get("mesh_instances", []))
    expect("D-09_pbr_materials_visible",
           tex_ok and metrics.get("front", {}).get("colorful_pct", 0) > 0.5,
           f"four_4096_textures={tex_ok} "
           f"front_colorful={metrics.get('front', {}).get('colorful_pct')}%")

    # D-10 游戏内尺度从 baked2 现算，不是拍脑袋
    char_px = abs(float(baked["stance"]["head"][1])
                  - float(baked["stance"]["f_foot"][1]))
    expect("D-10_game_scale_from_baked2",
           char_px == stats["game_character_px"]
           == conclusion["game_character_px"]
           and int(char_px) in stats["scale_steps"]
           and int(char_px) in [r["target_h"] for r in scale["rows"]],
           f"char_px={char_px} stats={stats['game_character_px']} "
           f"steps={stats['scale_steps']}")

    # D-11 尺度损失独立重算，必须严格递增
    src = Image.open(SHOTS / "godot-front.png").convert("RGB")
    ref = fit_h(src, 400)
    recomputed = [round(mae(fit_h(fit_h(src, h), 400), ref), 4)
                  for h in [row["target_h"] for row in scale["rows"]]]
    stored = [row["mae_vs_direct_400"] for row in scale["rows"]]
    inc = all(a < b for a, b in zip(stored, stored[1:]))
    expect("D-11_scale_loss_monotonic",
           inc and scale["strictly_increasing"] is True
           and scale["baseline_zero"] is True
           and recomputed == stored,
           f"stored={stored} recomputed={recomputed} inc={inc}")

    # D-12 四张板非空、尺寸对账、与磁盘集合一致
    boards = stats["boards"]
    disk = sorted(p.name for p in BOARDS.glob("D-*.png"))
    listed = sorted(b["file"] for b in boards)
    board_ok = all(
        (BOARDS / b["file"]).is_file()
        and (BOARDS / b["file"]).stat().st_size == b["bytes"] > 30000
        and Image.open(BOARDS / b["file"]).size == (b["w"], b["h"])
        for b in boards)
    expect("D-12_four_boards_nonblank",
           len(boards) == 4 and board_ok and disk == listed,
           f"boards={len(boards)} disk={len(disk)} bytes_ok={board_ok}")

    # D-13 Creative Review 结论可复算
    unbound = [m for m in target.get("mesh_instances", [])
               if m.get("skeleton_path") == ""]
    expect("D-13_review_conclusion_recomputable",
           conclusion["verdict"] == "STATIC_ONLY"
           and conclusion["recommendation"] == "B"
           and conclusion["human_visual_review"] is True
           and len(conclusion["reject_C_reasons"]) >= 5
           and conclusion["glb_animations"] == anim_count
           and conclusion["highpoly_unbound_meshes"] == len(unbound)
           and conclusion["scale_mae_strictly_increasing"] is True,
           f"verdict={conclusion['verdict']} rec={conclusion['recommendation']} "
           f"reasons={len(conclusion['reject_C_reasons'])} "
           f"unbound={len(unbound)}")

    # D-14 侧视退化三视角证据齐全且两两不同
    ev = conclusion["side_view_cape"]["evidence_views"]
    ev_files = [SHOTS / f"godot-{n}.png" for n in ev]
    ev_ok = all(p.is_file() for p in ev_files)
    ev_mae = [mae(lowfreq(ev_files[0]), lowfreq(ev_files[1])),
              mae(lowfreq(ev_files[0]), lowfreq(ev_files[2])),
              mae(lowfreq(ev_files[1]), lowfreq(ev_files[2]))] if ev_ok else []
    expect("D-14_side_view_evidence_triplet",
           len(ev) == 3 and ev_ok
           and conclusion["side_view_cape"]["degenerate_at_90deg"] is True
           and conclusion["side_view_cape"]["not_a_floating_shard"] is True
           and len(ev_mae) == 3 and min(ev_mae) > 0.5,
           f"evidence={ev} mae={ev_mae}")

    # D-15 隔离 + 日志洁净
    copy_ok = sha256(PROBE / "assets" / "foe-full.glb") == sha256(src_glb)
    game_glb = [p for p in GAME.rglob("*")
                if p.is_file() and p.suffix.lower() in (".glb", ".gltf")]
    logs = ["godot_render_3d.log", "godot_editor_import_d.log"]
    log_errs = [(n, (HERE / "logs" / n).read_text(
        encoding="utf-8", errors="replace").count("SCRIPT ERROR"))
        for n in logs if (HERE / "logs" / n).is_file()]
    expect("D-15_isolation_and_clean_logs",
           copy_ok and not game_glb
           and str(PROBE) != str(GAME)
           and log_errs and all(c == 0 for _, c in log_errs),
           f"copy={copy_ok} game_glb={len(game_glb)} errs={log_errs}")

    # D-16 源码针脚（9 条）
    board_src = (HERE / "make_review_boards.py").read_text(encoding="utf-8")
    scale_src = (HERE / "measure_scale.py").read_text(encoding="utf-8")
    needles = [
        ("RenderingServer.frame_post_draw", gd_src),
        ("get_viewport().get_texture().get_image()", gd_src),
        ("D_SHOT_DIR", gd_src),
        ("--resolution", driver_src),
        ("--quit-after", driver_src),
        ("RenderingServer.frame_post_draw", driver_src),
        ("ImageChops.difference", scale_src),
        ("BOARD_LIST_MISMATCH", board_src),
        ("review_conclusion.json", board_src),
    ]
    miss = [n for n, text in needles if n not in text]
    expect("D-16_source_wiring", not miss,
           f"needles={len(needles)} missing={miss}")

    # D-17 非生产导入声明
    expect("D-17_not_a_production_import",
           conclusion["verdict"] != "PRODUCTION"
           and "隔离" in driver_src
           and not game_glb and str(PROBE).startswith(str(HERE)),
           f"verdict={conclusion['verdict']} isolated_project={PROBE.name}")

    # D-18 尺度档位与板脚本口径一致
    expect("D-18_scale_steps_aligned",
           [r["target_h"] for r in scale["rows"]] == stats["scale_steps"]
           and scale["source_size"] == [src.width, src.height]
           and scale["display_height"] == 400,
           f"rows={[r['target_h'] for r in scale['rows']]} "
           f"steps={stats['scale_steps']}")

    passed = sum(1 for c in CHECKS if c["ok"])
    failed = [c["name"] for c in CHECKS if not c["ok"]]
    out = {"checks": CHECKS, "total": len(CHECKS), "passed": passed,
           "failed": failed,
           "metrics": {k: {"stddev": v.get("stddev"),
                           "colorful_pct": v.get("colorful_pct")}
                       for k, v in metrics.items()}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for c in CHECKS:
        print(f"{'OK  ' if c['ok'] else 'FAIL'} {c['name']} | {c['detail']}")
    print(f"TOTAL={len(CHECKS)} PASSED={passed} FAILED={failed}")
    print("D_VERIFIED" if passed == len(CHECKS) else "D_VERIFY_FAILED")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
