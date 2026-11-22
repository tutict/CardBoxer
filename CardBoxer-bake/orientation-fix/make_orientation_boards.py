"""把朝向扫描的 9 帧拼成三张板：总览 / 玩家四组特写 / 对手四组特写。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
BOTH_BOX = (180, 230, 1100, 590)
P_BOX = (240, 250, 610, 580)
F_BOX = (660, 250, 1030, 580)
LABELS = {
    "base": "基线：玩家 +55/false，对手 -55/false",
    "p-y55-f0": "玩家 yaw=+55  flip=false",
    "p-y55-f1": "玩家 yaw=+55  flip=true",
    "p-yn55-f0": "玩家 yaw=-55  flip=false",
    "p-yn55-f1": "玩家 yaw=-55  flip=true",
    "f-yn55-f0": "对手 yaw=-55  flip=false",
    "f-yn55-f1": "对手 yaw=-55  flip=true",
    "f-y55-f0": "对手 yaw=+55  flip=false",
    "f-y55-f1": "对手 yaw=+55  flip=true",
}


def font(size: int):
    if FONT.is_file():
        return ImageFont.truetype(str(FONT), size)
    return ImageFont.load_default()


def tile(name: str, box: tuple[int, int, int, int], size: tuple[int, int]):
    im = Image.open(SHOTS / f"o-{name}.png").convert("RGB").crop(box)
    return im.resize(size, Image.LANCZOS)


def grid(names: list[str], box, cell: tuple[int, int], cols: int,
         title: str, out: Path) -> None:
    band = 34
    rows = (len(names) + cols - 1) // cols
    w = cell[0] * cols
    h = 66 + rows * (cell[1] + band)
    canvas = Image.new("RGB", (w, h), (16, 18, 26))
    d = ImageDraw.Draw(canvas)
    d.text((24, 16), title, font=font(26), fill=(240, 240, 246))
    for i, name in enumerate(names):
        c, r = i % cols, i // cols
        x, y = c * cell[0], 66 + r * (cell[1] + band)
        d.rectangle((x, y, x + cell[0], y + band), fill=(26, 29, 40))
        d.text((x + 12, y + 7), LABELS.get(name, name),
               font=font(17), fill=(255, 214, 140))
        canvas.paste(tile(name, box, cell), (x, y + band))
    canvas.save(out)
    print("WROTE", out.name, canvas.size, out.stat().st_size)


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    all_names = list(LABELS)
    grid(all_names, BOTH_BOX, (640, 250), 2,
         "朝向扫描 · 同进程同树，一次只改一侧（裁角色区域）",
         BOARDS / "orientation-overview.png")
    grid([n for n in all_names if n.startswith("p-")], P_BOX,
         (560, 500), 2, "玩家侧四组（放大）", BOARDS / "orientation-player-four-groups.png")
    grid([n for n in all_names if n.startswith("f-")], F_BOX,
         (560, 500), 2, "对手侧四组（放大）", BOARDS / "orientation-foe-four-groups.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
