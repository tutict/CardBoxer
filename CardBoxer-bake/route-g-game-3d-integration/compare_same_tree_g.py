"""G 路线：同树同状态 3D A/B 的像素判据（跨运行噪声为零的硬证据）。

用法：python compare_same_tree_g.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "ab_same_tree"
BOARDS = HERE / "boards"
DATA = HERE / "data"
OUT = DATA / "same_tree_ab_g.json"
ROI = (290, 270, 580, 535)
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")

NAMES = ["off", "on-stance", "on-jab6", "on-wave17"]


def diff(a: Image.Image, b: Image.Image, box=None) -> int:
    x = a.convert("RGB") if box is None else a.convert("RGB").crop(box)
    y = b.convert("RGB") if box is None else b.convert("RGB").crop(box)
    return sum(1 for p in ImageChops.difference(x, y).get_flattened_data()
               if p != (0, 0, 0))


def font(sz: int):
    if FONT_PATH.is_file():
        return ImageFont.truetype(str(FONT_PATH), sz)
    return ImageFont.load_default()


def make_board(ims: dict, out: Path) -> None:
    w, h, pad, label_h = 470, 265, 14, 28
    canvas = Image.new("RGB", (2 * (w + pad) + pad,
                              2 * (h + label_h + pad) + pad), (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = font(18)
    for i, name in enumerate(NAMES):
        r, c = divmod(i, 2)
        x, y = pad + c * (w + pad), pad + r * (h + label_h + pad)
        canvas.paste(ims[name].resize((w, h)), (x, y))
        d.text((x + 4, y + h + 2), name, font=f, fill=(150, 220, 200))
    canvas.save(out)


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    paths = {n: SHOTS / ("ab-%s.png" % n) for n in NAMES}
    ims = {n: Image.open(p).convert("RGB") for n, p in paths.items()
           if p.is_file()}
    if len(ims) != 4:
        print("MISSING PNG", set(NAMES) - set(ims))
        return 1

    full = {}
    roi = {}
    for a, b in [("off", "on-stance"), ("on-stance", "on-jab6"),
                 ("on-jab6", "on-wave17"), ("on-stance", "on-wave17")]:
        full[f"{a}__{b}"] = diff(ims[a], ims[b])
        roi[f"{a}__{b}"] = diff(ims[a], ims[b], ROI)
    outside = {k: full[k] - roi[k] for k in full}

    probe = json.loads((DATA / "three_d_ab.json").read_text(encoding="utf-8"))
    rows = {r["name"]: r for r in probe.get("payload", {}).get("shots", [])}
    prims_off = rows.get("off", {}).get("prims_mean", 0)
    prims_on = rows.get("on-stance", {}).get("prims_mean", 0)

    checks = {
        "all_png_1280x720": all(im.size == (1280, 720) for im in ims.values()),
        "3d_visible_in_roi": roi["off__on-stance"] > 5000,
        "outside_roi_clean": all(v < 1500 for v in outside.values()),
        "stance_vs_jab6_distinct": roi["on-stance__on-jab6"] > 500,
        "jab6_vs_wave17_distinct": roi["on-jab6__on-wave17"] > 500,
        "stance_vs_wave17_distinct": roi["on-stance__on-wave17"] > 500,
        "prims_grew": prims_on > prims_off * 10,
        "prims_stable_across_frames": all(
            rows.get(n, {}).get("prims_mean") == prims_on
            for n in ("on-jab6", "on-wave17")),
        "probe_ok": probe.get("ok") is True,
    }
    failed = [k for k, v in checks.items() if not v]
    ok = not failed
    OUT.write_text(json.dumps({
        "roi": list(ROI), "full_changed_px": full,
        "roi_changed_px": roi, "outside_roi_changed_px": outside,
        "prims": {"off": prims_off, "on": prims_on,
                  "ratio": round(prims_on / prims_off, 3) if prims_off else None},
        "draw_calls": {n: rows.get(n, {}).get("draw_calls_mean")
                       for n in NAMES},
        "checks": checks, "failed": failed, "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    make_board(ims, BOARDS / "G-same-scene-3d-dual-track-AB.png")

    for k in full:
        print(f"{k:34s} full={full[k]:>7} roi={roi[k]:>7} "
              f"outside={outside[k]:>7}")
    print(f"PRIMS off={prims_off:.0f} on={prims_on:.0f} "
          f"ratio={prims_on / prims_off:.2f}x" if prims_off else "PRIMS n/a")
    for k in failed:
        print("  FAIL", k)
    print("SAME_TREE_AB_G_OK" if ok else "SAME_TREE_AB_G_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
