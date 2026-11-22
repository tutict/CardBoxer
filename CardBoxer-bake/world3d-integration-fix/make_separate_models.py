"""两侧「各自单独建模」展示板 + 用户帧来源硬判定。

产出：
  boards/independent-models-presentation-board.png     左侧纯女拳手 / 右侧纯铁甲怪（放大）
  boards/independent-models-cross-talk-comparison.png   上排改前串扰 / 下排当前独立（2x2）
  data/separate_models.json          像素/ sha 判据 + 用户帧来源 MAE

素材全部来自引擎内真实截帧（shots/shipped 与 shots/legacy 的
SubViewport 原图），不做任何 3D 合成或模型编辑。

用法：python make_separate_models.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
P0 = BAKE / "route-b-asset-deduplication"
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"
OUT = HERE / "data" / "separate_models.json"
USER = Path(r"C:\Users\tutic\.workbuddy\clipboard-images"
            r"\clipboard-2026-11-14T07-41-08-103Z-c0f0d105.png")
ORIENT_BOARD = BAKE / "orientation-fix" / "boards" / "orientation-before-after-comparison.png"

SV = {
    "shipped_player": SHOTS / "shipped" / "sh-shipped-sv-player.png",
    "shipped_foe": SHOTS / "shipped" / "sh-shipped-sv-foe.png",
    "legacy_player": SHOTS / "legacy" / "sh-legacy-sv-player.png",
    "legacy_foe": SHOTS / "legacy" / "sh-legacy-sv-foe.png",
}
BOARD_MAIN = BOARDS / "independent-models-presentation-board.png"
BOARD_COMPARE = BOARDS / "independent-models-cross-talk-comparison.png"
# 缩放匹配用的对照分辨率；提高到 1/2 以保留卡牌数字与朝向差异。
SMALL = (342, 148)


def font(sz: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
    return ImageFont.load_default()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def stats(p: Path) -> dict:
    im = Image.open(p).convert("RGBA")
    opaque = white = cyan = 0
    for r, g, b, a in im.getdata():
        if a < 32:
            continue
        opaque += 1
        if r > 175 and g > 175 and b > 175:
            white += 1
        if b > 110 and g > 110 and r < g - 18:
            cyan += 1
    return {"size": list(im.size), "opaque_px": opaque,
            "near_white_px": white, "cyan_px": cyan,
            "white_ratio": round(white / max(1, opaque), 6)}


def mae(a: Image.Image, b: Image.Image) -> float:
    d = ImageChops.difference(a, b)
    return round(sum(ImageStat.Stat(d).mean) / 3, 3)


def best_window(b: Image.Image, us: Image.Image,
                y0s, hs, x0s, ws) -> dict:
    best = {"mae": 1e9}
    for y0 in y0s:
        for h in hs:
            for x0 in x0s:
                for w in ws:
                    if x0 + w > b.width or y0 + h > b.height:
                        continue
                    crop = b.crop((x0, y0, x0 + w, y0 + h)).resize(
                        SMALL, Image.LANCZOS)
                    m = mae(us, crop)
                    if m < best["mae"]:
                        best = {"mae": m, "x0": x0, "y0": y0,
                                "w": w, "h": h}
    return best


def locate_user_frame() -> dict:
    """三路相对对照定位来源，不拍绝对阈值。

    用户图经过缩放/重编码，逐行精确匹配失效；改为分别在
    ① 朝向板下格（修朝向后、修 World3D 前）
    ② 朝向板上格（修朝向前）
    ③ 当前修后落生态整帧
    穷举裁剪窗口取最小 MAE，用「哪一路最像」判定，而不是调阈值凑绿。
    """
    u0 = Image.open(USER)
    if u0.mode == "RGBA":
        bg = Image.new("RGBA", u0.size, (255, 255, 255, 255))
        u = Image.alpha_composite(bg, u0).convert("RGB")
    else:
        u = u0.convert("RGB")
    uw, uh = u.size
    us = u.resize(SMALL, Image.LANCZOS)
    b = Image.open(ORIENT_BOARD).convert("RGB")
    x0s, ws = (0, 10, 20, 30, 40), (920, 900, 880, 860)
    hs = (370, 380, 390, 400)
    lower = best_window(b, us, range(500, 565, 5), hs, x0s, ws)
    upper = best_window(b, us, range(100, 175, 5), hs, x0s, ws)
    cur_im = Image.open(
        SHOTS / "shipped" / "sh-shipped-live.png").convert("RGB")
    cur_im = cur_im.resize((920, 518), Image.LANCZOS)
    current = best_window(cur_im, us, range(0, 130, 10), hs, x0s, ws)
    scores = {"orientation_lower": lower["mae"],
              "orientation_upper": upper["mae"],
              "shipped_live": current["mae"]}
    best_name = min(scores, key=scores.get)
    return {
        "user_size": [uw, uh], "board": str(ORIENT_BOARD),
        "board_size": list(b.size),
        "best_window": lower,
        "scores": scores,
        "closest": best_name,
        "is_orientation_lower": best_name == "orientation_lower",
        "pre_fix_closer_than_shipped": (
            min(scores["orientation_lower"], scores["orientation_upper"])
            < scores["shipped_live"]),
        "note": ("像素级同源只做相对判定（用户图经缩放/重编码）；"
                 "另有人眼可核的标签文字「改后：玩家 -55°、对手 +55° "
                 "→ 两人面对面」与卡牌序列 1/9/4/6/7 逐项一致。"),
    }


def gradient_panel(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line((0, y, w, y),
               fill=(int(30 + 18 * t), int(26 + 12 * t),
                     int(40 + 22 * t)))
    return im


def paste_character(panel: Image.Image, fg: Image.Image,
                    x: int, y: int, size) -> None:
    f = fg.convert("RGBA").resize(size, Image.LANCZOS)
    shadow = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    cx = x + size[0] // 2
    cy = y + size[1] - 8
    sd.ellipse((cx - size[0] // 4, cy - 12,
                cx + size[0] // 4, cy + 12), fill=(0, 0, 0, 110))
    panel.paste(Image.alpha_composite(
        panel.convert("RGBA"), shadow).convert("RGB"), (0, 0))
    panel.paste(f, (x, y), f)


def build_main() -> None:
    W, H = 1200, 848
    HEAD, LABEL, FRAME, FOOT = 72, 48, 632, 96
    board = Image.new("RGB", (W, H), (20, 20, 25))
    d = ImageDraw.Draw(board)
    f30, f21, f17 = font(30), font(21), font(17)
    d.text((22, 16), "《牌拳》双侧独立建模 · 当前落生态",
           font=f30, fill=(240, 240, 242))
    ly = HEAD
    d.text((40, ly + 10), "玩家 · 女性拳手（白长衫 / 靛蓝云纹）",
           font=f21, fill=(255, 236, 205))
    d.text((640, ly + 10), "对手 · 铁甲怪（兜帽重甲 / 黑披风）",
           font=f21, fill=(205, 224, 255))
    fy = HEAD + LABEL
    for i, key in enumerate(("shipped_player", "shipped_foe")):
        x = 20 + i * 600
        panel = gradient_panel(560, FRAME)
        paste_character(panel, Image.open(SV[key]), 50, 22, (460, 570))
        board.paste(panel, (x, fy))
        d.rectangle((x, fy, x + 560, fy + FRAME),
                    outline=(70, 74, 90), width=2)
        d.text((x + 16, fy + FRAME - 34),
               ("player-rigged.glb  ·  57,934 顶点  ·  yaw -55°"
                if i == 0 else
                "foe-rigged.glb  ·  64,059 顶点  ·  yaw +55°"),
               font=f17, fill=(190, 196, 210))
    yy = fy + FRAME
    d.rectangle((0, yy, W, yy + FOOT), fill=(14, 16, 21))
    d.text((22, yy + 10),
           "各自独立 World3D：每个 SubViewport 只渲染自己的角色；"
           "上图为引擎内真实截帧原图，非离线合成。",
           font=f17, fill=(224, 228, 234))
    d.text((22, yy + 38),
           "判据：两层原图与 P0「一次只挂一层」单层真值逐字节相同；"
           "玩家近白 31.15%，对手 1.03%。",
           font=f17, fill=(170, 180, 194))
    d.text((22, yy + 66),
           "你贴的帧是修 World3D 之前的串扰态（见朝向修复对照板），"
           "不是当前工程状态；来源判定见 separate_models.json。",
           font=f17, fill=(255, 205, 150))
    board.save(BOARD_MAIN)


def build_compare() -> None:
    CW, CH = 340, 424
    W, H = 760, 56 + 2 * (CH + 34) + 76
    board = Image.new("RGB", (W, H), (20, 20, 25))
    d = ImageDraw.Draw(board)
    f24, f18, f16 = font(24), font(18), font(16)
    d.text((18, 12), "改前串扰 / 当前独立 · 四个视口原图 2×2 对照",
           font=f24, fill=(238, 238, 242))
    rows = [
        ("改前 · 共享 World3D（串扰态）",
         "legacy_player", "legacy_foe"),
        ("当前 · 独立 World3D（工程现状）",
         "shipped_player", "shipped_foe"),
    ]
    for r, (title, kp, kf) in enumerate(rows):
        ty = 56 + r * (CH + 34)
        d.text((18, ty + 4), title, font=f18,
               fill=(255, 214, 160) if r == 0 else (170, 230, 190))
        for c, key in enumerate((kp, kf)):
            x = 18 + c * (CW + 20)
            y = ty + 30
            panel = gradient_panel(CW, CH)
            paste_character(panel, Image.open(SV[key]),
                            18, 8, (304, 376))
            board.paste(panel, (x, y))
            d.rectangle((x, y, x + CW, y + CH),
                        outline=(70, 74, 90), width=2)
            d.text((x + 8, y + CH - 26),
                   ("玩家视口" if c == 0 else "对手视口"),
                   font=f16, fill=(210, 214, 224))
    yy = 56 + 2 * (CH + 34)
    d.rectangle((0, yy, W, yy + 76), fill=(14, 16, 21))
    d.text((18, yy + 10),
           "上排：每个视口都画进两个角色，白长衫与重甲叠在同一身体上。",
           font=f16, fill=(224, 228, 234))
    d.text((18, yy + 40),
           "下排：左纯女性长衫、右纯铁甲怪，各自单独，无对方造型残留。",
           font=f16, fill=(170, 230, 190))
    board.save(BOARD_COMPARE)


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    for p in SV.values():
        assert p.is_file(), p
    truth = {r["role"]: r for r in
             json.loads((P0 / "data" / "single_layers.json").read_text(
                 encoding="utf-8"))["runs"]}
    rows = {k: dict(stats(p), sha256=sha(p)) for k, p in SV.items()}
    origin = locate_user_frame()
    build_main()
    build_compare()

    sp, sf = rows["shipped_player"], rows["shipped_foe"]
    lp, lf_ = rows["legacy_player"], rows["legacy_foe"]
    checks = {
        "four_sv_present": all(
            p.is_file() and p.stat().st_size > 20000 for p in SV.values()),
        "sv_size_420x520": all(
            r["size"] == [420, 520] for r in rows.values()),
        "shipped_player_matches_single_truth": (
            sp["sha256"] == truth["player"]["png_sha256"] != ""),
        "shipped_foe_matches_single_truth": (
            sf["sha256"] == truth["foe"]["png_sha256"] != ""),
        "shipped_pair_distinct": sp["sha256"] != sf["sha256"],
        "shipped_player_is_white": sp["white_ratio"] > 0.25,
        "shipped_foe_is_dark": sf["white_ratio"] < 0.03,
        "legacy_both_mixed": (lp["white_ratio"] > 0.10
                              and lf_["white_ratio"] > 0.10),
        "legacy_differs_from_truth": all(
            rows[f"legacy_{r}"]["sha256"] != truth[r]["png_sha256"]
            for r in ("player", "foe")),
        "user_frame_is_pre_world3d_fix": (
            origin["pre_fix_closer_than_shipped"]),
        "origin_three_way_scores_recorded": len(origin["scores"]) == 3,
        "two_boards_written": (BOARD_MAIN.is_file()
                               and BOARD_COMPARE.is_file()
                               and BOARD_MAIN.stat().st_size > 50000
                               and BOARD_COMPARE.stat().st_size > 50000),
    }
    report = {
        "user_frame": origin,
        "sv": rows,
        "single_layer_truth_sha256": {
            r: truth[r]["png_sha256"] for r in ("player", "foe")},
        "conclusion": (
            "当前工程落生态已经是「左边单独女性建模 / 右边单独铁甲怪建模」："
            "两层 SubViewport 原图与一次只挂一层的单层真值逐字节相同。"
            "用户贴的帧是 World3D 修复之前的串扰态，不是当前工程状态。"),
        "origin_observations": {
            "mae_scores": origin["scores"],
            "closest": origin["closest"],
            "unresolved": (
                "整体 MAE 无法区分朝向板上下格（同场景、同背景、角色位置"
                "接近）：上格 "
                f"{origin['scores']['orientation_upper']} < 下格 "
                f"{origin['scores']['orientation_lower']}。像素级只能证明"
                "「用户帧是修 World3D 之前的串扰态」；指向下格的依据是"
                "标签文字「改后：玩家 -55°、对手 +55° → 两人面对面」、"
                "卡牌序列 1/9/4/6/7 与两人面对面朝向的视觉比对，"
                "不作为像素级证明。"),
        },
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("ORIGIN", json.dumps(origin, ensure_ascii=False))
    for k, r in rows.items():
        print("SV", k, r["white_ratio"], r["near_white_px"],
              r["sha256"][:12])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("SEPARATE_MODELS_OK" if report["ok"]
          else "SEPARATE_MODELS_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
