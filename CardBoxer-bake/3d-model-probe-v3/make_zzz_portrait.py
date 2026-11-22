"""Post-process the transparent toon renders into ZZZ-style character portraits.

Outlines follow the reference's rule: a THIN line of the SAME HUE but LOWER
VALUE than the neighbouring surface, not a heavy black stroke. We approximate
the neighbour colour by dilating the premultiplied RGB, darkening it, and
painting only the 1-2px outer alpha edge.

Also: low-saturation cool-grey backdrop, soft ground shadow, 2x2 contact sheet.
Run with the project venv (Pillow 12).
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

HERE = Path(__file__).resolve().parent
SHOTS = ["front", "angle25", "angle55", "back35"]


def pixels(im):
    """Pillow 12 removed getdata(); older builds still need it."""
    if hasattr(im, "get_flattened_data"):
        return list(im.get_flattened_data())
    return list(im.getdata())


def build(src: Path, dst: Path):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    rgb = im.convert("RGB")
    alpha = im.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return {"file": src.name, "error": "EMPTY_ALPHA"}

    # low-saturation cool-grey vertical gradient
    bg = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(bg)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)],
               fill=(int(26 + 16 * t), int(28 + 16 * t), int(34 + 20 * t)))
    base = bg.convert("RGBA")

    # soft ground shadow under the feet
    cx = (bbox[0] + bbox[2]) // 2
    foot_y = bbox[3]
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        [cx - 105, foot_y - 20, cx + 105, foot_y + 16], fill=(0, 0, 0, 145))
    base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)))

    # same-hue / lower-value outline. Outer 2px goes UNDER the character,
    # inner 1px goes OVER it (so open-shell seams also read as ink lines).
    dil_a = alpha.filter(ImageFilter.MaxFilter(5))
    outer = ImageChops.subtract(dil_a, alpha)
    ero_a = alpha.filter(ImageFilter.MinFilter(3))
    inner = ImageChops.subtract(alpha, ero_a)
    premul = ImageChops.multiply(rgb, Image.merge("RGB", (alpha, alpha, alpha)))
    dilated_rgb = Image.merge("RGB", tuple(
        premul.getchannel(i).filter(ImageFilter.MaxFilter(5)) for i in range(3)))
    ink = ImageEnhance.Color(
        ImageEnhance.Brightness(dilated_rgb).enhance(0.30)).enhance(0.75)
    edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    edge.paste(ink, (0, 0), outer)
    base.alpha_composite(edge)
    base.alpha_composite(im)
    inner_edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    inner_edge.paste(ImageEnhance.Brightness(ink).enhance(1.35), (0, 0), inner)
    base.alpha_composite(inner_edge)
    base.convert("RGB").save(dst)

    a = pixels(alpha)
    opaque = sum(1 for v in a if v > 8)
    return {
        "file": src.name,
        "output": dst.name,
        "size": [w, h],
        "alpha_bbox": list(bbox),
        "opaque_pixels": opaque,
        "outer_edge_pixels": sum(1 for v in pixels(outer) if v > 0),
        "inner_edge_pixels": sum(1 for v in pixels(inner) if v > 0),
        "bytes": dst.stat().st_size,
    }


stats = []
for name in SHOTS:
    src = HERE / f"zzz-{name}.png"
    if not src.exists():
        stats.append({"shot": name, "error": "MISSING_RENDER"})
        continue
    dst = HERE / f"立绘-{name}.png"
    stats.append(build(src, dst))

# 2x2 contact sheet
thumbs = []
for name in SHOTS:
    p = HERE / f"立绘-{name}.png"
    if not p.exists():
        continue
    t = Image.open(p).convert("RGB").resize((384, 384), Image.LANCZOS)
    thumbs.append((name, t))
if thumbs:
    PAD, TOP = 12, 30
    sheet = Image.new("RGB", (384 * 2 + PAD * 3, 384 * 2 + TOP * 2 + PAD * 3),
                      (238, 240, 243))
    sd = ImageDraw.Draw(sheet)
    for i, (name, t) in enumerate(thumbs):
        col, row = i % 2, i // 2
        x = PAD + col * (384 + PAD)
        y = TOP + row * (384 + TOP + PAD)
        sd.text((x, y - 20), f"ZZZ toon | {name}", fill=(32, 36, 42))
        sheet.paste(t, (x, y))
    sheet_path = HERE / "ZZZ-four-views.png"
    sheet.save(sheet_path)

(HERE / "portrait_stats.json").write_text(
    json.dumps({"shots": stats,
                "contact_sheet": "ZZZ-four-views.png" if thumbs else None,
                "outline_rule": "same hue, lower value, 1-2px, no pure black"},
               ensure_ascii=False, indent=2), encoding="utf-8")
for s in stats:
    print("PORTRAIT", json.dumps(s, ensure_ascii=False), flush=True)
print("PORTRAIT_OK", flush=True)
