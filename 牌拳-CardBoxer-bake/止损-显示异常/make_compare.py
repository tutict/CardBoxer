"""把回滚后两种启动方式的真实截帧拼成一张对照板（纯展示，不改判据）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
TOP = HERE / "shots" / "after-default" / "display-live.png"
BOTTOM = HERE / "shots" / "after-3d" / "display-live.png"
OUT = HERE / "止损-两版对照.png"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")


def load_font(size: int):
    if FONT.is_file():
        return ImageFont.truetype(str(FONT), size)
    return ImageFont.load_default()


def main() -> int:
    a = Image.open(TOP).convert("RGB")
    b = Image.open(BOTTOM).convert("RGB")
    assert a.size == b.size == (1280, 720), (a.size, b.size)
    head, band, gap = 108, 46, 16
    y1 = head
    y2 = head + band + 720 + gap
    height = y2 + band + 720
    canvas = Image.new("RGB", (1280, height), (16, 18, 26))
    d = ImageDraw.Draw(canvas)
    big, small = load_font(26), load_font(18)
    d.text((28, 14), "止损复测 · 回滚到 I 基线后的真实运行画面",
           font=big, fill=(240, 240, 246))
    d.text((28, 55), "Godot 4.5 / GL Compatibility / 1280x720 / 零脚本错误",
           font=small, fill=(150, 158, 176))
    # 标题带单独占行，绝不覆盖截帧里的血条 / HUD。
    for y, text in (
        (y1, "上：默认启动（运行游戏.bat） → 2D 代码自绘小人，3D 层默认关"),
        (y2, "下：CARD_BOXER_3D=1（运行游戏-3D.bat） → 两套 3D 表现层"),
    ):
        d.rectangle((0, y, 1280, y + band), fill=(26, 29, 40))
        d.text((28, y + 12), text, font=small, fill=(255, 214, 140))
    canvas.paste(a, (0, y1 + band))
    canvas.paste(b, (0, y2 + band))
    canvas.save(OUT)
    print("WROTE", OUT, canvas.size, OUT.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
