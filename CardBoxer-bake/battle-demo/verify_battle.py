"""《牌拳》三回卡牌对战离线表演 · 承重判据。

只钉可复算事实，不评好看；看图结论单独写在 验证记录 里。
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
SCRIPT = HERE / "battle_script.json"
STATS = HERE / "battle_demo_stats.json"
BASELINE = BAKE / "combat-motion-design" / "source-baseline.json"
RESULT = HERE / "verify_battle_result.json"
SRC = (HERE / "make_battle.py").read_text(encoding="utf-8")

checks: list[dict] = []


def check(name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def diff_px(a: Image.Image, b: Image.Image, crop, threshold=18) -> int:
    ca = a.crop(crop).convert("RGB")
    cb = b.crop(crop).convert("RGB")
    d = ImageChops.difference(ca, cb).convert("L")
    return sum(d.histogram()[threshold + 1:])


def main() -> int:
    script, spec, stats, table = jload(SCRIPT), jload(SPEC), jload(STATS), jload(TABLE)

    # B01 牌型 -> 动作 / 伤害必须来自规格，不是剧本随手写
    bad = []
    for r in script["rounds"]:
        wt = r["player_type"] if r["winner"] == "player" else r["foe_type"]
        if (r["attack"] != spec["card_type_binding"][wt]["winner_card"]
                or r["damage"] != spec["damage_tiers"][wt]["base"]
                or r["attack"] not in table["cards"]):
            bad.append(r["n"])
    check("B01_card_type_binding", not bad,
          f"rounds={len(script['rounds'])} spec_violations={bad}")

    # B02 血量 / 怒气轨迹从剧本逐回独立复算
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
    check("B02_hp_rage_track_recomputed", track == script["hp_track"],
          f"recomputed={track[-1]} recorded={script['hp_track'][-1]}")

    # B03 胜负由最终兵力比较推出，不照抄文案
    out = script["outcome"]
    derived = "player" if track[-1]["player"] > track[-1]["foe"] else "foe"
    check("B03_outcome_derived", derived == out["winner"]
          and out["player_hp"] == track[-1]["player"]
          and out["foe_hp"] == track[-1]["foe"],
          f"derived={derived} declared={out['winner']} "
          f"hp={track[-1]['player']}:{track[-1]['foe']}")

    # B04 两条 GIF 文件与 stats 逐项一致
    gif_bad = []
    for mode, g in stats["modes"].items():
        p = HERE / g["file"]
        if not p.is_file() or sha(p) != g["sha256"] or p.stat().st_size != g["bytes"]:
            gif_bad.append(mode)
    check("B04_gif_hashes", len(stats["modes"]) == 2 and not gif_bad,
          f"modes={list(stats['modes'])} bad={gif_bad}")

    # B05 总播放时长守恒（GIF 会合并相同帧，钉时长不钉帧数）
    dur_bad = []
    for mode, g in stats["modes"].items():
        with Image.open(HERE / g["file"]) as im:
            total = 0
            for i in range(im.n_frames):
                im.seek(i)
                total += im.info.get("duration", 0)
            if (total != g["duration_sum_ms"]
                    or g["duration_sum_ms"] != g["expected_duration_ms"]
                    or g["expected_duration_ms"] != stats["total_frames"] * stats["frame_ms"]
                    or not (0 < g["encoded_frames"] <= g["src_frames"])):
                dur_bad.append(f"{mode}:{total}")
    check("B05_duration_conservation", not dur_bad,
          f"total_frames={stats['total_frames']} frame_ms={stats['frame_ms']} bad={dur_bad}")

    # B06 帧长必须是 10ms 整数倍：83ms 会被 GIF 量化成 80/90 丢总时长
    check("B06_frame_ms_10ms_multiple",
          stats["frame_ms"] % 10 == 0 and script["frame_ms"] == stats["frame_ms"]
          and script["fps"] == 1000 / stats["frame_ms"],
          f"frame_ms={stats['frame_ms']} fps={script['fps']}")

    # B07 GIF 逐帧可读、尺寸正确、非纯色（抽样）
    W, H = script["canvas"]
    frame_bad = []
    for mode, g in stats["modes"].items():
        with Image.open(HERE / g["file"]) as im:
            for i in range(0, im.n_frames, max(1, im.n_frames // 10)):
                im.seek(i)
                rgb = im.convert("RGB")
                if rgb.size != (W, H) or max(ImageStat.Stat(rgb).stddev) < 8:
                    frame_bad.append(f"{mode}:f{i}")
    check("B07_gif_frames_readable", not frame_bad,
          f"canvas={W}x{H} bad={frame_bad}")

    # B08 关键帧 PNG 两版各 12 张，尺寸与画布一致、内容非空
    key_bad = []
    for mode in ("puppet", "c3d"):
        d = HERE / "frames" / mode
        files = sorted(d.glob("battle-f*.png"))
        if len(files) != len(stats["key_indices"]):
            key_bad.append(f"{mode}:count={len(files)}")
        for p in files:
            im = Image.open(p)
            if im.size != (W, H) or p.stat().st_size < 20000:
                key_bad.append(p.name)
    check("B08_keyframes_complete", not key_bad,
          f"expected={len(stats['key_indices'])} per mode bad={key_bad[:4]}")

    # B09 两版在同一命中帧的对手区域必须确实不同（真3D版不是复制立绘版）
    hit = [i for i in stats["key_indices"] if i % stats["turn_frames"] == 27]
    assert len(hit) == 3
    gf = hit[1]
    a = Image.open(HERE / "frames" / "puppet" / f"battle-f{gf:03d}.png")
    b = Image.open(HERE / "frames" / "c3d" / f"battle-f{gf:03d}.png")
    foe_diff = diff_px(a, b, (430, 88, 880, 376))
    player_diff = diff_px(a, b, (0, 88, 380, 376))
    check("B09_foe_differs_between_versions", foe_diff > 3000,
          f"frame={gf} foe_diff_px={foe_diff} threshold>3000")
    # B10 玩家侧两版同源，必须几乎逐像素一致
    check("B10_player_identical_between_versions", player_diff < 200,
          f"frame={gf} player_diff_px={player_diff} threshold<200")

    # B11 展示板非空
    boards = ["battle-demo-keyframe-board.png", "battle-demo-two-version-comparison.png"]
    board_bad = []
    for n in boards:
        p = HERE / n
        if not p.is_file() or p.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n" \
                or p.stat().st_size < 50000:
            board_bad.append(n)
    check("B11_boards_nonempty", not board_bad,
          f"boards={len(boards)} bad={board_bad}")

    # B12 源码接线：角色来源、C 网格、时长口径、前压、速度线
    # optimize=False 也出现在注释里，宽松子串会被注释骗过（M5 实测逃逸）。
    # 钉真实调用形态：duration=... loop=0 optimize=False disposal=1)
    needles = ["FOE_C3D", "puppet_player", "battle_script.json",
               "duration=FRAME_MS, loop=0, optimize=False, disposal=1)",
               "120 * math.sin", "draw_speed_lines", "PLAYER_CX", "FOE_CX"]
    missing = [n for n in needles if n not in SRC]
    check("B12_source_wiring", not missing,
          f"needles={len(needles)} missing={missing}")

    # B13 stats 里记录的三个源文件指纹与实际一致
    src = stats["sources"]
    check("B13_source_fingerprints",
          src["spec_sha256"] == sha(SPEC)
          and src["table_sha256"] == sha(TABLE)
          and src["script_sha256"] == sha(SCRIPT)
          and src["foe_c3d_frames"].endswith("frames"),
          f"spec/table/script all_match="
          f"{src['spec_sha256'] == sha(SPEC) and src['table_sha256'] == sha(TABLE) and src['script_sha256'] == sha(SCRIPT)}")

    # B14 简化规则 / 表现层受击必须明说不宣称完整实现
    check("B14_not_claimed_is_explicit",
          "demo simplification" in script["compare"]
          and "受击是离线表现层" in script["_not_claimed"]
          and "new 未烘" in script["_not_claimed"],
          f"compare={script['compare'][:48]!r}")

    # B15 游戏源码 0 改动
    base = jload(BASELINE)
    game = Path(base["game_dir"])
    changed = [rel for rel, meta in base["files"].items()
               if not (game / rel).is_file()
               or (game / rel).stat().st_size != meta["bytes"]
               or sha(game / rel) != meta["sha256"]]
    check("B15_game_sources_untouched",
          not changed and len(base["files"]) >= 7,
          f"files={len(base['files'])} changed={changed}")

    passed = sum(1 for c in checks if c["ok"])
    result = {"checks": checks, "passed": passed, "total": len(checks),
              "verified": passed == len(checks),
              "diagnostics": {"foe_diff_px": foe_diff,
                              "player_diff_px": player_diff,
                              "compared_frame": gf}}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"VERIFY_BATTLE {passed}/{len(checks)} "
          f"{'BATTLE_DEMO_VERIFIED' if result['verified'] else 'BATTLE_DEMO_FAILED'}",
          flush=True)
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
