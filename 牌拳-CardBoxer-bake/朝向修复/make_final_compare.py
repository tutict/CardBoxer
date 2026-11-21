"""改前 / 改后同机位对照：都是不隐藏 HUD、无暂停横幅的完整主场景截帧。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BEFORE = BAKE / "止损-显示异常" / "shots" / "after-3d" / "display-live.png"
AFTER = HERE / "shots" / "final" / "display-live.png"
OUT = HERE / "boards" / "朝向-改前改后对照.png"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
BOX = (180, 230, 1100, 590)


def font(size: int):
    if FONT.is_file():
        return ImageFont.truetype(str(FONT), size)
    return ImageFont.load_default()


def main() -> int:
    a = Image.open(BEFORE).convert("RGB")
    b = Image.open(AFTER).convert("RGB")
    assert a.size == b.size == (1280, 720)
    ca = a.crop(BOX)   # 920x360
    cb = b.crop(BOX)
    cw, ch = ca.size
    band, head = 46, 76
    canvas = Image.new("RGB", (cw, head + 2 * (band + ch) + 16),
                       (16, 18, 26))
    d = ImageDraw.Draw(canvas)
    d.text((20, 12), "朝向订正 · 玩家 -55° / 对手 +55°（其余一律不动）",
           font=font(24), fill=(240, 240, 246))
    d.text((20, 46), "同机位 / 同分辨率 / 同 GLB 资产，唯一变量是两层 yaw",
           font=font(16), fill=(150, 158, 176))
    for i, (img, label) in enumerate((
        (ca, "改前：玩家 +55°、对手 -55° → 两人背对背朝外（用户反馈）"),
        (cb, "改后：玩家 -55°、对手 +55° → 两人面对面"),
    )):
        y = head + i * (band + ch + 16)
        d.rectangle((0, y, cw, y + band), fill=(26, 29, 40))
        d.text((16, y + 11), label, font=font(17), fill=(255, 214, 140))
        canvas.paste(img, (0, y + band))
    canvas.save(OUT)
    print("WROTE", OUT, canvas.size, OUT.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
