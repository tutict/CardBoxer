"""H 路线：把双侧角色的 ROI 放大，并做像素级「两人是否同一造型」核对。

左右 ROI 取同样尺寸，逐像素比对；若差异很小就说明渲染串味了。
输出 boards/H-双侧角色特写.png 与 data/zoom_h.json。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOT = HERE / "shots" / "two_side_ab" / "h-both-stance.png"
OUT = HERE / "boards" / "H-双侧角色特写.png"
DATA = HERE / "data" / "zoom_h.json"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
ROI_JSON = HERE / "data" / "roi_h.json"


def main() -> int:
    assert SHOT.is_file() and ROI_JSON.is_file()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    # 不手填 ROI：按 diag_roi_h.py 从 off/on 逐列差异自动定位的两个区域。
    roi = json.loads(ROI_JSON.read_text(encoding="utf-8"))
    assert roi["two_regions"] is True, roi
    left_box, right_box = roi["boxes"][:2]
    im = Image.open(SHOT).convert("RGB")
    w = min(left_box[2] - left_box[0], right_box[2] - right_box[0])
    h = min(left_box[3] - left_box[1], right_box[3] - right_box[1])
    def centered(box):
        cx = (box[0] + box[2]) // 2
        cy = (box[1] + box[3]) // 2
        return (cx - w // 2, cy - h // 2,
                cx - w // 2 + w, cy - h // 2 + h)
    LEFT, RIGHT = centered(left_box), centered(right_box)
    a = im.crop(LEFT)
    b = im.crop(RIGHT)
    assert a.size == b.size, (a.size, b.size)
    diff = ImageChops.difference(a, b)
    changed = sum(1 for px in diff.get_flattened_data()
                  if px != (0, 0, 0))
    total = a.width * a.height
    ratio = changed / total

    z = 2
    w, h = a.width * z, a.height * z
    pad, label = 24, 40
    canvas = Image.new("RGB", (2 * w + 3 * pad, h + label + 2 * pad),
                       (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 22) if FONT.is_file() \
        else ImageFont.load_default()
    canvas.paste(a.resize((w, h), Image.LANCZOS), (pad, pad))
    canvas.paste(b.resize((w, h), Image.LANCZOS), (2 * pad + w, pad))
    d.text((pad + 6, pad + h + 6), "左侧 · 玩家 V4b（+55°）",
           font=f, fill=(160, 225, 205))
    d.text((2 * pad + w + 6, pad + h + 6), "右侧 · 对手怪（-55°）",
           font=f, fill=(160, 225, 205))
    canvas.save(OUT)

    report = {"shot": SHOT.name, "left_roi": list(LEFT),
              "right_roi": list(RIGHT), "roi_size": list(a.size),
              "auto_boxes": [left_box, right_box],
              "changed_px": changed, "total_px": total,
              "changed_ratio": round(ratio, 4),
              # 注：这个比值含擂台背景差异，只作「不是同一张图」的辅助；
              # 「两个不同模型」的硬证据是引擎自报的 glb_path / mesh_name。
              "distinct": ratio > 0.15,
              "board": OUT.name, "board_bytes": OUT.stat().st_size}
    DATA.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print("ROI", a.size, "changed_px", changed, "/", total,
          "ratio", round(ratio, 4), "distinct", report["distinct"])
    print("ZOOM_H_OK" if report["distinct"] else "ZOOM_H_FAILED")
    return 0 if report["distinct"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
