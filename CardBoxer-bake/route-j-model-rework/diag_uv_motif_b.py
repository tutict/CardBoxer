"""B 路线决定性诊断：青冠 / 红花 / 白布青云纹是几何还是烘进贴图的图案？

引擎内 round2 的 j-sv-foe.png 里这些元素仍在，而 GLB 已证明删掉
262 个壳 / 10,526 顶点。若它们是 baseColor 贴图上的图案（UV 岛属于
保留的 G4_BODY 大壳），则几何手术原理上碰不到，B 单独不足够。

本脚本只读：
  * 在 4096² foe baseColor 上找 cyan / warm_red / near_white 特征像素；
  * 输出 bbox、数量、4×4 网格分布；
  * 生成一张「特征高亮」放大板，让图案本身可被看图证伪。

输出 data/uv_motif_b.json、boards/B-shared-texture-features.png。
用法：python diag_uv_motif_b.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
TEX = GAME / "assets" / "3d" / "foe-rigged_texture_pbr_20250901.png"
OUT = HERE / "data" / "uv_motif_b.json"
BOARD = HERE / "boards" / "B-shared-texture-features.png"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
S = 1024


def cyan(r, g, b):
    return b > 110 and g > 110 and r < g - 18


def warm(r, g, b):
    return r > 120 and g < r * 0.65 and b < r * 0.65


def white(r, g, b):
    return r > 175 and g > 175 and b > 175


def main() -> int:
    im = Image.open(TEX).convert("RGB")
    small = im.resize((S, S), Image.LANCZOS)
    px = list(small.getdata())
    marks = []
    counts = {"cyan": 0, "warm": 0, "white": 0}
    grid = [[0] * 4 for _ in range(4)]
    bbox = {"cyan": [S, S, 0, 0], "warm": [S, S, 0, 0],
            "white": [S, S, 0, 0]}
    cell = S // 4
    for i, c in enumerate(px):
        x, y = i % S, i // S
        kinds = [k for k, fn in (("cyan", cyan), ("warm", warm),
                                 ("white", white)) if fn(*c)]
        if not kinds:
            continue
        color = ((0, 255, 255) if "cyan" in kinds else
                 (255, 60, 60) if "warm" in kinds else (255, 255, 255))
        marks.append((x, y, color))
        for k in kinds:
            counts[k] += 1
            q = bbox[k]
            q[0], q[1] = min(q[0], x), min(q[1], y)
            q[2], q[3] = max(q[2], x), max(q[3], y)
        grid[y // cell][x // cell] += 1

    # 板：左=原贴图缩略，右=原图 + 特征高亮点
    pad, label = 18, 40
    W, H = 2 * S + 3 * pad, S + 2 * pad + label
    canvas = Image.new("RGB", (W, H), (22, 26, 36))
    canvas.paste(small, (pad, pad))
    marked = small.copy()
    d2 = ImageDraw.Draw(marked)
    for x, y, color in marks:
        d2.point((x, y), fill=color)
    canvas.paste(marked, (2 * pad + S, pad))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 18) if FONT.is_file() \
        else ImageFont.load_default()
    d.text((pad, pad + S + 8), "foe baseColor 4096→1024（原图）",
           font=f, fill=(210, 220, 240))
    d.text((2 * pad + S, pad + S + 8),
           f"特征高亮：青={counts['cyan']} 暖红={counts['warm']} "
           f"近白={counts['white']}", font=f, fill=(210, 220, 240))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)

    checks = {
        "texture_is_4096": im.size == (4096, 4096),
        "cyan_pattern_present": counts["cyan"] > 200,
        "warm_pattern_present": counts["warm"] > 20,
        "cyan_is_clustered": (
            max(max(row) for row in grid)
            > 3 * max(1, sum(sum(row) for row in grid) // 16)),
        "board_written": BOARD.is_file()
                         and BOARD.stat().st_size > 100000,
    }
    report = {
        "texture": str(TEX), "orig_size": list(im.size),
        "analyzed_size": [S, S], "counts": counts,
        "ratios": {k: round(v / (S * S), 6) for k, v in counts.items()},
        "bbox_1024": bbox, "grid4x4": grid,
        "board": str(BOARD), "board_bytes": BOARD.stat().st_size,
        "conclusion": (
            "若青/暖红/近白在 foe baseColor 上聚成可辨图案，"
            "则这些同源元素是烘在保留大壳 UV 上的贴图图案，"
            "几何删壳碰不到；B 必须与贴图语义重绘组合才能根治。"),
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
    }
    report["ok"] = not report["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("COUNTS", counts, "RATIOS", report["ratios"])
    print("BBOX", bbox)
    print("GRID", grid)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("UV_MOTIF_B_OK" if report["ok"] else "UV_MOTIF_B_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
