"""尺度可读性判据：下采样是不可逆的信息损失，用 MAE 量化。

对每一档 h_target：
  参考 ref = 原图直接 LANCZOS 到显示尺寸 400px 高
  实验 up  = 原图先降到 h_target，再 LANCZOS 放大回 400px 高
  MAE(up, ref) 越大，说明这一档丢掉的细节越多。

1100 档本身就是 ref，MAE 应为 0；其余档必须严格递增，
否则「尺度越小越糊」只是肉眼印象而非可复算事实。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
SRC = SHOTS / "godot-front.png"
OUT = HERE / "scale_metrics.json"
DISPLAY_H = 400


def fit_h(img: Image.Image, h: int) -> Image.Image:
    return img.resize((max(1, round(img.width * h / img.height)), max(1, h)),
                      Image.Resampling.LANCZOS)


def mae(a: Image.Image, b: Image.Image) -> float:
    stat = ImageStat.Stat(ImageChops.difference(a, b))
    return round(sum(stat.mean) / 3.0, 4)


def main() -> int:
    stats = json.loads((HERE / "board_stats.json").read_text(encoding="utf-8"))
    targets: list[int] = stats["scale_steps"]
    src = Image.open(SRC).convert("RGB")
    ref = fit_h(src, DISPLAY_H)
    rows = []
    for h in targets:
        up = fit_h(fit_h(src, h), DISPLAY_H)
        rows.append({
            "target_h": h,
            "downscaled_w": max(1, round(src.width * h / src.height)),
            "mae_vs_direct_400": mae(up, ref),
            "display": {"w": ref.width, "h": ref.height},
        })
    increasing = all(rows[i]["mae_vs_direct_400"] < rows[i + 1]["mae_vs_direct_400"]
                     for i in range(len(rows) - 1))
    out = {
        "source": str(SRC),
        "source_size": [src.width, src.height],
        "display_height": DISPLAY_H,
        "rows": rows,
        "strictly_increasing": increasing,
        "baseline_zero": rows[0]["mae_vs_direct_400"] == 0.0,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print(f"H={r['target_h']:>5}  down={r['downscaled_w']:>4}px wide  "
              f"MAE={r['mae_vs_direct_400']:.4f}")
    print(f"STRICTLY_INCREASING={increasing} BASELINE_ZERO={out['baseline_zero']}")
    print("SCALE_METRICS_OK" if increasing and out["baseline_zero"]
          else "SCALE_METRICS_FAILED")
    return 0 if increasing and out["baseline_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
