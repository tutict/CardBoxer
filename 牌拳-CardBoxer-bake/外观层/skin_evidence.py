"""Pixel evidence: the ON/OFF frames differ only because of the skin layer.

Both captures use the same scene and capture time (2.0s), but the bot shuffles
a fresh hand, so the CARD ROW also differs. Two consequences:
  * statistics are restricted to the fighter band (x 250..1030, y 280..545);
  * only CHANGED pixels are classified, so the shared backdrop cancels out.

First version used broad colour buckets and got it wrong: the old silhouette's
amber body was classified as "gold" and its dark limbs as "red", which made the
new costume look like it had LESS red/gold. Classifying by exact target RGB
(with a small tolerance) avoids that trap.

Targets are the literal constants in fighter_skin.gd and fighter.gd * 255.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

OUT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\外观层")
ON = OUT / "外观层-开启.png"
OFF = OUT / "外观层-回退.png"

# Fighter band: excludes the top HUD (y < 250) and the card row (y > 550).
BOX = (250, 280, 1030, 545)
TOL = 28
CHANGE_MIN = 20

TARGETS = {
    "white": (240, 240, 232),        # SkinSpec.WHITE
    "ink": (28, 28, 38),             # SkinSpec.INK
    "red": (184, 38, 41),            # SkinSpec.RED
    "gold": (219, 173, 77),          # SkinSpec.GOLD
    "player_main": (250, 168, 74),   # PALETTE_PLAYER.main (old silhouette)
    "player_dark": (133, 77, 33),    # PALETTE_PLAYER.dark
    "enemy_main": (87, 201, 245),    # PALETTE_ENEMY.main
    "enemy_dark": (33, 89, 133),     # PALETTE_ENEMY.dark
}


def near(px: tuple[int, int, int], target: tuple[int, int, int]) -> bool:
    return (
        abs(px[0] - target[0]) <= TOL
        and abs(px[1] - target[1]) <= TOL
        and abs(px[2] - target[2]) <= TOL
    )


def main() -> int:
    on = Image.open(ON).convert("RGB")
    off = Image.open(OFF).convert("RGB")
    assert on.size == off.size == (1280, 720), "unexpected capture size %s / %s" % (on.size, off.size)

    on_crop = on.crop(BOX)
    off_crop = off.crop(BOX)
    diff_crop = ImageChops.difference(on_crop, off_crop)
    w, h = on_crop.size
    on_px, off_px, diff_px = on_crop.load(), off_crop.load(), diff_crop.load()

    on_hits: Counter = Counter()
    off_hits: Counter = Counter()
    changed = 0
    for y in range(h):
        for x in range(w):
            if max(diff_px[x, y]) <= CHANGE_MIN:
                continue
            changed += 1
            a, b = on_px[x, y], off_px[x, y]
            for name, target in TARGETS.items():
                if near(a, target):
                    on_hits[name] += 1
                if near(b, target):
                    off_hits[name] += 1

    bbox = diff_crop.getbbox()
    print("fighter band %s  pixels=%d  changed=%d (%.1f%%)" % (BOX, w * h, changed, 100.0 * changed / (w * h)))
    print("diff bbox inside band: %s" % (bbox,))
    print("changed pixels classified against literal palette constants (tol=%d):" % TOL)
    print("")
    print("%-14s %10s %10s %10s" % ("target", "OFF", "ON", "ON-OFF"))
    for name in TARGETS:
        print("%-14s %10d %10d %+10d" % (name, off_hits[name], on_hits[name], on_hits[name] - off_hits[name]))

    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        if not ok:
            failures.append(msg)
        print("%s %s" % ("OK  " if ok else "FAIL", msg))

    old_body_off = off_hits["player_main"] + off_hits["player_dark"] + off_hits["enemy_main"] + off_hits["enemy_dark"]
    old_body_on = on_hits["player_main"] + on_hits["player_dark"] + on_hits["enemy_main"] + on_hits["enemy_dark"]

    print("")
    check(changed > 3000, "fighter band changed pixels = %d (> 3000)" % changed)
    check(bbox is not None and (bbox[2] - bbox[0]) > 400,
          "diff spans both fighters, width = %s (> 400)" % (bbox[2] - bbox[0] if bbox else None))
    check(on_hits["white"] > 1000, "new white outer layer = %d changed px (> 1000)" % on_hits["white"])
    check(on_hits["ink"] > 100, "new ink collar / hair = %d changed px (> 100)" % on_hits["ink"])
    check(on_hits["red"] > 30, "new red sash / knot = %d changed px (> 30)" % on_hits["red"])
    check(on_hits["gold"] > 30, "new gold clasp / trim = %d changed px (> 30)" % on_hits["gold"])
    check(off_hits["white"] < 500, "old silhouette has almost no white = %d (< 500)" % off_hits["white"])
    check(old_body_off > old_body_on + 500,
          "old amber/cyan body covered up: OFF %d vs ON %d (diff > 500)" % (old_body_off, old_body_on))
    check(on_crop.size == off_crop.size == (w, h), "crops aligned for per-pixel comparison")

    print("")
    print("EVIDENCE " + ("OK" if not failures else "FAILED (%d)" % len(failures)))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
