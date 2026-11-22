"""玩家 V4b vs 对手怪 V1 的 3D 同相机对照板。

两张都是 Blender 5.2.3 / EEVEE / ORTHO 2.30 / target_z 0.86 / 768² 透明底，
相机参数完全相同，所以直接并排就是公平对比，不用再缩放对齐。
底部数字从 blender_build.json / model_inspection.json / rigfit_result.json 读，
不写死；脚本不评好看，只把可复算的结构事实摆出来。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
PLAYER = BAKE / "3d-model-probe-v4b" / "v4b-front.png"
FOE = HERE / "foe-front.png"
OUT = HERE / "player-V4b-foe-3D-comparison.png"

FONT = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")
CYAN = (70, 210, 230)
ORANGE = (232, 148, 78)
WHITE = (238, 240, 246)
MUTED = (152, 162, 182)
# 看图修的：初版 (42,46,56) 太暗，深色对手怪在深灰卡片上轮廓发糊，
# 明度实测 0.3256 vs 玩家 0.5667 本来就是设计目标，但展示板不该把它吃掉。
# 两列统一提亮一档，保持「同底」的公平性，不单独改对手怪那一列。
CARD = (70, 74, 86)
EDGE = (86, 94, 112)
W, H = 1700, 1060


def fnt(size, bold=False):
    p = FONT_BOLD if bold else FONT
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def label(im, x, y, t, size, color=WHITE, bold=False):
    ImageDraw.Draw(im).text((x, y), t, font=fnt(size, bold), fill=color)


def on_card(im, src: Path, x: int) -> list[int]:
    """透明图合成到中灰卡片，返回 alpha>8 的人物 bbox（相对卡片）。"""
    with Image.open(src) as f:
        art = f.convert("RGBA")
    alpha = art.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    bb = alpha.getbbox()
    assert bb, f"empty alpha: {src.name}"
    card = Image.new("RGBA", art.size, CARD + (255,))
    card.alpha_composite(art)
    im.paste(card.convert("RGB"), (x, 130))
    return list(bb)


def main() -> None:
    assert PLAYER.is_file(), f"missing {PLAYER}"
    assert FOE.is_file(), f"missing {FOE}"
    build = json.loads((HERE / "blender_build.json").read_text(encoding="utf-8"))
    insp = json.loads((HERE / "model_inspection.json").read_text(encoding="utf-8"))
    rig = {}
    if (HERE / "rigfit_result.json").is_file():
        rig = json.loads((HERE / "rigfit_result.json").read_text(encoding="utf-8"))
    auto = rig.get("automatic_weights", {})
    auto_txt = (f"{auto.get('covered_vertices', '?')}/{auto.get('total_vertices', '?')}"
                if auto else "未跑")

    img = Image.new("RGB", (W, H), (18, 20, 26))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        k = y / H
        d.rectangle((0, y, W, y + 4),
                    fill=(round(18 + 10 * k), round(20 + 9 * k), round(26 + 12 * k)))
    d.rectangle((50, 28, 1650, 30), fill=CYAN)
    label(img, 50, 44, "《牌拳》玩家 V4b  vs  对手怪 V1 · 3D 同相机对照", 30, WHITE, True)
    label(img, 50, 90,
          "Blender 5.2.3 EEVEE · ORTHO 2.30 · target_z 0.86 · 768² · 保留生成模型自带 PBR，不加 toon / 描边",
          14, MUTED)

    pbb = on_card(img, PLAYER, 50)
    fbb = on_card(img, FOE, 882)
    label(img, 54, 916, "玩家  /  V4b 定稿", 20, WHITE, True)
    label(img, 54, 948, f"透明底人物 bbox={pbb} · 纤细 · 浅色 · 露脸 · 长衫", 14, CYAN)
    label(img, 886, 916, "对手怪  /  V1 图生 3D", 20, WHITE, True)
    label(img, 886, 948, f"透明底人物 bbox={fbb} · 宽肩 · 深色 · 覆面 · 硬壳", 14, ORANGE)

    d.line((50, 986, 1650, 986), fill=EDGE, width=1)
    facts = (
        f"对手怪结构：{insp.get('vertices_total', '?')} 顶点 / "
        f"{insp.get('triangles_total', '?')} 三角 / "
        f"{insp.get('connected_shells_unionfind', '?')} 连通壳 / "
        f"{insp.get('counts', {}).get('skins', '?')} skins / "
        f"{insp.get('counts', {}).get('animations', '?')} animations"
    )
    label(img, 50, 998, facts, 13, MUTED)
    label(img, 50, 1022,
          f"Blender 建模：归一化身高 1.72 m（scale={build['normalize']['scale']}）· "
          f"13 骨 Armature · 刚性权重覆盖 {build['armature']['coverage']} · "
          f"自动绑骨覆盖 {auto_txt} · 游戏源码 0 改动",
          13, MUTED)

    img.save(OUT)
    print(json.dumps({"file": OUT.name, "bytes": OUT.stat().st_size,
                      "player_bbox": pbb, "foe_bbox": fbb,
                      "size": list(img.size)}, ensure_ascii=False))
    print("FOE_COMPARE_OK")


if __name__ == "__main__":
    main()
