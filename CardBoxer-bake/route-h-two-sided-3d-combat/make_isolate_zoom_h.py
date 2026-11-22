"""把同进程两帧里各自的 3D 角色裁出来并排放大，做最终视觉定性。

vp-foe-hidden.png 只剩玩家层（左侧），vp-player-hidden.png 只剩对手层（右侧）。
用 diag_roi_h.py 自动定位的 ROI，不手填坐标。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
VP = HERE / "shots" / "vp_diag"
OUT = HERE / "boards" / "H-single-process-character-details.png"
ROI = HERE / "data" / "roi_h.json"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")


def main() -> int:
    boxes = json.loads(ROI.read_text(encoding="utf-8"))["boxes"]
    left, right = boxes[0], boxes[1]
    w = min(left[2] - left[0], right[2] - right[0])
    h = min(left[3] - left[1], right[3] - right[1])
    def centered(box):
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        return (cx - w // 2, cy - h // 2,
                cx - w // 2 + w, cy - h // 2 + h)
    a = Image.open(VP / "vp-foe-hidden.png").convert("RGB").crop(
        centered(left))
    b = Image.open(VP / "vp-player-hidden.png").convert("RGB").crop(
        centered(right))
    z = 2
    W, H = w * z, h * z
    pad, label = 24, 40
    canvas = Image.new("RGB", (2 * W + 3 * pad, H + label + 2 * pad),
                       (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 22) if FONT.is_file() \
        else ImageFont.load_default()
    canvas.paste(a.resize((W, H), Image.LANCZOS), (pad, pad))
    canvas.paste(b.resize((W, H), Image.LANCZOS), (2 * pad + W, pad))
    d.text((pad + 6, pad + H + 6), "玩家 V4b（仅玩家层可见）",
           font=f, fill=(160, 225, 205))
    d.text((2 * pad + W + 6, pad + H + 6), "对手怪（仅对手层可见）",
           font=f, fill=(160, 225, 205))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT)
    print("WROTE", OUT.name, OUT.stat().st_size, "B",
          "roi_size", (w, h))
    print("ISOLATE_ZOOM_OK" if OUT.stat().st_size > 10000
          else "ISOLATE_ZOOM_FAILED")
    return 0 if OUT.stat().st_size > 10000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
