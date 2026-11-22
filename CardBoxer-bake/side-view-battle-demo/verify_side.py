"""KOF 式侧身战斗 · 承重判据（18 条）。

只钉可复算事实，不评好看；看图结论单写在 side-view-combat-validation-record.txt。
重点钉住四件事：站架偏移来源、动作表侧视语义、两版角色朝向、时长守恒。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
SPEC = BAKE / "combat-motion-design" / "battle_motion_spec.json"
TABLE = BAKE / "baked2.json"
SCRIPT = BAKE / "battle-demo" / "battle_script.json"
BASELINE = BAKE / "combat-motion-design" / "source-baseline.json"
STATS = HERE / "side_battle_stats.json"
SFRAMES = HERE / "side_frames.json"
STANCE = HERE / "side_stance.json"
JOINTS = HERE / "side_joints.json"
ACTION = HERE / "side_action.json"
SPROBE = HERE / "stance_probe.json"
RESULT = HERE / "verify_side_result.json"

SRC_FRAMES = (HERE / "make_side_frames.py").read_text(encoding="utf-8")
SRC_BATTLE = (HERE / "make_side_battle.py").read_text(encoding="utf-8")
SRC_WARP = (HERE / "mesh_warp.py").read_text(encoding="utf-8")

checks: list[dict] = []


def check(name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def diff_px(a, b, crop=None, threshold=18):
    if crop:
        a, b = a.crop(crop), b.crop(crop)
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    return sum(d.histogram()[threshold + 1:])


def main() -> int:
    script, spec, stats = jload(SCRIPT), jload(SPEC), jload(STATS)
    sframes, stance = jload(SFRAMES), jload(STANCE)
    joints, action, sprobe, table = jload(JOINTS), jload(ACTION), jload(SPROBE), jload(TABLE)

    # S01 选组有据：三档都在、S2 的差异确实夹在 S1 与 S3 之间
    cands = stance["candidates"]
    ok_curve = all(
        sprobe["candidates"]["S1"][t]["diff_px_vs_A_pose"]
        < sprobe["candidates"]["S2"][t]["diff_px_vs_A_pose"]
        < sprobe["candidates"]["S3"][t]["diff_px_vs_A_pose"]
        for t in ("player", "foe"))
    check("S01_stance_candidate_curve",
          set(cands) == {"S1", "S2", "S3"} and stance["selected"] in cands
          and ok_curve,
          f"selected={stance['selected']} monotone_diff={ok_curve}")

    # S02 站架帧 == 选中的探针图（逐字节），且 != 原始 A-pose
    bad = []
    for tag in ("player", "foe"):
        f = HERE / "frames" / tag / "stance_f000.png"
        probe = HERE / "frames" / "stance_probe" / f"{tag}-{stance['selected']}.png"
        apose = HERE / "frames" / "stance_probe" / f"{tag}-A-pose.png"
        if not (f.is_file() and probe.is_file()) or sha(f) != sha(probe) \
                or sha(f) == sha(apose):
            bad.append(tag)
    check("S02_stance_frame_equals_selected_probe", not bad,
          f"tags=player,foe byte_identical_bad={bad}")

    # S03 侧视语义：源图翻转、无正视 retarget、hips 恒 0
    no_retarget = ("puppet_mapping" not in SRC_FRAMES
                   and "P.retarget" not in SRC_FRAMES)
    hips_all_zero = all(
        e["action_diag"]["hips_delta_deg"] == 0.0
        for t in ("player", "foe")
        for e in sframes["tags"][t]["manifest"])
    check("S03_side_view_semantics",
          joints["flip_source_horizontally"] is True and no_retarget
          and hips_all_zero and sframes["flip_source_horizontally"] is True,
          f"flip={joints['flip_source_horizontally']} no_retarget={no_retarget} "
          f"hips_zero={hips_all_zero}")

    # S04 局部相对角差：钉真实实现形态 + 动作表确实有超大幅度被分解限幅
    shape_ok = "raw = wrap_deg(world[n] - pw)" in SRC_FRAMES
    worlds = [e["action_diag"]["world_abs_max_deg"]
              for t in ("player", "foe")
              for e in sframes["tags"][t]["manifest"]]
    locals_ = [e["action_diag"]["local_abs_max_deg"]
               for t in ("player", "foe")
               for e in sframes["tags"][t]["manifest"]]
    cap_max = max(action["caps_deg"].values())
    check("S04_local_relative_angle_and_caps",
          shape_ok and max(worlds) > 100.0 and max(locals_) <= cap_max + 1e-6
          and sframes["gain"] == action["gain"]
          and sframes["root_gain"] == action["root_gain"]
          and sframes["caps_deg"] == action["caps_deg"],
          f"shape={shape_ok} world_max={max(worlds)} local_max={max(locals_)} "
          f"cap={cap_max} gain={sframes['gain']}")

    # S05 两版角色朝向：源帧朝右，对手翻一次朝左
    facing = stats["facing"]
    check("S05_facing_rule",
          "flip = side == \"foe\"" in SRC_BATTLE
          and facing["player"] == "right (+x)" and facing["foe"] == "left (-x)"
          and "frames already flipped" in facing["rule"],
          f"player={facing['player']} foe={facing['foe']}")

    # S06 逐帧完整：73 帧 ×2、卡片帧数与 baked2 一致、manifest 指纹与文件一致
    bad = []
    for tag in ("player", "foe"):
        info = sframes["tags"][tag]
        if info["frames"] != 73 or info["cards"] != {
                c: int(table["cards"][c]["frames"]) for c in ("jab", "cross", "wave")}:
            bad.append(f"{tag}:count")
        for e in info["manifest"]:
            p = HERE / "frames" / tag / e["file"]
            if not p.is_file() or sha(p) != e["png_sha256"]:
                bad.append(e["file"])
    check("S06_frames_complete_and_hashed", not bad,
          f"per_tag=73 bad={bad[:4]} total_bad={len(bad)}")

    # S07 时长守恒 + 10ms 整数倍
    g = stats["gif"]
    with Image.open(HERE / g["file"]) as im:
        total = 0
        for i in range(im.n_frames):
            im.seek(i)
            total += im.info.get("duration", 0)
    ok_dur = (total == g["duration_sum_ms"] == g["expected_duration_ms"]
              == stats["total_frames"] * stats["frame_ms"]
              and 0 < g["encoded_frames"] <= g["src_frames"]
              and stats["frame_ms"] % 10 == 0
              and sha(HERE / g["file"]) == g["sha256"])
    check("S07_duration_conservation", ok_dur,
          f"total={total} expected={g['expected_duration_ms']} "
          f"enc={g['encoded_frames']}/{g['src_frames']} frame_ms={stats['frame_ms']}")

    # S08 GIF 逐帧可读且非纯色
    W, H = script["canvas"]
    bad = []
    with Image.open(HERE / g["file"]) as im:
        for i in range(0, im.n_frames, max(1, im.n_frames // 10)):
            im.seek(i)
            rgb = im.convert("RGB")
            if rgb.size != (W, H) or max(ImageStat.Stat(rgb).stddev) < 8:
                bad.append(f"f{i}")
    check("S08_gif_frames_readable", not bad,
          f"canvas={W}x{H} sampled_bad={bad}")

    # S09 hit-stop：f27/f29 几乎相同（只有 HIT! 标签），但 f19 与 f27 差异大
    d = HERE / "frames" / "battle"
    f19 = Image.open(d / "side-battle-f019.png")
    f27 = Image.open(d / "side-battle-f027.png")
    f29 = Image.open(d / "side-battle-f029.png")
    stop_diff = diff_px(f27, f29)
    lead_diff = diff_px(f19, f27)
    check("S09_hitstop_is_three_frames",
          stats["hitstop_frames"] == [28, 29]
          and stats["hit_frame"] == 27
          and stop_diff < 3000 and lead_diff > 5000,
          f"f27_vs_f29={stop_diff}px (<3000) f19_vs_f27={lead_diff}px (>5000)")

    # S10 三回剧本 / 规格绑定 / 血量怒气独立复算
    bad = []
    for r in script["rounds"]:
        wt = r["player_type"] if r["winner"] == "player" else r["foe_type"]
        if (r["attack"] != spec["card_type_binding"][wt]["winner_card"]
                or r["damage"] != spec["damage_tiers"][wt]["base"]
                or r["attack"] not in table["cards"]):
            bad.append(r["n"])
    hp_p = hp_f = script["max_hp"]
    rage_p = rage_f = 0
    track = [{"after_round": 0, "player": hp_p, "foe": hp_f,
              "rage_player": rage_p, "rage_foe": rage_f}]
    for r in script["rounds"]:
        if r["winner"] == "player":
            hp_f -= r["damage"]
            rage_f += script["rage_per_hit"]
        else:
            hp_p -= r["damage"]
            rage_p += script["rage_per_hit"]
        track.append({"after_round": r["n"], "player": hp_p, "foe": hp_f,
                      "rage_player": rage_p, "rage_foe": rage_f})
    check("S10_script_spec_hp_rage", not bad and track == script["hp_track"]
          and stats["hp_track"] == script["hp_track"],
          f"spec_bad={bad} final={track[-1]['player']}:{track[-1]['foe']}")

    # S11 源文件指纹
    src = stats["sources"]
    pairs = {"spec_sha256": SPEC, "table_sha256": TABLE,
             "script_sha256": SCRIPT, "side_joints_sha256": JOINTS,
             "side_stance_sha256": STANCE, "side_action_sha256": ACTION,
             "front_key_sha256": BAKE / "battle-demo" / "frames" / "puppet" / "battle-f069.png"}
    mism = [k for k, p in pairs.items() if src.get(k) != sha(p)]
    check("S11_source_fingerprints", not mism,
          f"checked={len(pairs)} mismatched={mism}")

    # S12 源码接线：钉真实调用形态，不钉注释里也会出现的词
    needles = [
        "duration=frame_ms, loop=0, optimize=False, disposal=1)",
        "lf_eff = HIT_FRAME if lf in HITSTOP else lf",
        "stop=lf in HITSTOP",
        "shadow_layer", "draw_spark", "draw_speed_lines",
        "pulse = max(0.0, 1.0 - abs(t - 0.45) / 0.30)",
        "GROUND_Y", "HITSTOP = (28, 29)",
    ]
    missing = [n for n in needles if n not in SRC_BATTLE]
    check("S12_source_wiring", not missing,
          f"needles={len(needles)} missing={missing}")

    # S13 四张展示板非空
    boards = ["side-view-combat-keyframe-board.png", "side-vs-front-comparison.png",
              "side-view-motion-keyframe-board.png", "three-level-stance-comparison.png"]
    bad = [n for n in boards
           if not (HERE / n).is_file()
           or (HERE / n).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"
           or (HERE / n).stat().st_size < 50000]
    check("S13_boards_nonempty", not bad, f"boards={len(boards)} bad={bad}")

    # S14 连续网格位移场（不是 13 分块仿射）
    check("S14_mesh_warp_wired",
          "warp.warp(src, mats)" in SRC_FRAMES
          and "P.render_frame" not in SRC_FRAMES
          and "Image.Transform.MESH" in SRC_WARP
          and all(sframes["tags"][t]["mesh_grid_count"] == 1024
                  and sframes["tags"][t]["mesh_far_vertices"] > 0
                  for t in ("player", "foe")),
          f"grid={sframes['tags']['player']['mesh_grid_count']} "
          f"far={sframes['tags']['player']['mesh_far_vertices']}")

    # S15 负结果留档：V1 分块版与 V2 大偏移版都要在
    v1 = list((HERE / "frames" / "stance_probe_v1").glob("*.png"))
    v2 = list((HERE / "frames" / "stance_probe_v2").glob("*.png"))
    check("S15_negative_results_archived",
          len(v1) >= 8 and len(v2) >= 8
          and (HERE / "frames" / "stance_probe_v1" / "three-level-stance-comparison-V1.png").is_file()
          and (HERE / "frames" / "stance_probe_v2" / "three-level-stance-comparison-V2.png").is_file(),
          f"v1_png={len(v1)} v2_png={len(v2)}")

    # S16 侧身版与正视版在同一命中帧确实不同（对照不是复制粘贴）
    comp = Image.open(HERE / "side-vs-front-comparison.png").convert("RGB")
    cw = 440
    left = comp.crop((15, 68, 15 + cw, 68 + 250))
    right = comp.crop((15 + cw + 15, 68, 15 + cw + 15 + cw, 68 + 250))
    two_version_diff = diff_px(left, right)
    check("S16_side_differs_from_front", two_version_diff > 20000,
          f"same_hit_frame_diff={two_version_diff}px (>20000)")

    # S17 不宣称完整实现
    check("S17_not_claimed_is_explicit",
          "不是真 3D 蒙皮动画" in action["_not_claimed"]
          and "受击是离线表现层" in script["_not_claimed"]
          and "demo simplification" in script["compare"]
          and stance["_not_claimed"].startswith("这三组不是"),
          f"action_not_claimed_len={len(action['_not_claimed'])}")

    # S18 游戏源码 0 改动
    base = jload(BASELINE)
    game = Path(base["game_dir"])
    changed = [rel for rel, meta in base["files"].items()
               if not (game / rel).is_file()
               or (game / rel).stat().st_size != meta["bytes"]
               or sha(game / rel) != meta["sha256"]]
    check("S18_game_sources_untouched",
          not changed and len(base["files"]) >= 7,
          f"files={len(base['files'])} changed={changed}")

    passed = sum(1 for c in checks if c["ok"])
    result = {"checks": checks, "passed": passed, "total": len(checks),
              "verified": passed == len(checks),
              "diagnostics": {"hitstop_diff_px": stop_diff,
                              "leadin_diff_px": lead_diff,
                              "side_vs_front_diff_px": two_version_diff,
                              "world_abs_max_deg": max(worlds),
                              "local_abs_max_deg": max(locals_)}}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"VERIFY_SIDE {passed}/{len(checks)} "
          f"{'SIDE_BATTLE_VERIFIED' if result['verified'] else 'SIDE_BATTLE_FAILED'}",
          flush=True)
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
