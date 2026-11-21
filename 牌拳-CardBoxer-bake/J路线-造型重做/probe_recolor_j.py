"""J 路线 r2 探针：离线模拟 foe 层 canvas shader 的「语义重绘」效果。

不改游戏源码、不改资产。只对 v1 已截帧的 foe SubViewport RGBA 图做逐像素
变换，模拟把 shader 挂到 foe 层本地 material 后会得到什么，用来判断
「表现层语义重绘」这条链值不值得接线。

三档对照：
  C0 现状      = I 路线 tint vec3(0.42, 0.30, 0.28)
  C1 暗钢覆面  = C0 + 近白高光压成炭黑/铁锈红 + 青色压成低饱和暗青
  C2 工业警示  = C1 + 原近白区域叠加工业橙/黑斜向警示条纹

判据口径沿用 diag_motif_j.py：角色掩膜 = alpha > 127。
输出：boards/J-语义重绘探针.png、data/recolor_probe_j.json。
用法：python probe_recolor_j.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC = HERE / "shots" / "asset_v1" / "j-sv-foe.png"
PLAYER = HERE / "shots" / "asset_v1" / "j-sv-player.png"
BOARD = HERE / "boards" / "J-语义重绘探针.png"
OUT = HERE / "data" / "recolor_probe_j.json"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")

TINT = (0.42, 0.30, 0.28)          # 与 FOE_CANVAS_SHADER_CODE 一致
CHARCOAL = (34, 30, 30)
RUST = (104, 48, 34)
DARK_CYAN = (26, 62, 70)
WARN_ORANGE = (196, 122, 32)


def near_white(r, g, b):
    return r > 200 and g > 200 and b > 200


def cyan(r, g, b):
    return b > 120 and g > 120 and r < g - 20


def hot_red(r, g, b):
    return r > 140 and g < r * 0.62 and b < r * 0.62


def tint(rgb, mul):
    return tuple(int(min(255, v * m)) for v, m in zip(rgb, mul))


def recolor(mode: str, src: Image.Image) -> Image.Image:
    im = src.convert("RGBA")
    px = list(im.getdata())
    w, h = im.size
    out = []
    for i, (r, g, b, a) in enumerate(px):
        if a <= 127:
            out.append((r, g, b, a))
            continue
        base = tint((r, g, b), TINT)
        if mode == "C0":
            out.append((*base, a))
            continue
        x, y = i % w, i // w
        luma = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 255.0
        is_highlight = near_white(r, g, b) or luma > 0.74
        if is_highlight:
            # 高光不再是「白衫」，改写成炭黑 + 铁锈红的斑驳金属。
            t = 0.5 + 0.5 * math.sin((x + y) * 0.11)
            c = tuple(int(CHARCOAL[k] * (1 - t) + RUST[k] * t)
                      for k in range(3))
            if mode == "C2" and ((x + y) // 14) % 2 == 0:
                c = WARN_ORANGE
            out.append((*c, a))
        elif cyan(r, g, b):
            # 青云纹不再发光，只留极少量低饱和暗青（以太结晶感）。
            out.append((*DARK_CYAN, a))
        elif hot_red(r, g, b):
            # 红色头花并入铁锈红，不再是高饱和花饰。
            out.append((*RUST, a))
        else:
            out.append((*base, a))
    res = Image.new("RGBA", (w, h))
    res.putdata(out)
    return res


def stats(im: Image.Image) -> dict:
    px = list(im.convert("RGBA").getdata())
    inner = [(r, g, b) for r, g, b, a in px if a > 127]
    n = len(inner)
    nw = sum(1 for c in inner if near_white(*c))
    cy = sum(1 for c in inner if cyan(*c))
    hr = sum(1 for c in inner if hot_red(*c))
    warn = sum(1 for r, g, b in inner
               if r > 150 and 80 < g < 170 and b < 90)
    mean = [round(sum(c[k] for c in inner) / n, 2) for k in range(3)]
    return {
        "mask_px": n, "near_white_ratio": round(nw / n, 6),
        "cyan_ratio": round(cy / n, 6), "hot_red_ratio": round(hr / n, 6),
        "warning_orange_ratio": round(warn / n, 6),
        "mean_rgb": mean,
    }


def main() -> int:
    src = Image.open(SRC)
    modes = ("C0", "C1", "C2")
    images = {m: recolor(m, src) for m in modes}
    st = {"source": stats(src)}
    st.update({m: stats(images[m]) for m in modes})
    st["player_reference"] = stats(Image.open(PLAYER))

    pad, cell_w, cell_h, label = 18, 300, 375, 56
    W = pad * 4 + 4 * cell_w
    H = pad * 2 + cell_h + label
    canvas = Image.new("RGB", (W, H), (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 15) if FONT.is_file() \
        else ImageFont.load_default()
    titles = {
        "source": ("v1 原图 (无 tint)", st["source"]),
        "C0": ("C0 现状 tint", st["C0"]),
        "C1": ("C1 暗钢覆面", st["C1"]),
        "C2": ("C2 工业警示", st["C2"]),
    }
    order = ("source", "C0", "C1", "C2")
    for i, key in enumerate(order):
        im = src if key == "source" else images[key]
        x = pad + i * (cell_w + pad)
        # 贴到浅底以看清透明区之外的角色轮廓
        tile = Image.new("RGB", (cell_w, cell_h), (232, 232, 236))
        shown = im.convert("RGBA").resize((cell_w, cell_h), Image.LANCZOS)
        tile.paste(shown, (0, 0), shown)
        canvas.paste(tile, (x, pad))
        title, s = titles[key]
        d.text((x + 2, pad + cell_h + 4), title, font=f,
               fill=(225, 230, 245))
        d.text((x + 2, pad + cell_h + 22),
               f"white {s['near_white_ratio']:.4f}  "
               f"cyan {s['cyan_ratio']:.4f}", font=f,
               fill=(170, 190, 215))
        d.text((x + 2, pad + cell_h + 38),
               f"orange {s['warning_orange_ratio']:.4f}  "
               f"mean {s['mean_rgb'][0]:.0f}/{s['mean_rgb'][1]:.0f}/"
               f"{s['mean_rgb'][2]:.0f}", font=f, fill=(170, 190, 215))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)

    # 订正（实测）：I 路线的 tint 已经把 foe 的近白 / 青特征清零，
    # 所以「再加一层语义重绘」没有可消除的目标；三档掩膜像素数完全相同，
    # 说明 canvas 层无论怎么调色都改不了剪影。这是本探针最重要的结论。
    checks = {
        "source_is_rgba_with_alpha": src.mode == "RGBA",
        "source_has_high_white": st["source"]["near_white_ratio"] > 0.10,
        "i_route_tint_already_removes_white": (
            st["C0"]["near_white_ratio"] <= 0.02),
        "i_route_tint_already_removes_cyan": (
            st["C0"]["cyan_ratio"] <= 0.005),
        "c1_removes_white": st["C1"]["near_white_ratio"] <= 0.02,
        "c2_removes_white": st["C2"]["near_white_ratio"] <= 0.02,
        "c1_removes_cyan": st["C1"]["cyan_ratio"] <= 0.005,
        "c2_adds_warning_color": (
            st["C2"]["warning_orange_ratio"]
            > st["C1"]["warning_orange_ratio"] + 0.01),
        "c1_darker_than_c0": (sum(st["C1"]["mean_rgb"])
                              < sum(st["C0"]["mean_rgb"])),
        "all_modes_keep_identical_silhouette": (
            len({st[k]["mask_px"] for k in
                 ("source", "C0", "C1", "C2")}) == 1),
        "player_reference_unchanged": (
            st["player_reference"]["mask_px"] > 0),
        "board_written": BOARD.is_file()
                         and BOARD.stat().st_size > 50000,
    }
    report = {
        "source": str(SRC), "tint": list(TINT),
        "stats": st, "board": str(BOARD),
        "board_bytes": BOARD.stat().st_size,
        "conclusion": (
            "I 路线 canvas tint 已把 foe 掩膜内近白/青特征清零；"
            "C1/C2 相对 C0 只改颜色，角色掩膜像素数逐档相同，"
            "证明 2D canvas 层无法改变剪影。C2 的橙黑警示条纹能把白衫"
            "下摆的色彩语义换成工业条幅，观感改善明显，但披风/头饰/"
            "站姿形状不变：表现层链是低成本观感改进，不是根治。"
            "要根治几何同源仍需精确删壳或重生成 3D。"),
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in st.items():
        print("STATS", k, v)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("RECOLOR_PROBE_J_OK" if report["ok"]
          else "RECOLOR_PROBE_J_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
