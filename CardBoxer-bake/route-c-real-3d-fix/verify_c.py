"""C 路线（真 3D 连续壳 + 平滑权重）承重判据。

每条判据都要能回答「删掉它声称要防的那段会不会红」。判据不评好不好看：
看图结论单独写在 验证记录 里；这里只钉可复算的几何量、接线、文件完整性。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
FRAMES = HERE / "frames"
BASELINE = BAKE / "combat-motion-design" / "source-baseline.json"
MAPPING = BAKE / "3d-attack-gifs" / "puppet_mapping.json"
RESULT = HERE / "verify_c_result.json"

EXPECTED_BONES = {
    "chest", "forearm_b", "forearm_f", "head", "hips", "neck",
    "shin_b", "shin_f", "spine", "thigh_b", "thigh_f",
    "upperarm_b", "upperarm_f",
}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FRAME_MS = 60

checks: list[dict] = []


def check(name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    build = jload(HERE / "c_build.json")
    gif = jload(HERE / "c_gif_stats.json")
    sweep = jload(HERE / "gain_sweep.json")
    sweep_blender = jload(HERE / "gain_sweep_blender.json")
    src = (HERE / "c_build.py").read_text(encoding="utf-8")

    # C01 源码接线：改动这些调用就不再是连续壳 + 平滑权重路线
    # DATA_TRANSFER 必须钉「带引号的整串字面量」：宽松子串会被
    # "DATA_TRANSFER_X" 这种无效类型名骗过（M5 实测逃逸）。
    needed = ["voxel_remesh()", "ARMATURE_AUTO", '"DATA_TRANSFER"',
              "retarget_delta", "TOLERANCE_M", "--sweep", "arm_only"]
    missing = [s for s in needed if s not in src]
    check("C01_source_wiring", not missing,
          f"needles={len(needed)} missing={missing}")

    # C02 13 骨 A-pose rest
    bones = set(build["rig"]["names"])
    check("C02_apose_13_bones",
          build["rig"]["bones"] == 13 and bones == EXPECTED_BONES,
          f"bones={build['rig']['bones']} names_match={bones == EXPECTED_BONES}")

    # C03 Voxel 连续壳 + 自动权重覆盖
    px = build["proxy"]
    check("C03_voxel_proxy_weights",
          px["voxel_size"] == 0.020
          and px["auto_weight_covered"] / px["verts"] >= 0.999,
          f"voxel={px['voxel_size']} verts={px['verts']} "
          f"covered={px['auto_weight_covered']}")

    # C04 Data Transfer 回传高模的覆盖率 + 真正是「平滑」而非单骨
    fin = build["final"]
    cov = fin["covered"] / fin["verts"]
    multi = fin["multi_bone_vertices"] / fin["verts"]
    check("C04_smooth_weight_coverage",
          cov >= 0.999 and multi >= 0.90,
          f"covered={fin['covered']}/{fin['verts']} ({cov:.5f}) "
          f"multi_bone={fin['multi_bone_vertices']} ({multi:.4f})")

    # C05 UV / 材质 / PBR 贴图逐项保留
    assets = fin["assets"]
    tex_ok = (len(assets["textures"]) == 3
              and all(t["size"] == [4096, 4096] for t in assets["textures"]))
    check("C05_assets_preserved",
          assets["uv_layers"] == 1 and assets["materials"] == 1
          and tex_ok and assets["uv_same"] and assets["textures_same"],
          f"uv={assets['uv_layers']} mat={assets['materials']} "
          f"tex={len(assets['textures'])} same={assets['uv_same']}/{assets['textures_same']}")

    # C06 站架恒等：走完整驱动链后网格不得变形
    si = build["stance_identity"]
    check("C06_stance_identity",
          si["vertices_identical"] is True
          and si["max_vertex_delta_m"] < si["tolerance_m"]
          and si["mean_vertex_delta_m"] < si["tolerance_m"],
          f"max={si['max_vertex_delta_m']} mean={si['mean_vertex_delta_m']} "
          f"tol={si['tolerance_m']}")

    # C07 撕裂改进：同一 jab#8 帧，平滑 vs 刚性
    ab = build["jab8_ab"]
    st, rt = ab["smooth_tear"], ab["rigid_tear"]
    p999_ratio = rt["p999_edge_tear_m"] / st["p999_edge_tear_m"]
    edge_ratio = rt["edges_gt_5cm"] / max(st["edges_gt_5cm"], 1)
    check("C07_tear_improvement",
          p999_ratio >= 8.0 and edge_ratio >= 20.0,
          f"p999 {st['p999_edge_tear_m']} vs {rt['p999_edge_tear_m']} "
          f"(x{p999_ratio:.2f}); >5cm {st['edges_gt_5cm']} vs "
          f"{rt['edges_gt_5cm']} (x{edge_ratio:.2f})")

    # C08 不是「不动」：平滑权重必须真的驱动了几乎全部顶点
    ds = ab["smooth_displacement"]
    check("C08_mesh_actually_moves",
          ds["moved_gt_1mm"] >= 64000 and ds["max_displacement_m"] >= 0.30,
          f"moved={ds['moved_gt_1mm']} max={ds['max_displacement_m']} m")

    # C09 73 张 GIF 帧逐项哈希对账
    shots = build["shots"]
    bad = []
    for s in shots:
        p = FRAMES / s["file"]
        if not p.is_file() or p.stat().st_size != s["bytes"] or sha(p) != s["sha256"]:
            bad.append(s["file"])
    check("C09_shot_hashes",
          len(shots) == 73 and not bad,
          f"shots={len(shots)} mismatched={len(bad)} {bad[:3]}")

    # C10 帧集合完整：72 动作帧 + 5 探针帧 + 21 sweep 帧
    pngs = list(FRAMES.glob("*.png"))
    sw = [p for p in pngs if p.name.startswith("sweep-")]
    check("C10_frame_inventory",
          len(pngs) == 98 and len(sw) == 21,
          f"png={len(pngs)} sweep={len(sw)}")

    # C11 GIF 时长由帧数独立复算，不照抄 stats
    gif_bad = []
    for card in ("jab", "cross", "wave"):
        c = gif["cards"][card]
        p = HERE / c["file"]
        expect = c["frames"] * FRAME_MS
        if (not p.is_file() or sha(p) != c["sha256"]
                or c["duration_sum_ms"] != c["expected_duration_ms"]
                or c["duration_sum_ms"] != expect
                or not (c["frames"] - 4 <= c["encoded_frames"] <= c["frames"])):
            gif_bad.append(card)
    combo = gif["combo"]
    cp = HERE / combo["file"]
    if (not cp.is_file() or sha(cp) != combo["sha256"]
            or combo["duration_sum_ms"] < sum(
                gif["cards"][k]["duration_sum_ms"] for k in ("jab", "cross", "wave"))):
        gif_bad.append("combo")
    check("C11_gif_duration_conservation", not gif_bad,
          f"cards=3 combo=1 bad={gif_bad}")

    # C12 四张展示图非空且尺寸达标
    boards = ["C-route-four-way-comparison-board.png", "C-route-probe-comparison-board.png",
              "real-3d-mesh-keyframe-comparison.png", "gain-pose-comparison-board.png",
              "gain-tearing-tradeoff.png"]
    board_bad = []
    for name in boards:
        p = HERE / name
        b = p.read_bytes() if p.is_file() else b""
        if not (b[:8] == PNG_MAGIC and len(b) > 30000):
            board_bad.append(name)
    check("C12_boards_nonempty", not board_bad,
          f"boards={len(boards)} empty_or_missing={board_bad}")

    # C13 Blender sweep 原始数据：7 档 × 3 卡，mapping 指纹一致
    entries = sweep_blender["sweep"]
    modes = [e["mode"] for e in entries]
    check("C13_sweep_blender_shape",
          len(entries) == 7 and modes.count("all") == 4
          and modes.count("arm_only") == 3
          and all(len(e["rows"]) == 3 for e in entries)
          and sweep_blender["baseline_mapping_sha256"] == sha(MAPPING),
          f"entries={len(entries)} all={modes.count('all')} "
          f"arm_only={modes.count('arm_only')} mapping_sha_ok="
          f"{sweep_blender['baseline_mapping_sha256'] == sha(MAPPING)}")

    # C14 幅度与撕裂随增益单调（从 rows 复算，不读 verdict 文案）
    rows = sweep["rows"]
    mono_bad = []
    for card in ("jab", "cross", "wave"):
        cr = sorted([r for r in rows if r["mode"] == "all" and r["card"] == card],
                    key=lambda r: r["gain"])
        if not all(cr[i]["max_delta_deg"] < cr[i + 1]["max_delta_deg"]
                   for i in range(len(cr) - 1)):
            mono_bad.append(f"{card}:amplitude")
        if not all(cr[i]["p999_edge_tear_m"] < cr[i + 1]["p999_edge_tear_m"]
                   for i in range(len(cr) - 1)):
            mono_bad.append(f"{card}:tear")
    arm = [r for r in rows if r["mode"] == "arm_only"]
    check("C14_sweep_monotonic",
          len(rows) == 21 and len(arm) == 9 and not mono_bad,
          f"rows={len(rows)} arm_only={len(arm)} violations={mono_bad}")

    # C15 全部档位的撕裂都远低于刚性基线，且 verdict 与复算一致
    worst = max(r["p999_edge_tear_m"] for r in rows)
    v = sweep["verdict"]
    rigid = build["jab8_ab"]["rigid_tear"]["p999_edge_tear_m"]
    check("C15_worst_tear_below_rigid",
          worst < rigid / 2.0
          and abs(v["worst_sweep_p999_m"] - worst) < 1e-9
          and abs(v["worst_over_rigid"] - worst / rigid) < 1e-4,
          f"worst={worst} rigid={rigid} ratio={worst/rigid:.4f}")

    # C16 点名已判定的可用区间，防止悄悄放宽到已证伪的档位
    check("C16_usable_gain_range_named",
          v["usable_gain_range"] == "1.0 .. 1.5 (2.0 marginal)"
          and "torso_gain" in v["root_cause"],
          f"range={v['usable_gain_range']!r}")

    # C17 渲染像素指标已退役，只作 diagnostic_only
    check("C17_pixel_metrics_retired",
          len(sweep["rejected_metrics"]) == 2
          and all("diagnostic_only" in r for r in rows)
          and v["primary_amplitude_metric"].startswith("max_delta_deg"),
          f"rejected={len(sweep['rejected_metrics'])} "
          f"primary={v['primary_amplitude_metric']}")

    # C18 游戏源码 0 改动
    base = jload(BASELINE)
    game = Path(base["game_dir"])
    changed = []
    for rel, meta in base["files"].items():
        p = game / rel
        if not p.is_file() or p.stat().st_size != meta["bytes"] or sha(p) != meta["sha256"]:
            changed.append(rel)
    check("C18_game_sources_untouched",
          not changed and len(base["files"]) >= 7,
          f"files={len(base['files'])} changed={changed}")

    passed = sum(1 for c in checks if c["ok"])
    result = {"checks": checks, "passed": passed, "total": len(checks),
              "verified": passed == len(checks)}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"VERIFY_C {passed}/{len(checks)} "
          f"{'C_ROUTE_VERIFIED' if result['verified'] else 'C_ROUTE_FAILED'}",
          flush=True)
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
