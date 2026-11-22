"""两张说明板：为什么之前只看到对手怪 / 女角色 Godot 内四视角。

图源全部是真实引擎内截帧，不重画、不合成人物；数字现读 JSON。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BOARDS = HERE / "boards"
SHOTS = HERE / "shots"
D_SHOTS = BAKE / "route-d-creative-review-captures" / "shots"

BG = (18, 24, 36)
CARD = (30, 38, 54)
FG = (236, 240, 250)
MUTED = (152, 164, 184)
ACCENT = (240, 214, 160)
GOOD = (126, 214, 168)
BAD = (238, 132, 118)


def font(size: int, bold: bool = False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc",) if bold else (
        r"C:\Windows\Fonts\msyh.ttc",)
    for p in names + (r"C:\Windows\Fonts\msyh.ttc",):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = font(32, True)
F_SUB = font(17)
F_H = font(22, True)
F_B = font(17)
F_S = font(15)


def contain(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    w, h = img.size
    bw, bh = box
    s = min(bw / w, bh / h)
    return img.resize((max(1, int(w * s)), max(1, int(h * s))),
                      Image.Resampling.LANCZOS)


def paste(canvas: Image.Image, p: Path,
          box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    img = contain(Image.open(p).convert("RGB"), (w, h))
    canvas.paste(img, (x + (w - img.width) // 2, y + (h - img.height) // 2))


def header(d, title: str, sub: str, w: int) -> None:
    d.text((40, 24), title, font=F_TITLE, fill=FG)
    d.text((40, 70), sub, font=F_SUB, fill=MUTED)
    d.line((40, 108, w - 40, 108), fill=CARD, width=2)


def board1(result: dict, d_result: dict) -> Path:
    w, h = 1800, 1300
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    header(d, "为什么你在 Godot 里只看到对手怪的 3D",
           "左右两张都是 Godot 4.5 引擎内真实截帧，不是 Blender 渲染；"
           "差别在工程有没有搭展示场景", w)

    left = SHOTS / "godot-player-front.png"
    right = D_SHOTS / "godot-front.png"
    for x, path, label, note, col in (
            (40, left, "女角色 V4b（玩家）",
             "E 路线 player-full.glb / 本轮新建展示工程", GOOD),
            (920, right, "对手怪（ foe ）",
             "D 路线 foe-full.glb / 已有展示工程", BAD)):
        d.rounded_rectangle((x, 150, x + 840, 150 + 920), radius=10,
                            fill=CARD)
        paste(im, path, (x + 20, 170, 800, 850))
        d.text((x + 20, 1038), label, font=F_H, fill=col)
        d.text((x + 20, 1074), note, font=F_S, fill=MUTED)

    lines = [
        ("D 路线探针工程：搭了六视角棚拍场景，导入的是 foe-*.glb  ->  你看到的是对手怪。", BAD),
        ("E 路线探针工程：run/main_scene=\"\"，只做资源结构读回，没有把女角色摆进场景  ->  打开是空的。", ACCENT),
        ("本轮新建 probe_project_player：main_scene=player_showcase.tscn，打开按 F5 即见女角色。", GOOD),
        ("两者都是静态 A-pose / 0 animation；可见性差别，不是资产缺失。", MUTED),
    ]
    y = 1130
    for text, col in lines:
        d.text((40, y), text, font=F_B, fill=col)
        y += 34
    out = BOARDS / "female-vs-foe-Godot-comparison.png"
    im.save(out)
    return out


def board2(result: dict) -> Path:
    w, h = 1800, 1300
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    header(d, "女角色 V4b · Godot 4.5 引擎内四视角",
           "同一份 player-full.glb、同一套固定灯光；"
           "4096² PBR 与投影全部生效，代理壳已隐藏", w)
    labels = {"front": "正面 0°", "angle35": "斜 35°",
              "side90": "侧面 90°", "back": "背面 180°"}
    for i, row in enumerate(result["pngs"]):
        col, r = i % 2, i // 2
        x, y = 40 + col * 880, 140 + r * 570
        d.rounded_rectangle((x, y, x + 850, y + 545), radius=10, fill=CARD)
        paste(im, Path(row["path"]), (x + 20, y + 16, 810, 480))
        d.text((x + 20, y + 510),
               f"{labels.get(row['name'], row['name'])}   "
               f"{row['w']}x{row['h']}  {row['bytes']:,} B",
               font=F_S, fill=MUTED)
    out = BOARDS / "female-character-Godot-four-views.png"
    im.save(out)
    return out


def main() -> int:
    result = json.loads((HERE / "godot_player_result.json").read_text(
        encoding="utf-8"))
    d_result = json.loads((BAKE / "route-d-creative-review-captures" /
                           "godot_render_result.json").read_text(
                               encoding="utf-8"))
    assert result["ok"] is True, "godot_player_result not ok"
    assert d_result["ok"] is True, "d route render not ok"
    BOARDS.mkdir(exist_ok=True)
    outs = [board1(result, d_result), board2(result)]
    stats = {"boards": [{"file": p.name, "w": Image.open(p).width,
                         "h": Image.open(p).height,
                         "bytes": p.stat().st_size} for p in outs],
             "views": [x["name"] for x in result["pngs"]],
             "hidden_proxy_shell": result["scene"]["hidden_proxy_shell"],
             "visible_highpoly": result["scene"]["visible_highpoly"]}
    (HERE / "showcase_boards.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for b in stats["boards"]:
        print(f"BOARD {b['file']:<34} {b['w']}x{b['h']} {b['bytes']} B")
    on_disk = sorted(p.name for p in BOARDS.glob("*.png"))
    listed = sorted(b["file"] for b in stats["boards"])
    if on_disk != listed:
        print(f"BOARD_LIST_MISMATCH disk={on_disk} listed={listed}")
        return 1
    print("SHOWCASE_BOARDS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
