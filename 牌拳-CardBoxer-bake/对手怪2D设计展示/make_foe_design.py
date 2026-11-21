"""把对手怪 V1 的两张 2D 概念图整理成可看的设计板与细节页。

不重画、不改造型、不改材质：源图逐字节复制进本目录；展示板里只做
三件事 —— 缩放排版、按人工取景框裁细节、抹掉右下角服务水印。
「原图（含水印）」和「抹水印全身」两张都留着，viewer 里可切换对照。

取景框是**人工设计选择**（相对原图宽高的比例），不是测量结论；
全部列在 CROPS 与 design_stats.json 里，可复算。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
SRC = BAKE / "对手怪模型探针V1"
CONCEPT = SRC / "概念图"
FULL = CONCEPT / "Full_body_character_concept_ar_2026-11-07T11-02-32.png"
REDRAW = CONCEPT / "Same_single_character__identic_2026-11-07T11-03-25.png"
BOARD = SRC / "玩家V4b-对手怪V1-概念对照.png"

FONT = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")
CYAN = (70, 210, 230)
ORANGE = (232, 148, 78)
WHITE = (238, 240, 246)
MUTED = (152, 162, 182)
CARD = (48, 52, 62)
EDGE = (86, 94, 112)

# 相对坐标 (x0, y0, x1, y1)，单位：原图宽 / 高的比例。
# 人工取景：只看设计要点，不做「检测到了某部件」的声称。
CROPS = [
    ("head", "头部 · 兜帽与全面罩", (0.40, 0.02, 0.68, 0.25),
     "深兜帽 + 双圆镜片防毒面罩 + 呼吸管；脸完全遮住、无表情"),
    ("crystal", "单肩 · 以太结晶", (0.13, 0.08, 0.41, 0.28),
     "青色发光结晶簇 + 细裂纹；干净风格化，不做血肉融合"),
    ("chest", "胸甲 · 铆接与管线", (0.27, 0.16, 0.73, 0.47),
     "错配装甲板、斜跨带、圆盘机件、外露铆钉与管线"),
    ("arms", "护臂 · 缠手带", (0.04, 0.29, 0.37, 0.63),
     "超大铆接护臂 + 补丁缠带；手部无拳套"),
    ("belt", "腰带 · 挂包与垂牌", (0.19, 0.38, 0.77, 0.65),
     "厚重工具腰带、挂包、盘绕电缆、垂挂金属牌、破布下摆"),
    ("boots", "腿部 · 警示条纹与靴", (0.11, 0.72, 0.90, 0.99),
     "橙黄警示斜纹、护膝、厚底钢头靴；炭黑与铁锈红掉漆"),
]
SHOW_ON_BOARD = ("head", "crystal", "chest", "boots")

# 服务水印只占右下角纯背景区；区域外不碰任何造型像素。
WIPE = (0.86, 0.935)   # 从 (0.86w, 0.935h) 到右下角


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fnt(size: int, bold: bool = False):
    p = FONT_BOLD if bold else FONT
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def label(im, x, y, text, size, color=WHITE, bold=False):
    ImageDraw.Draw(im).text((x, y), text, font=fnt(size, bold), fill=color)


def bg(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h), (18, 20, 26))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 4):
        k = y / h
        d.rectangle((0, y, w, y + 4),
                    fill=(round(18 + 10 * k), round(20 + 9 * k), round(26 + 12 * k)))
    return im


def wipe_watermark(src: Image.Image) -> tuple[Image.Image, dict]:
    """抹掉右下角「AI生成 / WORKBUDDY」水印：用其正上方纯背景条带的
    均值色填充。不从左侧复制 —— 左侧同高度有靴子，会复制出假靴子。"""
    im = src.convert("RGB").copy()
    w, h = im.size
    x0, y0 = round(w * WIPE[0]), round(h * WIPE[1])
    band = im.crop((x0, y0 - 24, w, y0))
    px = list(band.get_flattened_data() if hasattr(band, "get_flattened_data")
              else band.getdata())
    fill = tuple(round(sum(p[i] for p in px) / len(px)) for i in range(3))
    ImageDraw.Draw(im).rectangle((x0, y0, w, h), fill=fill)

    def dark_ratio(a: Image.Image) -> float:
        r = a.crop((x0, y0, w, h)).convert("L")
        hist = r.histogram()
        return round(sum(hist[:150]) / (r.width * r.height), 5)

    def off_fill_ratio(a: Image.Image) -> float:
        """水印是浅灰底上的**白色字**，不是深色字：用「与背景填充色的
        最大通道偏差 >12」判，别猜亮度阈值。首次用暗像素比例判得到
        0.0/0.0，整条判据空转。"""
        r = a.crop((x0, y0, w, h))
        px = list(r.get_flattened_data() if hasattr(r, "get_flattened_data")
                  else r.getdata())
        return round(sum(1 for p in px
                         if max(abs(p[i] - fill[i]) for i in range(3)) > 12)
                     / len(px), 5)

    return im, {"box": [x0, y0, w, h], "fill_rgb": list(fill),
                "dark_ratio_before": dark_ratio(src.convert("RGB")),
                "dark_ratio_after": dark_ratio(im),
                "off_fill_before": off_fill_ratio(src.convert("RGB")),
                "off_fill_after": off_fill_ratio(im)}


def contain(im: Image.Image, box: tuple[int, int]) -> Image.Image:
    """等比缩放到框内，不裁内容、不拉伸；留白用卡片底色填。"""
    bw, bh = box
    k = min(bw / im.width, bh / im.height)
    r = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))),
                  Image.Resampling.LANCZOS)
    out = Image.new("RGB", (bw, bh), CARD)
    out.paste(r, ((bw - r.width) // 2, (bh - r.height) // 2))
    return out


def crops_of(im: Image.Image) -> dict[str, Image.Image]:
    w, h = im.size
    out = {}
    for key, _, (a, b, c, d), _ in CROPS:
        out[key] = im.crop((round(w * a), round(h * b), round(w * c), round(h * d)))
    return out


def card(d: ImageDraw.ImageDraw, box, fill=CARD, outline=EDGE):
    d.rounded_rectangle(box, radius=10, fill=fill, outline=outline, width=1)


def make_board(clean: Image.Image, crops: dict) -> Image.Image:
    W, H = 1800, 1500
    img = bg(W, H)
    d = ImageDraw.Draw(img)
    d.rectangle((50, 28, 1750, 30), fill=CYAN)
    label(img, 50, 44, "《牌拳》对手怪 V1 · 2D 造型设计", 32, WHITE, True)
    label(img, 50, 90,
          "ImageGen 概念图 · 参考绝区零「盗洞暴徒」视觉语言 · 非 3D 模型 / 非游戏内实渲",
          15, MUTED)

    # 左：全身
    card(d, (50, 130, 700, 1090))
    full = contain(clean, (560, 840))
    img.paste(full, (95, 155))
    label(img, 70, 1014, "正面全身 · 1024×1536", 18, WHITE, True)
    label(img, 70, 1046, "仅抹除右下角服务水印，造型像素未改；含水印原图见查看器", 13, MUTED)

    # 右：2x2 重点特写
    meta = {k: (t, s) for k, t, _, s in CROPS}
    for n, key in enumerate(SHOW_ON_BOARD):
        col, row = n % 2, n // 2
        x, y = 730 + col * 525, 130 + row * 490
        card(d, (x, y, x + 495, y + 460))
        img.paste(contain(crops[key], (475, 340)), (x + 10, y + 10))
        title, desc = meta[key]
        label(img, x + 14, y + 364, title, 19, WHITE, True)
        # 说明按 24 字手动折行，两行内写完
        desc_lines = [desc[i:i + 26] for i in range(0, len(desc), 26)][:2]
        for j, line in enumerate(desc_lines):
            label(img, x + 14, y + 398 + j * 24, line, 14, MUTED)

    # 底部信息区
    card(d, (50, 1110, 1750, 1450), fill=(32, 35, 44))
    label(img, 70, 1124, "设计要点", 16, CYAN, True)
    points = [
        "剪影对立：宽肩厚躯 / 短粗四肢 / 微前倾，对照玩家 V4b 的纤细修长；",
        "材质对立：炭黑 + 铁锈红 + 工业橙硬壳铆钉，对照象牙白明黄布质长衫；",
        "头部对立：深兜帽全面罩无表情，对照露脸有表情；单处电光青作小面积呼应；",
        "全覆盖中性战斗服、无武器、无露肤、无性化；保留人形以兼容 11 关节坐标桥。",
    ]
    for j, t in enumerate(points):
        label(img, 70, 1156 + j * 28, t, 14, (206, 214, 228))
    d.line((70, 1276, 1730, 1276), fill=EDGE, width=1)
    label(img, 70, 1288, "如实偏差 / 负结果", 16, ORANGE, True)
    gaps = [
        "规格要「单片裂纹护目镜」，生成成双圆镜片防毒面具；风格偏写实重甲插画，比 V4b 的二游 PBR 更硬；",
        "第二张图生图 input_fidelity=high 把构图锁死，视角几乎没换，只能当高保真重绘副本，不是多视图输入；",
        "3D 生成当日 hy-3d 配额 5/5 用满被 429 拒绝：无 GLB、无骨架、无动画，本页全部是 2D 概念图。",
    ]
    for j, t in enumerate(gaps):
        label(img, 70, 1318 + j * 28, t, 14, (206, 214, 228))
    d.line((70, 1400, 1730, 1400), fill=EDGE, width=1)
    label(img, 70, 1410, "边界：游戏源码 0 改动 · 未导 Godot · 未渲动作帧 · 造型好不好看由人判断，脚本 10 条判据一条都没评", 13, MUTED)
    return img


def make_detail_sheet(crops: dict) -> Image.Image:
    W, H = 1800, 1180
    img = bg(W, H)
    d = ImageDraw.Draw(img)
    d.rectangle((50, 28, 1750, 30), fill=CYAN)
    label(img, 50, 44, "《牌拳》对手怪 V1 · 细节六格", 32, WHITE, True)
    label(img, 50, 90, "六块取景框按原图宽高比例人工选定 · 等比缩放不裁不变形 · 源图 1024×1536", 15, MUTED)
    for n, (key, title, _, desc) in enumerate(CROPS):
        col, row = n % 3, n // 3
        x, y = 50 + col * 575, 130 + row * 505
        card(d, (x, y, x + 550, y + 480))
        img.paste(contain(crops[key], (530, 360)), (x + 10, y + 10))
        label(img, x + 14, y + 382, title, 19, WHITE, True)
        for j, line in enumerate([desc[i:i + 27] for i in range(0, len(desc), 27)][:2]):
            label(img, x + 14, y + 416 + j * 24, line, 14, MUTED)
    label(img, 50, 1140, "取景框见 CROPS / design_stats.json；原图右下角服务水印在展示板中已抹除，含水印原图在查看器中保留", 13, MUTED)
    return img


def colors(p: Path) -> int:
    with Image.open(p) as f:
        small = f.convert("RGB").resize((120, 120), Image.Resampling.BILINEAR)
    px = list(small.get_flattened_data() if hasattr(small, "get_flattened_data")
              else small.getdata())
    return len(set(px))


def main() -> None:
    # 源图逐字节复制，sha256 证明「展示用的就是那张图」
    copies = {}
    for src, name in ((FULL, "foe-full-original.png"),
                      (REDRAW, "foe-redraw.png"),
                      (BOARD, "玩家V4b-对手怪V1-概念对照.png")):
        dst = HERE / name
        dst.write_bytes(src.read_bytes())
        copies[name] = {"source": src.relative_to(BAKE).as_posix(),
                        "sha256": sha(src), "copy_sha256": sha(dst),
                        "identical": sha(src) == sha(dst)}
        assert copies[name]["identical"], f"复制不一致：{name}"

    with Image.open(FULL) as f:
        original = f.convert("RGB")
    clean, wipe = wipe_watermark(original)
    clean.save(HERE / "foe-full-clean.png")
    crops = crops_of(clean)

    board = make_board(clean, crops)
    detail = make_detail_sheet(crops)
    board_path = HERE / "对手怪V1-2D设计板.png"
    detail_path = HERE / "对手怪V1-细节六格.png"
    board.save(board_path)
    detail.save(detail_path)

    stats = {
        "note": "2D 概念图展示整理；取景框是人工设计选择，不是测量结论",
        "source_size": list(original.size),
        "copies": copies,
        "wipe_watermark": wipe,
        "crops": [{"key": k, "title": t, "relative_box": list(b), "desc": s}
                  for k, t, b, s in CROPS],
        "board": {"file": board_path.name, "size": list(board.size),
                  "bytes": board_path.stat().st_size, "colors_120": colors(board_path),
                  "shown_crops": list(SHOW_ON_BOARD)},
        "detail": {"file": detail_path.name, "size": list(detail.size),
                   "bytes": detail_path.stat().st_size, "colors_120": colors(detail_path)},
    }
    (HERE / "design_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成时自检：不是「跑通了就算」，抹水印必须真的把暗字去掉
    checks = [
        ("all_copies_byte_identical", all(v["identical"] for v in copies.values())),
        ("wipe_box_is_pure_background_not_art",
         wipe["dark_ratio_before"] < 0.01),
        ("watermark_actually_removed",
         wipe["off_fill_before"] > 0.005
         and wipe["off_fill_after"] < 0.01
         and wipe["off_fill_after"] < wipe["off_fill_before"] / 5),
        ("board_size_exact", list(board.size) == [1800, 1500]),
        ("detail_size_exact", list(detail.size) == [1800, 1180]),
        ("board_not_blank", stats["board"]["colors_120"] > 300),
        ("detail_not_blank", stats["detail"]["colors_120"] > 300),
        ("six_crops_defined_and_distinct",
         len(CROPS) == 6 and len({c["key"] for c in stats["crops"]}) == 6),
    ]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    verdict = "FOE_DESIGN_OK" if all(ok for _, ok in checks) else "FOE_DESIGN_FAILED"
    print(json.dumps({"verdict": verdict, "wipe": wipe,
                      "board": stats["board"], "detail": stats["detail"]},
                     ensure_ascii=False))
    raise SystemExit(0 if verdict == "FOE_DESIGN_OK" else 1)


if __name__ == "__main__":
    main()
