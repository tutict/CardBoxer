"""Check actual transparent SubViewport captures for empty/clipped characters."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image


def check(root: Path, padding: int = 4) -> dict:
    rows = []
    for path in sorted(root.glob("*.png")):
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A").point(lambda value: 255 if value > 16 else 0)
            bounds = alpha.getbbox()
            width, height = rgba.size
        clipped = bounds is None or bounds[0] < padding or bounds[1] < padding \
            or bounds[2] > width - padding or bounds[3] > height - padding
        rows.append({"file": path.name, "size": [width, height],
                     "bounds": bounds, "clipped": clipped})
    failed = [row for row in rows if row["clipped"]]
    return {"ok": bool(rows) and not failed, "images": len(rows),
            "failed": len(failed), "padding": padding, "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.root)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"CAPTURE_FRAMING: {'PASS' if result['ok'] else 'FAIL'} "
          f"({result['images']} images, {result['failed']} clipped/empty)")
    for row in [row for row in result["rows"] if row["clipped"]][:8]:
        print(row["file"], row["bounds"], row["size"])
    raise SystemExit(0 if result["ok"] else 1)
