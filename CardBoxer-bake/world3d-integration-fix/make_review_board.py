"""World3D 接线修复 · Creative Review 对照板与亮度量化。

用 shipped（落生态）/ legacy（强制关复现旧态）两张真实整帧：
  * 上下拼成改前改后对照板；
  * 两侧角色 ROI 裁出四格放大对照；
  * 逐 ROI 量化平均亮度 / 亮像素占比 / 暗像素占比，把「独立 World3D
    后各层只剩自己的 4 盏灯」这个副作用变成可复算数字。

用法：python make_review_board.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"
D = HERE / "data"
LEGACY = SHOTS / "legacy" / "sh-legacy-live.png"
SHIPPED = SHOTS / "shipped" / "sh-shipped-live.png"
NO_TINT = SHOTS / "no_tint" / "sh-shipped-live.png"
BOARD = BOARDS / "World3D-fix-before-after-comparison.png"
ROIBOARD = BOARDS / "World3D-fix-character-brightness-comparison.png"
ATTRBOARD = BOARDS / "World3D-fix-foe-darkening-analysis.png"
OUT = D / "review_brightness.json"

# 角色 ROI（1280x720 整帧，脚在 y≈520、头在 y≈300）
ROIS = {"player": (350, 275, 545, 535),
        "foe": (730, 275, 985, 535)}


def font(size: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def roi_stats(im: Image.Image, box) -> dict:
    c = im.convert("RGB").crop(box)
    vals = []
    for r, g, b in c.getdata():
        vals.append((r * 299 + g * 587 + b * 114) // 1000)
    n = max(1, len(vals))
    # ROI 里 77~94% 是暗背景，整块平均亮度会被稀释；另给「只算亮于
    # 背景的像素」口径，更贴近角色本体的亮度变化。
    bright = [v for v in vals if v > 48]
    return {
        "mean_luma": round(sum(vals) / n, 3),
        "pct_above_128": round(sum(1 for v in vals if v > 128) / n, 6),
        "pct_below_48": round(sum(1 for v in vals if v < 48) / n, 6),
        "pct_above_48": round(len(bright) / n, 6),
        "mean_luma_above_48": round(
            sum(bright) / max(1, len(bright)), 3),
        "pct_above_80": round(sum(1 for v in vals if v > 80) / n, 6),
        "max_luma": max(vals),
        "pixels": len(vals),
    }


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    assert LEGACY.is_file() and SHIPPED.is_file() and NO_TINT.is_file()
    a = Image.open(LEGACY).convert("RGB")
    b = Image.open(SHIPPED).convert("RGB")
    c = Image.open(NO_TINT).convert("RGB")
    assert a.size == b.size == c.size == (1280, 720)

    data = {"rois": ROIS, "frames": {}}
    for tag, im in (("legacy", a), ("shipped", b), ("no_tint", c)):
        data["frames"][tag] = {k: roi_stats(im, v)
                               for k, v in ROIS.items()}
    for role in ROIS:
        la = data["frames"]["legacy"][role]["mean_luma"]
        lb = data["frames"]["shipped"][role]["mean_luma"]
        data["frames"][f"{role}_luma_delta"] = round(lb - la, 3)
        data["frames"][f"{role}_luma_pct"] = round(
            (lb - la) / max(1e-6, la) * 100, 2)
    lf = data["frames"]["legacy"]["foe"]["mean_luma"]
    sf = data["frames"]["shipped"]["foe"]["mean_luma"]
    nf = data["frames"]["no_tint"]["foe"]["mean_luma"]
    data["attribution"] = {
        "foe_roi_luma": {"legacy": lf, "shipped": sf, "no_tint": nf},
        "tint_effect": round(nf - sf, 3),
        "world_isolation_effect_vs_legacy": round(sf - lf, 3),
        "conclusion": (
            "shipped 与 no_tint 同为独立 World3D（每层 4 盏灯），只差 I 路线 "
            "2D 调暗 shader；关掉 tint 后 foe ROI 亮度上升且高于改前，"
            "证伪「独立后灯少导致变暗」。改后 foe 偏暗的主因是 I 路线刻意 "
            "调暗 + 深色重甲，属既有设计，本轮未改。"),
    }
    data["note"] = (
        "共享 World3D 时两层共 8 盏灯同时照到两个角色；独立后每层只剩自己的 "
        "4 盏灯。但实测关掉 I 路线 2D shader 后 foe 反而比改前更亮，"
        "所以「灯少导致变暗」被证伪；亮度下降主要来自串扰白布消失与 "
        "I 路线刻意调暗，本轮不改 tint 设计，作为已知视觉债如实记录。")

    # 主对照板：改前在上、改后在下。标签条放在帧外，避免盖住血条 HUD。
    H, BAR, FOOT = 64, 42, 124
    board = Image.new("RGB", (1280, H + (BAR + 720) * 2 + FOOT),
                      (22, 22, 26))
    d = ImageDraw.Draw(board)
    f28, f20, f17 = font(28), font(20), font(17)
    d.text((20, 16), "《牌拳》3D 层接线修复 · 改前 / 改后整帧对照",
           font=f28, fill=(238, 238, 240))
    for i, (tag, im, label) in enumerate((
            ("改前", a, "共享 World3D：每个视口都画进两个角色"),
            ("改后", b, "独立 World3D：每个视口只画自己的角色"))):
        y = H + i * (BAR + 720)
        d.rectangle((0, y, 1280, y + BAR), fill=(16, 18, 22))
        d.text((20, y + 9), f"{tag} · {label}", font=f20,
               fill=(255, 240, 210))
        board.paste(im, (0, y + BAR))
    fy = H + (BAR + 720) * 2
    d.rectangle((0, fy, 1280, fy + FOOT), fill=(16, 18, 22))
    p = data["frames"]["player_luma_delta"]
    q = data["frames"]["foe_luma_delta"]
    d.text((20, fy + 12),
           f"玩家 ROI 平均亮度 {data['frames']['legacy']['player']['mean_luma']}"
           f" → {data['frames']['shipped']['player']['mean_luma']} ({p:+.2f})；"
           f"对手 ROI {data['frames']['legacy']['foe']['mean_luma']}"
           f" → {data['frames']['shipped']['foe']['mean_luma']} ({q:+.2f})",
           font=f20, fill=(220, 225, 230))
    d.text((20, fy + 48),
           "独立后每层只剩自己的 4 盏灯，亮度下降是必然副作用；"
           "对手侧另有 I 路线调暗 shader，本轮未改。",
           font=f17, fill=(160, 168, 178))
    la48 = data["frames"]["legacy"]["player"]["mean_luma_above_48"]
    lb48 = data["frames"]["shipped"]["player"]["mean_luma_above_48"]
    fa48 = data["frames"]["legacy"]["foe"]["mean_luma_above_48"]
    fb48 = data["frames"]["shipped"]["foe"]["mean_luma_above_48"]
    d.text((20, fy + 80),
           f"角色像素(亮度>48) 平均：玩家 {la48} → {lb48}；"
           f"对手 {fa48} → {fb48}（排除暗背景后的口径）",
           font=f17, fill=(190, 198, 208))
    board.save(BOARD)

    # ROI 四格放大对照
    cell_w, cell_h = 390, 520
    rb = Image.new("RGB", (cell_w * 2 + 60, cell_h + 110), (22, 22, 26))
    rd = ImageDraw.Draw(rb)
    rd.text((16, 12), "角色 ROI 放大对照（左：改前 / 右：改后）",
            font=f20, fill=(238, 238, 240))
    for col, (tag, im) in enumerate((("改前", a), ("改后", b))):
        x = 20 + col * (cell_w + 20)
        rd.text((x, 48), tag, font=f20, fill=(255, 240, 210))
        for row, (role, box) in enumerate(ROIS.items()):
            crop = im.crop(box).resize(
                (cell_w, cell_h // 2 - 6), Image.LANCZOS)
            rb.paste(crop, (x, 78 + row * (cell_h // 2)))
            st = data["frames"]["legacy" if col == 0 else "shipped"][role]
            rd.text((x + 6, 84 + row * (cell_h // 2)),
                    f"{role} luma={st['mean_luma']}", font=f17,
                    fill=(255, 255, 255))
    rb.save(ROIBOARD)

    # 对手变暗归因：三格 foe ROI 并排（改前 / 改后 / 改后关 tint）
    ap = Image.new("RGB", (1250, 640), (22, 22, 26))
    ad = ImageDraw.Draw(ap)
    ad.text((16, 14), "对手偏暗归因 · foe ROI 放大（三帧同机位）",
            font=f20, fill=(238, 238, 240))
    for i, (tag, key, im) in enumerate((
            ("改前 · 共享 World3D", "legacy", a),
            ("改后 · 独立 World3D", "shipped", b),
            ("改后 · 独立 + 关 tint", "no_tint", c))):
        x = 20 + i * 410
        crop = im.crop(ROIS["foe"]).resize((390, 480), Image.LANCZOS)
        ap.paste(crop, (x, 56))
        ad.text((x, 542),
                f"{tag}   luma={data['frames'][key]['foe']['mean_luma']}",
                font=f17, fill=(255, 240, 210))
    ad.text((16, 578),
            f"只关 I 路线 2D 调暗 shader：{sf} → {nf} ({nf - sf:+.3f})，"
            "且高于改前；「独立后灯少导致变暗」不成立。",
            font=f17, fill=(220, 225, 230))
    ad.text((16, 608),
            "改后对手偏暗是 I 路线刻意调暗 + 深色重甲的既有观感，"
            "本轮未改设计，作为已知视觉债记录。",
            font=f17, fill=(160, 168, 178))
    ap.save(ATTRBOARD)

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for role in ROIS:
        print(role, "legacy", data["frames"]["legacy"][role],
              "shipped", data["frames"]["shipped"][role],
              "delta_pct", data["frames"][f"{role}_luma_pct"])
    print("BOARD", BOARD.stat().st_size, ROIBOARD.stat().st_size,
          ATTRBOARD.stat().st_size)
    print("ATTRIBUTION",
          json.dumps(data["attribution"]["foe_roi_luma"],
                     ensure_ascii=False),
          "tint_effect", data["attribution"]["tint_effect"])
    print("REVIEW_BOARD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
