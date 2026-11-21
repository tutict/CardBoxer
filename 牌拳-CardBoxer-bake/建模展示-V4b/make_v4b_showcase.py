"""把 V4b 的 7 张同相机渲染拼成一张大展示板。

只做排版与合成，不改任何渲染图、不加 toon / 描边 / 调色：
工程师选的是 PBR 服务预览原图，展示板必须保留同一材质口径。
相机参数与结构统计全部从 render_v4b.json / model_inspection.json 读，
不写死数字。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V4B = BAKE / "3D模型探针V4b"

RENDER = json.loads((V4B / "render_v4b.json").read_text(encoding="utf-8"))
INSPECT = json.loads((V4B / "model_inspection.json").read_text(encoding="utf-8"))
SHOTS = {s["shot"]: s for s in RENDER["shots"]}

FONT = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")

W, H = 1800, 1320
BG = (18, 20, 26)
CARD = (48, 52, 62, 255)
EDGE = (86, 94, 112, 255)
CYAN = (70, 210, 230)
WHITE = (238, 240, 246)
MUTED = (150, 160, 180)

ROWS = [
    {
        "title": "全身四视角  /  FULL BODY",
        # 头部文字到 y≈131；栏标题 156，卡片 186..586，两行标签 594 / 616
        "title_y": 156, "y": 186, "cw": 400, "ch": 400, "gap": 20, "x0": 60,
        "items": [
            ("front", "正面 0°"),
            ("angle25", "斜视 25°"),
            ("angle55", "侧视 55°"),
            ("back35", "背面 -35°"),
        ],
    },
    {
        "title": "脸模与配饰特写  /  FACE & DETAILS",
        # 上一行标签到 y≈629；栏标题 666，卡片 696..1196，两行标签 1204 / 1226
        "title_y": 666, "y": 696, "cw": 500, "ch": 500, "gap": 40, "x0": 110,
        "items": [
            ("face-front", "脸部正面 · 琥珀分层虹膜"),
            ("face-25", "脸部 25° · 侧面五官"),
            ("upper", "上半身 · 叠穿与配饰"),
        ],
    },
]


def fnt(size: int, bold: bool = False):
    p = FONT_BOLD if bold else FONT
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def label(im: Image.Image, x: int, y: int, text: str, size: int,
          color=WHITE, bold: bool = False) -> None:
    ImageDraw.Draw(im).text((x, y), text, font=fnt(size, bold), fill=color)


def tile(shot: str, cw: int, ch: int) -> Image.Image:
    """透明渲染图 contain 进圆角卡片，人物居中，原 alpha 保留。"""
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle(
        (0, 0, cw - 1, ch - 1), radius=10, fill=CARD, outline=EDGE, width=1)
    p = V4B / SHOTS[shot]["file"]
    with Image.open(p) as f:
        art = f.convert("RGBA")
    art = ImageOps.contain(art, (cw - 20, ch - 20), Image.Resampling.LANCZOS)
    card.alpha_composite(art, ((cw - art.width) // 2, (ch - art.height) // 2))
    return card


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        k = y / H
        d.rectangle((0, y, W, y + 4),
                    fill=(round(18 + 10 * k), round(20 + 9 * k), round(26 + 12 * k)))

    d.rectangle((60, 30, 1740, 32), fill=CYAN)
    label(img, 60, 44, "《牌拳》V4b 定稿造型 · 建模渲染总览", 34, WHITE, True)
    label(img, 60, 92,
          f"{RENDER['blender']} · 7-shot 同相机正交渲染 · 保留 PBR 原材质 · "
          "静态模型（0 骨架 / 0 动画）", 15, MUTED)
    label(img, 60, 116, "离线渲染 · 非游戏内实渲 · 游戏源码未改", 13, (120, 130, 148))

    used = []
    for row in ROWS:
        label(img, row["x0"], row["title_y"], row["title"], 16, CYAN, True)
        for i, (shot, caption) in enumerate(row["items"]):
            x = row["x0"] + i * (row["cw"] + row["gap"])
            card = tile(shot, row["cw"], row["ch"])
            img.paste(card, (x, row["y"]), card)
            s = SHOTS[shot]
            label(img, x + 4, row["y"] + row["ch"] + 8, caption, 15, WHITE, True)
            label(img, x + 4, row["y"] + row["ch"] + 30,
                  f"{s['file']} · {s['resolution']}² · angle {s['angle_deg']}° · "
                  f"ortho {s['ortho_scale']}", 11, MUTED)
            used.append(s["file"])

    c = INSPECT["counts"]
    verts = INSPECT["vertices_total"]
    tris = INSPECT["triangles_total"]
    shells = INSPECT["connected_shells_unionfind"]
    d.rounded_rectangle((60, 1255, 1740, 1310), radius=8,
                        fill=(32, 35, 44), outline=EDGE, width=1)
    label(img, 78, 1262, "结构实测", 15, CYAN, True)
    label(img, 78, 1286,
          f"GLB：{verts:,} 顶点 / {tris:,} 三角 / {c['textures']} 张内嵌 PBR 贴图 / "
          f"{c['skins']} skins / {c['animations']} animations / {shells:,} 连通壳 · "
          "自动绑骨 0 覆盖 —— 换造型换不出骨架", 14, (206, 214, 228))
    label(img, 1500, 1262, "V4b · 2026-11-07", 13, MUTED)

    out = HERE / "V4b-建模展示板.png"
    img.save(out)

    manifest = {
        "note": "V4b 七张同相机渲染的排版总览；只做合成，不改渲染图/材质",
        "source_dir": str(V4B),
        "source_files": {f: sha256(V4B / f) for f in used},
        "render_params_sha256": sha256(V4B / "render_v4b.json"),
        "inspection_sha256": sha256(V4B / "model_inspection.json"),
        "canvas": [W, H],
        "output": {"file": out.name, "bytes": out.stat().st_size, "sha256": sha256(out)},
    }
    (HERE / "showcase_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": out.name, "size": [W, H],
                      "tiles": len(used), "bytes": out.stat().st_size}, ensure_ascii=False))
    print("SHOWCASE_OK")


if __name__ == "__main__":
    main()
