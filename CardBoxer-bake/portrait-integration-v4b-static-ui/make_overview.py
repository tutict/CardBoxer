"""交付总览板：实机图 / 档案两页 / A→B 差异热区（红色=新增像素）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
S = HERE / "shots"
FONT = Path("C:/Windows/Fonts/msyh.ttc")
CELL_W, CELL_H = 640, 360
LABEL_H = 30


def fnt(sz: int):
    return ImageFont.truetype(str(FONT), sz) if FONT.exists() else ImageFont.load_default()


def load(name: str) -> Image.Image:
    with Image.open(S / name) as im:
        return im.convert("RGB")


def diff_heat() -> Image.Image:
    a, b = load("A_baseline-without-portraits.png"), load("B_integration-panel-closed.png")
    d = ImageChops.difference(a, b).convert("L").point(lambda p: 255 if p > 6 else 0)
    heat = b.copy()
    red = Image.new("RGB", heat.size, (255, 60, 60))
    heat.paste(red, (0, 0), d)
    return heat


def main() -> None:
    panels = [
        ("F_live-unpaused.png", "实机画面（无暂停）"),
        ("C_profile-page-1.png", "档案板 页1 · 正面大立绘 + 要素表"),
        ("D_profile-page-2.png", "档案板 页2 · 三视角半身"),
    ]
    imgs = [(load(f), title) for f, title in panels]
    imgs.append((diff_heat(), "A→B 差异热区（红=新增，框外 0 变化像素）"))

    out = Image.new("RGB", (CELL_W * 2, (CELL_H + LABEL_H) * 2), (18, 20, 27))
    d = ImageDraw.Draw(out)
    for i, (im, title) in enumerate(imgs):
        thumb = im.resize((CELL_W, CELL_H), Image.Resampling.LANCZOS)
        x, y = (i % 2) * CELL_W, (i // 2) * (CELL_H + LABEL_H)
        out.paste(thumb, (x, y))
        d.text((x + 10, y + CELL_H + 4), title, font=fnt(17), fill=(228, 232, 242))
        d.rectangle((x, y, x + CELL_W, y + CELL_H), outline=(84, 92, 112), width=1)
    out.save(HERE / "integration-overview.png")
    print(f"OVERVIEW_OK {out.size}")


if __name__ == "__main__":
    main()
