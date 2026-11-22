"""把 8 张资产拼成看图样张（仅用于人工复核，不进 Godot）。

每张统一 contain 进固定面板，避免大图溢出压到邻栏（第一版踩过）。
棋盘底只用来肉眼判断 alpha 是否真的透明，不写进任何产物。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
A = HERE / "assets"
FONT = Path("C:/Windows/Fonts/msyh.ttc")
NAMES = [
    "card_p1.png", "card_p55.png", "avatar_player.png", "avatar_foe.png",
    "profile_front.png", "profile_25.png", "profile_55.png", "profile_back35.png",
]
CELL_W, CELL_H = 440, 330
PANEL_W, PANEL_H = 420, 280
PAD, LABEL_H = 16, 44


def fnt(sz: int):
    return ImageFont.truetype(str(FONT), sz) if FONT.exists() else ImageFont.load_default()


def checker(size: tuple[int, int]) -> Image.Image:
    im = Image.new("RGB", size, (48, 50, 60))
    d = ImageDraw.Draw(im)
    for y in range(0, size[1], 12):
        for x in range(0, size[0], 12):
            if (x // 12 + y // 12) % 2:
                d.rectangle((x, y, x + 11, y + 11), fill=(66, 68, 80))
    return im


def main() -> None:
    cols = 4
    out = Image.new("RGB", (CELL_W * cols + PAD, (CELL_H + LABEL_H) * 2 + PAD), (24, 26, 34))
    d = ImageDraw.Draw(out)
    for i, name in enumerate(NAMES):
        with Image.open(A / name) as src:
            im = src.convert("RGBA")
        native = list(im.size)
        # 统一 contain，保留真实宽高比；小图（40px 头像）放大到可读尺寸
        fit = ImageOps.contain(im, (PANEL_W, PANEL_H), Image.Resampling.LANCZOS)
        col, row = i % cols, i // cols
        x = PAD + col * CELL_W
        y = PAD + row * (CELL_H + LABEL_H)
        panel = checker((PANEL_W, PANEL_H))
        px = (PANEL_W - fit.width) // 2
        py = PANEL_H - fit.height            # 底对齐，和引擎里一致
        panel.paste(fit, (px, py), fit)
        out.paste(panel, (x, y))
        d.rectangle((x, y, x + PANEL_W, y + PANEL_H), outline=(86, 92, 112), width=1)
        d.text((x + 4, y + PANEL_H + 4), f"{name}  {native[0]}x{native[1]}",
               font=fnt(15), fill=(226, 230, 240))
        d.text((x + 4, y + PANEL_H + 24), "contain 进面板 · 底对齐 · 棋盘=透明",
               font=fnt(11), fill=(140, 148, 168))
    out.save(HERE / "asset-samples.png")
    print(f"ASSET_SHEET_OK {out.size}")


if __name__ == "__main__":
    main()
