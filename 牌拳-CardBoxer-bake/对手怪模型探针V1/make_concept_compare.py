"""玩家 V4b vs 对手怪 V1 的 2D 概念对照板。

公平性处理：两边都裁到各自的人物包围盒，再统一缩放到「人物高 700px」
且脚底对齐同一 y —— 这样对比的是体块与明度，不是画布留白。
玩家用 alpha>8 求 bbox；对手怪概念图是浅灰实底，用亮度 <150 求 bbox，
并先把右下角水印区抹掉，免得水印撑大包围盒。

注意：这只是 2D 概念视觉对照，不做明度数值断言。
同相机 / 同归一化身高的明度与肩宽数字要等 3D 渲染图出来，
由 measure_silhouette.py 复算，别拿不同底色的概念图硬算。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
CONCEPT = HERE / "概念图"
PLAYER = BAKE / "3D模型探针V4b" / "v4b-front.png"
FOE = CONCEPT / "Full_body_character_concept_ar_2026-11-07T11-02-32.png"

FONT = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")
W, H = 1440, 1160
CARD_W, CARD_H = 660, 820
BODY_H = 700
FOOT_Y = 130 + 740           # 两列脚底对齐到同一绝对 y
CYAN = (70, 210, 230)
WHITE = (238, 240, 246)
MUTED = (150, 160, 180)


def fnt(size: int, bold: bool = False):
    p = FONT_BOLD if bold else FONT
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def label(im, x, y, text, size, color=WHITE, bold=False):
    ImageDraw.Draw(im).text((x, y), text, font=fnt(size, bold), fill=color)


def player_subject() -> tuple[Image.Image, list[int]]:
    with Image.open(PLAYER) as f:
        im = f.convert("RGBA")
    mask = im.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    bb = mask.getbbox()
    assert bb, "player alpha empty"
    return im.crop(bb), list(bb)


def edge_bg(im: Image.Image) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """概念图是浅灰垂直渐变实底：取顶部整条与底部整条的均值，
    卡片底按这两色逐行插值，避免单一均值色造成「内亮方块」。
    bbox 从 y=38 起、到 y=1500 止，画布 1536 —— 两端整条都是纯背景。
    """
    w, h = im.size
    n = 24

    def avg(box):
        p = im.crop(box)
        vals = [p.getpixel((x, y)) for y in range(p.height) for x in range(p.width)]
        return tuple(round(sum(v[i] for v in vals) / len(vals)) for i in range(3))

    return avg((0, 0, w, n)), avg((0, h - n, w, h))


def foe_subject() -> tuple[Image.Image, list[int], tuple[tuple[int, int, int], tuple[int, int, int]]]:
    with Image.open(FOE) as f:
        im = f.convert("RGB")
    w, h = im.size
    grad = edge_bg(im)
    g = im.convert("L")
    # 右下角「AI生成 / WORKBUDDY」水印是深色，会撑大 bbox，先抹成背景色
    d = ImageDraw.Draw(g)
    d.rectangle((round(w * 0.78), round(h * 0.90), w, h), fill=235)
    mask = g.point(lambda v: 255 if v < 150 else 0)
    bb = mask.getbbox()
    assert bb, "foe luminance bbox empty"
    crop = im.crop(bb).convert("RGB")
    # 抹掉右下角水印：复制它左侧同高同宽的条带（那里是纯背景）。
    # 用上方条带会连带复制靴子，实测会在右下角留一个黑方块。
    cw, ch = crop.size
    x0, y0 = round(cw * 0.82), round(ch * 0.94)
    band_w = cw - x0
    if band_w > 0 and x0 - band_w >= 0:
        crop.paste(crop.crop((x0 - band_w, y0, x0, ch)), (x0, y0))
    return crop.convert("RGBA"), list(bb), grad


def fit_to_body(im: Image.Image) -> Image.Image:
    w = round(im.width * BODY_H / im.height)
    return im.resize((w, BODY_H), Image.Resampling.LANCZOS)


def feather(im: Image.Image, fade: int = 5) -> Image.Image:
    """只柔化 5px 贴片硬边。半径一大就会把贴边的人物轮廓吃淡，
    并在同色卡片底上造出「内亮方块」，第一版 22px 已实测翻车。"""
    w, h = im.size
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rectangle((fade, fade, w - 1 - fade, h - 1 - fade), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(fade / 2))
    out = im.convert("RGBA")
    out.putalpha(m)
    return out


def main() -> None:
    p, pbb = player_subject()
    f, fbb, foe_grad = foe_subject()
    p, f = fit_to_body(p), fit_to_body(feather(f))

    img = Image.new("RGB", (W, H), (18, 20, 26))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        k = y / H
        d.rectangle((0, y, W, y + 4),
                    fill=(round(18 + 10 * k), round(20 + 9 * k), round(26 + 12 * k)))
    d.rectangle((50, 28, 1390, 30), fill=CYAN)
    label(img, 50, 42, "《牌拳》玩家 V4b  vs  对手怪 V1 · 造型对照", 30, WHITE, True)
    label(img, 50, 88, "2D 概念图 · 人物等高 700px、脚底对齐 · 非同相机渲染，不做明度数值断言", 14, MUTED)

    cols = [
        (50, "玩家  /  V4b 定稿", p, None, "纤细 · 浅色 · 露脸 · 长衫飘带", CYAN),
        (730, "对手怪  /  V1 概念", f, foe_grad, "厚重 · 深色 · 覆面 · 拼装硬壳", (232, 132, 72)),
    ]
    for x, title, art, grad, tag, accent in cols:
        if grad is None:
            d.rounded_rectangle((x, 130, x + CARD_W, 130 + CARD_H), radius=10,
                                fill=(48, 52, 62), outline=(86, 94, 112), width=1)
        else:
            # 卡片底按概念图自身的上下背景色逐行插值，圆角用 mask 保留
            top, bot = grad
            card_mask = Image.new("L", (CARD_W, CARD_H), 0)
            ImageDraw.Draw(card_mask).rounded_rectangle(
                (0, 0, CARD_W - 1, CARD_H - 1), radius=10, fill=255)
            grad_img = Image.new("RGB", (CARD_W, CARD_H))
            gd = ImageDraw.Draw(grad_img)
            for yy in range(CARD_H):
                t = yy / CARD_H
                gd.line((0, yy, CARD_W, yy),
                        fill=tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
            img.paste(grad_img, (x, 130), card_mask)
            d.rounded_rectangle((x, 130, x + CARD_W, 130 + CARD_H), radius=10,
                                fill=None, outline=(86, 94, 112), width=1)
        ax = x + (CARD_W - art.width) // 2
        ay = FOOT_Y - art.height
        img.paste(art, (ax, ay), art)
        label(img, x + 4, 962, title, 19, WHITE, True)
        label(img, x + 4, 992, tag, 15, accent)
        label(img, x + 4, 1020, f"bbox={art.size[0]}x{BODY_H} (裁后等高)", 12, MUTED)

    d.rounded_rectangle((50, 1060, 1390, 1140), radius=8,
                        fill=(32, 35, 44), outline=(86, 94, 112), width=1)
    label(img, 70, 1070, "设计判据", 15, CYAN, True)
    label(img, 70, 1098,
          "同屏一眼可分：宽肩厚躯 vs 修长身形；炭黑铁锈红 vs 象牙白明黄；全面罩无表情 vs 露脸有表情；硬壳铆钉 vs 布质长衫。",
          14, (206, 214, 228))
    label(img, 70, 1120, "对手怪当前是 2D 概念图；3D 生成因当日 hy-3d 配额 5/5 用满被 429 拒绝，见 配额阻塞记录.txt", 12, MUTED)

    out = HERE / "玩家V4b-对手怪V1-概念对照.png"
    img.save(out)
    stats = {
        "note": "2D 概念视觉对照；bbox 可复算，明度数字等 3D 同相机渲染再算",
        "player_bbox_in_source": pbb,
        "foe_luminance_bbox_in_source": fbb,
        "body_height_px": BODY_H,
        "foot_y": FOOT_Y,
        "output": out.name,
        "bytes": out.stat().st_size,
    }
    (CONCEPT / "concept_compare_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))
    print("CONCEPT_COMPARE_OK")


if __name__ == "__main__":
    main()
