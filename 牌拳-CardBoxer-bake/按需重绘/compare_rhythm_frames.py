"""节奏帧跨运行对比 —— 负结果诊断，不是判据。

本想用「手牌区以上逐像素 identical」证明节奏层没被停刷成旧帧，实测失败：
8 张全部 changed≈60 万像素，振幅直方图以 ±0..6 大面积低振幅为主
（背景纹理在 --resolution 1280x720 与 project.godot 的 1600x900 stretch
下重采样不同），另有一簇 ~13 的偏移和角色/HIT 区域的高振幅差异（呼吸相位
逐帧不同、手牌随机）。是跨运行渲染差异，不是门控回归，但也不是可判据的
零差异 —— 和上轮「全局 RNG 每次启动随机化」同类。

因此退役该判据：节奏层兼容性改由「同一进程的 5 段注入态像素 A/B」+
「8/8 注入式节奏截帧成功且 HIT 标签/星芒可见」承担。本脚本只留可复算
的振幅证据。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
NEW = HERE / "节奏回归帧1280"
OLD = BAKE / "引擎优化" / "回归帧"
HAND_Y = 540


def main() -> int:
    rows = []
    for p in sorted(NEW.glob("节奏帧-*.png")):
        q = OLD / p.name
        if not q.is_file():
            rows.append({"png": p.name, "baseline": "MISSING"})
            continue
        a = Image.open(p).convert("RGB")
        b = Image.open(q).convert("RGB")
        if a.size != b.size:
            rows.append({"png": p.name, "size": [a.size, b.size], "baseline": "SIZE_MISMATCH"})
            continue
        d = ImageChops.difference(a, b)
        above = d.crop((0, 0, a.width, HAND_Y))
        hist = Counter(max(px) for px in above.get_flattened_data())
        total = a.width * HAND_Y
        low = sum(n for k, n in hist.items() if k <= 6)
        rows.append({
            "png": p.name,
            "bytes": p.stat().st_size,
            "size": [a.width, a.height],
            "above_hand_px": total,
            "above_hand_low_amp_le6": low,
            "above_hand_low_amp_pct": round(low / total * 100.0, 3),
            "above_hand_max_delta": max(hist.keys()),
            "top_amplitudes": [[int(k), int(v)] for k, v in hist.most_common(6)],
            "baseline": "CROSS_RUN_NOT_COMPARABLE",
        })
        print("%-32s bytes=%-8d low_amp<=6: %6.2f%%  max=%d  %s"
              % (p.name, p.stat().st_size, low / total * 100.0,
                 max(hist.keys()), "CROSS_RUN_NOT_COMPARABLE"))
    payload = {
        "verdict": "CRITERION_RETIRED",
        "reason": "predominantly low-amplitude (+/-0..6, plus a ~13 cluster) background "
                  "resampling shift, plus high-amplitude local differences from per-run "
                  "breathing phase and random hand; cross-run pixel equality is not a "
                  "valid gate regression test",
        "hand_area_y0": HAND_Y,
        "frames": rows,
    }
    (HERE / "节奏回归诊断.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RHYTHM_DIAG: CRITERION_RETIRED frames=%d" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
