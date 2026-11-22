"""Pixel evidence that the two P0 human-input HUD states are really drawn.

Mark colours used by hud.gd:
  discard mark  Color(0.98, 0.42, 0.36) -> ~(250, 107,  92)
  select  mark  Color(0.98, 0.80, 0.36) -> ~(250, 204,  92)

Two traps found while writing this (both are "aggregate statistics lie"):
  1. Counting all matching pixels in the hand area: the orange-red "进攻"
     label on every card also lands near the discard mark colour, so the
     select frame still had 2812 "red" pixels with no red selection border.
  2. Even the longest horizontal run is not enough: each card has a CATEGORY
     colour bar (attack cards = red) 7 px below the card top, which is a
     146 px continuous red line in the select frame.
The selection border sits on the card TOP EDGE row (y=524). The criterion
therefore compares the two colours ON THAT SAME ROW, not globally.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

SHOTS = Path(r"D:\Projects\CardBoxer\CardBoxer-bake\background-candidates\classic-battle-p0")
FILES = {"discard": SHOTS / "discard-selection.png", "select": SHOTS / "card-selection.png"}
TARGETS = {"red_mark": (250, 107, 92), "gold_mark": (250, 204, 92)}
BORDER_ROW = 524
CATEGORY_ROW = 531


def near(px, target, tol: int = 26) -> bool:
    return all(abs(px[i] - target[i]) <= tol for i in range(3))


def run_on_row(pixels, width: int, y: int, target) -> int:
    best, run = 0, 0
    for x in range(width):
        if near(pixels[x, y], target):
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def main() -> int:
    rows: dict[str, dict[int, dict[str, int]]] = {}
    hashes: dict[str, str] = {}
    for mode, path in FILES.items():
        hashes[mode] = hashlib.sha256(path.read_bytes()).hexdigest()
        im = Image.open(path).convert("RGB")
        px = im.load()
        rows[mode] = {
            y: {name: run_on_row(px, im.width, y, target) for name, target in TARGETS.items()}
            for y in (BORDER_ROW, CATEGORY_ROW)
        }
        b, c = rows[mode][BORDER_ROW], rows[mode][CATEGORY_ROW]
        print("%-8s %dx%d sha=%s | top y=524 red=%3d gold=%3d | cat y=531 red=%3d gold=%3d" % (
            mode, im.width, im.height, hashes[mode][:12],
            b["red_mark"], b["gold_mark"], c["red_mark"], c["gold_mark"],
        ))

    d = rows["discard"][BORDER_ROW]
    s = rows["select"][BORDER_ROW]
    ok = (
        hashes["discard"] != hashes["select"]
        and d["red_mark"] >= 100 and d["gold_mark"] < 30
        and s["gold_mark"] >= 100 and s["red_mark"] < 30
    )
    print("EVIDENCE %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
