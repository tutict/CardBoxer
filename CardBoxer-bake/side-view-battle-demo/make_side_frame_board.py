"""侧身动作帧关键帧板：2 行（玩家/对手）× 4 列（站架 / 刺拳 / 交叉反击 / 气功波）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BG = (232, 236, 244, 255)
SHOTS = [("stance_f000.png", "站架 S2"), ("jab_f007.png", "刺拳 f07"),
         ("cross_f013.png", "交叉反击 f13"), ("wave_f018.png", "气功波 f18")]


def font(size, bold=False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc") if bold \
        else (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf")
    for p in names:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


FT, FM, FS = font(22, True), font(16, True), font(13)


def main() -> int:
    CW, LABEL_W, GAP, TOP = 300, 100, 16, 104
    board = Image.new("RGB", (LABEL_W + 4 * CW + 3 * GAP + 20,
                              TOP + 2 * (CW + 34) + 20), (22, 25, 36))
    d = ImageDraw.Draw(board)
    d.text((20, 12), "《牌拳》侧身动作帧 · 55° 立绘 + 连续网格位移场",
           font=FT, fill=(238, 242, 252))
    d.text((20, 44), "动作幅度逐帧来自 baked2.json 侧视原始角度差（局部相对角差 + 限幅），不做正视 retarget",
           font=FS, fill=(160, 170, 190))
    d.text((20, 68), "源图已水平翻转，角色朝右 = 游戏 +x；合成战斗时对手再翻一次朝左",
           font=FS, fill=(150, 226, 246))
    for ci, (_f, label) in enumerate(SHOTS):
        d.text((LABEL_W + ci * (CW + GAP) + 4, TOP - 24), label,
               font=FM, fill=(240, 214, 160))
    for ri, tag in enumerate(("player", "foe")):
        y = TOP + ri * (CW + 34)
        d.text((8, y + CW // 2 - 10), "玩家 V4b" if tag == "player" else "对手怪 V1",
               font=FM, fill=(196, 206, 224))
        for ci, (name, _label) in enumerate(SHOTS):
            p = HERE / "frames" / tag / name
            assert p.is_file(), p
            im = Image.alpha_composite(
                Image.new("RGBA", (768, 768), BG),
                Image.open(p).convert("RGBA")).convert("RGB")
            x = LABEL_W + ci * (CW + GAP)
            board.paste(im.resize((CW, CW), Image.LANCZOS), (x, y))
    board.save(HERE / "side-view-motion-keyframe-board.png")
    print("SIDE_FRAME_BOARD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
