"""把 3D模型探针V4b（脸模/配饰优化定稿）贴进《牌拳》真实引擎截帧。

V3 版在 `portrait-integration-preview/`，本目录独立保留，不覆盖旧归档。

边界（必须随图一起说清楚）：
  * 这是 Pillow 离线合成，不是 Godot 引擎实渲，也没有改任何游戏源码。
  * 立绘是静态 A-pose 渲染，不会摆出 jab / sweep 等动作帧。
  * 角色锚点、卡牌几何全部来自 arena.gd / hud.gd 的常量，不靠目测。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V4B = BAKE / "3d-model-probe-v4b"
SHOT = BAKE / "background-candidates" / "rage-meter" / "rage-meter-full-meter.png"

# ── 全部来自游戏源码，不靠截图目测 ──────────────────────────────
# arena.gd:33 GROUND_Y := 520.0 / :130 player.x=430 / :136 enemy.x=850
GROUND_Y = 520
PLAYER_X, ENEMY_X = 430, 850
# hud.gd:13-16
CARD_W, CARD_H, CARD_GAP, HAND_Y = 148, 150, 16, 552

WARM = (255, 186, 96)
COOL = (108, 200, 246)
INK_BG = (26, 28, 34)
CARD_BG = (26, 28, 41)

# 四视角透明渲染里人物的包围盒（probe_v4b_assets.py 实测 alpha>8）
# 不能沿用 V3：V4b 多了明黄披肩 / 长袖 / 白色飘带，front 横向 420px vs V3 238px。
SUBJECT = {
    "front": (174, 96, 594, 672),
    "angle25": (156, 96, 569, 672),
    "angle55": (188, 96, 569, 672),
    "back35": (255, 96, 608, 672),
}

# 脸特写（1024²，透明背景）作头像母图，比从 768² 全身图裁脸清晰得多。
FACE_SHOT = {
    "front": "v4b-face-front.png",
    "angle25": "v4b-face-25.png",
    "angle55": "v4b-face-25.png",
    "back35": "v4b-face-front.png",
}

FONT_FILE = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")


def fnt(size: int, bold: bool = False):
    p = FONT_BOLD if bold else FONT_FILE
    if p.exists():
        return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_subject(key: str, height: int) -> Image.Image:
    """裁出人物包围盒，等比缩到指定高度，返回 RGBA。"""
    with Image.open(V4B / f"v4b-{key}.png") as src:
        im = src.convert("RGBA")
    im = im.crop(SUBJECT[key])
    w = round(im.width * height / im.height)
    return im.resize((w, height), Image.Resampling.LANCZOS)


def tint(im: Image.Image, color: tuple[int, int, int], alpha: float) -> Image.Image:
    """只染 RGB，原 alpha 原样保留。"""
    if alpha <= 0:
        return im
    rgb = Image.blend(im.convert("RGB"), Image.new("RGB", im.size, color), alpha)
    out = rgb.convert("RGBA")
    out.putalpha(im.getchannel("A"))
    return out


def paste(base: Image.Image, layer: Image.Image, xy: tuple[int, int]) -> None:
    if layer.mode in ("RGBA", "LA"):
        base.paste(layer, xy, layer)
    else:
        base.paste(layer, xy)


def erase_by_shift(im: Image.Image, box: tuple[int, int, int, int], dx: int) -> None:
    """用同一 y 带的邻近背景水平平移，盖掉角色身体。

    只擦 GROUND_Y 以上；脚下椭圆阴影、地面光晕、地面线全部保留。
    绳子 / 观众席在这个 y 带是水平连续的，平移后接缝最小。
    """
    x0, y0, x1, y1 = box
    patch = im.crop((x0 + dx, y0, x1 + dx, y1))
    # 左右各 10px 与原图线性羽化，避免硬边
    fade = 10
    orig = im.crop(box).convert("RGBA")
    patch = patch.convert("RGBA")
    mask = Image.new("L", patch.size, 255)
    md = ImageDraw.Draw(mask)
    for i in range(fade):
        v = round(255 * i / fade)
        md.line([(i, 0), (i, patch.height)], fill=v)
        md.line([(patch.width - 1 - i, 0), (patch.width - 1 - i, patch.height)], fill=v)
    merged = Image.composite(patch, orig, mask)
    im.paste(merged.convert("RGB"), box)


def label(base: Image.Image, x: int, y: int, text: str, size: int = 12,
          color=(150, 156, 172), bold: bool = False) -> None:
    ImageDraw.Draw(base).text((x, y), text, font=fnt(size, bold), fill=color)


def offline_tag(base: Image.Image, x: int, y: int) -> None:
    """每张贴进真实截帧的图都打上「非引擎实渲」标记，防止被当成真实截图。

    右边界必须 < 238（第 1 张卡牌的左边缘），不然会压住卡面。
    """
    d = ImageDraw.Draw(base)
    d.rounded_rectangle((x - 8, y - 6, x + 210, y + 34), radius=6, fill=(12, 13, 20))
    label(base, x, y, "离线合成 · 非引擎实渲", 13, (232, 206, 140), True)
    label(base, x, y + 19, "V4b 定稿造型贴片 / 源码未改", 11, (140, 146, 162))


# ── A：战斗区替换 ────────────────────────────────────────────────

def make_a() -> Image.Image:
    with Image.open(SHOT) as s:
        img = s.convert("RGB")

    # V4b 立绘比 V3 宽约 75px：擦除框必须盖住整个贴片，否则旧火柴人的
    # 橙/蓝残影会露在新立绘两侧。240px 高时 front≈175px / angle25≈172px 宽。
    # 填充源统一取两人之间 x=560..760 的纯背景：与擦除框同 y 带，绳索水平
    # 对齐，既没有人物也没有左上角的斜向装饰。早先用 dx=±190 从外侧取，
    # 会把那条斜线复制进人物两侧（差异图与放大图实测），已退役。
    erase_by_shift(img, (330, 310, 530, GROUND_Y - 2), 230)
    erase_by_shift(img, (750, 310, 950, GROUND_Y - 2), -190)

    height = 240  # 原火柴人约 195px 高；放大到 240px 以便看清立绘细节
    p = tint(load_subject("front", height), WARM, 0.10)
    e = ImageOps.mirror(tint(load_subject("angle25", height), COOL, 0.14))
    paste(img, p, (PLAYER_X - p.width // 2, GROUND_Y - height))
    paste(img, e, (ENEMY_X - e.width // 2, GROUND_Y - height))

    offline_tag(img, 24, 632)
    return img


# ── B：角色插画卡 + HUD 头像 ─────────────────────────────────────

def bust(key: str, w: int, h: int, crop_h: int = 330) -> Image.Image:
    """上半身像：取头到腰一段，contain 进目标框。

    crop_h 越小人物在框里越大；148x150 的小卡要 250，档案板的大卡要 330。
    """
    with Image.open(V4B / f"v4b-{key}.png") as src:
        im = src.convert("RGBA")
    bb = SUBJECT[key]
    im = im.crop((bb[0], bb[1], bb[2], bb[1] + crop_h))
    return ImageOps.contain(im, (w, h), Image.Resampling.LANCZOS)


def portrait_crop(key: str) -> Image.Image:
    """圆形头像母图：用 1024² 脸特写的中心 600² 正方形。

    纯按画布中心推导，不靠目测标脸位置；脸特写相机本身就是对准脸的
    （render_character.py 的 face-front / face-25 shot），alpha 四角为 0。
    """
    with Image.open(V4B / FACE_SHOT[key]) as src:
        im = src.convert("RGBA")
    cx, cy, side = im.width // 2, im.height // 2, 600
    return im.crop((cx - side // 2, cy - side // 2,
                    cx + side // 2, cy + side // 2))


def circular_avatar(key: str, size: int) -> Image.Image:
    src = portrait_crop(key)
    side = min(src.size)
    src = ImageOps.fit(src, (side, side), Image.Resampling.LANCZOS)
    src = src.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(src, (0, 0), mask)
    return out


def char_card(key: str, index: int, name: str, sub: str, accent) -> Image.Image:
    """148x150 —— 与 hud.gd 的 CARD_W / CARD_H 完全一致。"""
    card = Image.new("RGB", (CARD_W, CARD_H), CARD_BG)
    d = ImageDraw.Draw(card)
    d.rectangle((0, 0, CARD_W, 5), fill=accent)
    d.rectangle((0, 0, CARD_W - 1, CARD_H - 1), outline=(77, 84, 112), width=1)

    art_h = 104
    art = bust(key, CARD_W - 12, art_h, crop_h=250)
    ax = (CARD_W - art.width) // 2
    paste(card, art, (ax, 6 + (art_h - art.height) // 2))

    # 名字条顶边恰好接在插画下沿；游戏底部提示文字在 y≈700，
    # 卡内最后一行文字必须停在 y<696，否则会被提示行压住。
    d.rectangle((0, CARD_H - 40, CARD_W, CARD_H), fill=(18, 20, 30))
    d.line((0, CARD_H - 40, CARD_W, CARD_H - 40), fill=accent, width=1)
    d.text((10, CARD_H - 34), name, font=fnt(17, True), fill=(242, 243, 248))
    if sub:
        d.text((10, CARD_H - 15), sub, font=fnt(10), fill=(150, 158, 178))

    # 与游戏一致的左上角序号圆
    d.ellipse((6, 8, 30, 32), fill=(15, 18, 28), outline=accent, width=2)
    d.text((14, 12), str(index), font=fnt(14, True), fill=(242, 243, 248))
    return card


def make_b() -> Image.Image:
    with Image.open(SHOT) as s:
        img = s.convert("RGB")

    x0 = 640 - (5 * CARD_W + 4 * CARD_GAP) // 2  # = 238，与 hud.gd:_draw_hand 同式
    slots = [x0 + i * (CARD_W + CARD_GAP) for i in range(5)]
    # 只换第 1、5 张，中间 3 张原样保留，作为真实尺寸对照
    img.paste(char_card("front", 1, "裁决官", "", WARM), (slots[0], HAND_Y))
    img.paste(char_card("angle25", 5, "青岚", "", COOL), (slots[4], HAND_Y))

    # HUD 头像：血条起点上方 40px 空档，左右各一枚，不改血条本身
    for cx, key, accent in [(22, "front", WARM), (1256, "angle25", COOL)]:
        av = circular_avatar(key, 40)
        d = ImageDraw.Draw(img)
        d.ellipse((cx - 22, 0, cx + 22, 44), fill=(14, 16, 24), outline=accent, width=2)
        paste(img, av, (cx - 20, 2))

    offline_tag(img, 24, 632)
    return img


# ── C：角色档案板（概念面板，不是游戏 UI） ───────────────────────

def make_c() -> Image.Image:
    img = Image.new("RGB", (1280, 720), INK_BG)
    d = ImageDraw.Draw(img)
    for y in range(0, 720, 4):
        k = y / 720
        d.rectangle((0, y, 1280, y + 4), fill=(round(26 + 12 * k), round(28 + 10 * k), round(34 + 16 * k)))

    d.rectangle((56, 44, 1224, 46), fill=(70, 210, 230))
    label(img, 56, 60, "角色档案  /  CHARACTER PROFILE", 38, (238, 240, 246), True)
    label(img, 56, 112, "《牌拳》V4b 定稿造型 · 国风立领 × 都市机能 · 静态 A-pose", 16, (150, 160, 180))

    big = load_subject("front", 500)
    paste(img, big, (150, 150))
    d = ImageDraw.Draw(img)
    d.line((150, 656, 440, 656), fill=(70, 210, 230), width=2)
    label(img, 150, 664, "正面 / FRONT", 14, (190, 200, 216), True)

    thumb_keys = ["angle25", "angle55", "back35"]
    thumb_names = ["25° 斜视", "55° 侧视", "背面 35°"]
    for i, (k, nm) in enumerate(zip(thumb_keys, thumb_names)):
        x = 530 + i * 232
        # 卡片只到 y=440，角度标签一律放到卡外，避免压在人物衣摆上
        d.rounded_rectangle((x, 168, x + 208, 440), radius=8, fill=(34, 37, 46), outline=(72, 78, 96), width=1)
        art = bust(k, 196, 258)
        paste(img, art, (x + (208 - art.width) // 2, 174 + (258 - art.height) // 2))
        label(img, x + 10, 448, nm, 15, (218, 224, 236), True)
        label(img, x + 10, 472, "可作卡牌插画 / 头像母图", 12, (140, 150, 168))

    d.rounded_rectangle((530, 520, 1224, 672), radius=8, fill=(32, 35, 44), outline=(72, 78, 96), width=1)
    rows = [
        ("脸模", "琥珀分层虹膜 + 清晰睫毛 + 细眉 + 干净下颌"),
        ("叠穿", "明黄披肩领 + 黑不对称襟片 + 白叶枝印花"),
        ("配饰", "太极圆牌 / 金绳结 / 红流苏 / 银环耳环 / 青护腕"),
        ("覆盖", "白色长袖到手腕 · V4 的裸露上臂已修掉 · 无拳套"),
    ]
    for i, (k, v) in enumerate(rows):
        yy = 534 + i * 34
        label(img, 550, yy, k, 15, (70, 210, 230), True)
        label(img, 620, yy, v, 15, (214, 220, 232))
    label(img, 550, 676, "离线合成概念板 · 非游戏内 UI · 造型定稿后再谈接入", 12, (130, 140, 158))
    return img


# ── D：部件尺寸样张 ──────────────────────────────────────────────

def make_d() -> Image.Image:
    img = Image.new("RGB", (1280, 720), INK_BG)
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 1240, 42), fill=(70, 210, 230))
    label(img, 40, 56, "部件尺寸样张  /  ASSET SIZE SHEET", 32, (238, 240, 246), True)
    label(img, 40, 100, "全部按真实像素尺寸摆放，1:1，没有放大预览", 15, (150, 160, 180))

    # 标题必须短于「本部件宽 + 46」的步进，否则相邻标题会连成一串
    # 样张要控制变量：三枚头像一律用正面脸，只变尺寸。
    # V3 版 64px 用 angle25，换成 1024² 脸特写母图后侧脸会偏出圆心，已退役。
    items = [
        ("96px 头像", 96, "front", "avatar"),
        ("64px 头像", 64, "front", "avatar"),
        ("40px 头像", 40, "front", "avatar"),
        ("148 角色卡", 148, "front", "card"),
        ("220 立绘卡", 220, "angle25", "tall"),
    ]
    x = 60
    for title, size, key, kind in items:
        label(img, x, 160, title, 14, (214, 222, 234), True)
        y = 200
        if kind == "avatar":
            av = circular_avatar(key, size)
            d.ellipse((x - 3, y - 3, x + size + 3, y + size + 3), outline=(72, 78, 96), width=2)
            paste(img, av, (x, y))
        elif kind == "card":
            paste(img, char_card(key, 1, "裁决官", "148 x 150", WARM), (x, y))
        else:
            h = 300
            d.rounded_rectangle((x, y, x + size, y + h), radius=8, fill=(34, 37, 46), outline=(72, 78, 96), width=1)
            art = ImageOps.contain(load_subject(key, h - 12), (size - 12, h - 12), Image.Resampling.LANCZOS)
            paste(img, art, (x + (size - art.width) // 2, y + (h - art.height) // 2))
            d.rectangle((x, y + h - 40, x + size, y + h), fill=(18, 20, 30))
            label(img, x + 12, y + h - 32, "裁决官", 18, (238, 240, 246), True)
        width = size if kind != "card" else CARD_W
        d.line((x, 540, x + width, 540), fill=(70, 210, 230), width=2)
        label(img, x, 550, f"{width} px", 13, (150, 160, 180))
        x += width + 46

    d.rounded_rectangle((40, 600, 1240, 676), radius=8, fill=(32, 35, 44), outline=(72, 78, 96), width=1)
    label(img, 60, 614, "读数要点", 17, (70, 210, 230), True)
    label(img, 60, 644, "三枚头像同一张正面脸、只变尺寸（控制变量）：40px 仍辨琥珀虹膜；64px 起睫毛可读；96px 起发箍与红发夹成立。", 14, (206, 214, 228))
    label(img, 60, 686, "离线合成样张 · 非游戏内 UI", 12, (130, 140, 158))
    return img


# ── E：2x2 总览 ─────────────────────────────────────────────────

def make_overview(parts: dict[str, Image.Image]) -> Image.Image:
    out = Image.new("RGB", (1280, 720), (18, 20, 27))
    order = [("A", "战斗区替换"), ("B", "卡牌插画 + HUD 头像"),
             ("C", "角色档案板"), ("D", "部件尺寸样张")]
    for i, (k, title) in enumerate(order):
        thumb = parts[k].resize((624, 351), Image.Resampling.LANCZOS)
        x, y = 10 + (i % 2) * 640, 6 + (i // 2) * 360
        out.paste(thumb, (x, y))
        d = ImageDraw.Draw(out)
        d.rectangle((x, y, x + 624, y + 351), outline=(88, 96, 118), width=1)
        d.rectangle((x, y, x + 210, y + 28), fill=(14, 16, 24))
        label(out, x + 8, y + 5, f"{k} · {title}", 14, (232, 236, 244), True)
    return out


def main() -> None:
    parts = {"A": make_a(), "B": make_b(), "C": make_c(), "D": make_d()}
    parts["E"] = make_overview(parts)
    names = {
        "A": "preview-A-arena-replacement.png",
        "B": "preview-B-card-art-and-avatars.png",
        "C": "preview-C-character-profile.png",
        "D": "preview-D-part-size-samples.png",
        "E": "preview-overview.png",
    }
    for k, im in parts.items():
        im.save(HERE / names[k])

    manifest = {
        "note": "V4b 定稿造型的离线合成效果预览，非引擎实渲；游戏源码零改动",
        "source_shot": str(SHOT),
        "source_shot_sha256": sha256(SHOT),
        "sources": {f"v4b-{k}.png": sha256(V4B / f"v4b-{k}.png") for k in SUBJECT},
        "face_sources": {v: sha256(V4B / v) for v in sorted(set(FACE_SHOT.values()))},
        "geometry_from_source": {
            "arena.gd": {"GROUND_Y": GROUND_Y, "player_x": PLAYER_X, "enemy_x": ENEMY_X},
            "hud.gd": {"CARD_W": CARD_W, "CARD_H": CARD_H, "CARD_GAP": CARD_GAP, "HAND_Y": HAND_Y},
        },
        "composite": {
            "subject_height_px": 240,
            "original_silhouette_height_px": 195,
            "erase_boxes": [[330, 310, 530, GROUND_Y - 2], [750, 310, 950, GROUND_Y - 2]],
            "card_slots_x": [640 - (5 * CARD_W + 4 * CARD_GAP) // 2 + i * (CARD_W + CARD_GAP) for i in range(5)],
            "replaced_card_indices": [0, 4],
        },
        "outputs": {k: {"file": v, "size": list(parts[k].size), "sha256": sha256(HERE / v)} for k, v in names.items()},
    }
    (HERE / "preview_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"outputs": list(names.values()), "sizes": {k: list(v.size) for k, v in parts.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
