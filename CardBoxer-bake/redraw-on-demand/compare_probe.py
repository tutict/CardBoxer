"""对 A/B 五张 PNG 做逐像素比对，并输出帧统计摘要。"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
OUT = HERE / "comparison-frames"


def changed(a: Path, b: Path) -> tuple[int, tuple]:
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return -1, (ia.size, ib.size)
    diff = ImageChops.difference(ia, ib)
    bbox = diff.getbbox()
    n = 0 if bbox is None else sum(
        1 for px in diff.get_flattened_data() if px != (0, 0, 0))
    return n, (bbox, ia.size)


def main() -> int:
    data = json.loads((OUT / "probe_result.json").read_text(encoding="utf-8"))
    for ph in data["phases"]:
        raw = ph["raw_process_ms"]
        s = sorted(raw)
        print("%-12s gate=%-5s mean=%.4f median=%.4f min=%.4f max=%.4f n=%d"
              % (ph["name"], ph["gate"], ph["process_ms"]["mean"],
                 ph["process_ms"]["median"], s[0], s[-1], len(raw)))
        print("              raw_head=%s raw_tail=%s"
              % ([round(x, 3) for x in raw[:5]], [round(x, 3) for x in raw[-5:]]))
    pairs = [
        ("A_still-disabled.png", "B_still-enabled.png", "静止像素等价"),
        ("C_modified-enabled.png", "D_modified-disabled.png", "变更后像素等价"),
        ("E_rollback-enabled.png", "A_still-disabled.png", "回退像素等价"),
        ("A_still-disabled.png", "C_modified-enabled.png", "状态变化必须可见(非0)"),
    ]
    result = {}
    for a, b, label in pairs:
        n, extra = changed(OUT / a, OUT / b)
        print("%-24s %s vs %s  changed=%d  %s" % (label, a, b, n, extra))
        result[label] = {"a": a, "b": b, "changed_px": n, "extra": str(extra)}
    for name in ["A_still-disabled.png", "B_still-enabled.png", "C_modified-enabled.png",
                 "D_modified-disabled.png", "E_rollback-enabled.png"]:
        p = OUT / name
        print("PNG %-24s %d B" % (name, p.stat().st_size))
        result[name] = p.stat().st_size
    (OUT / "compare_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
