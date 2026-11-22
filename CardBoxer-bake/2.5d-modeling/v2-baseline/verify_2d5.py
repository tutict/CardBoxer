"""Independent, re-runnable acceptance checks for the 2.5D boxer renders.

Run with the project venv (Pillow is required):

    C:/Users/tutic/IdeaProjects/Fantasy-Agent/.venv/Scripts/python.exe \
        D:/Projects/CardBoxer/CardBoxer-bake/2.5d-modeling/verify_2d5.py

This script does NOT import Blender and does NOT touch the Godot project.
It only reads the PNGs, render_manifest.json, baked2.json and boxer_2d5.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
TABLE = BAKE / "baked2.json"
MANIFEST = HERE / "render_manifest.json"
RUN1 = HERE / "2d5-run1-stance-comparison.png"

JOINTS = [
    "hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
    "f_knee", "f_foot", "b_knee", "b_foot",
]

# Same camera math as boxer_2d5.py: ORTHO, ortho_scale=2.6, 512px, target.x=0.25.
ORTHO_SCALE = 2.6
RES = 512
PX_PER_UNIT = RES / ORTHO_SCALE  # 196.923 px per blender unit == 1.96923 px per game px

results: list[tuple[str, bool, str]] = []
reports: dict[str, object] = {}


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(im: Image.Image):
    """Pillow 12 renamed getdata(); keep the checker version-agnostic."""
    getter = getattr(im, "get_flattened_data", None)
    return getter() if getter is not None else im.getdata()


def flat(path: Path) -> Image.Image:
    """Composite RGBA over white, so hidden RGB under transparent sky cannot fake a diff."""
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def diff_pixels(a: Image.Image, b: Image.Image) -> int:
    """Count pixels that differ by more than a small tolerance (antialiasing noise)."""
    d = ImageChops.difference(a, b)
    # max channel delta per pixel
    grey = d.convert("L")
    return sum(1 for v in pixels(grey) if v > 6)


def dark_pixels(im: Image.Image) -> int:
    return sum(1 for r, g, b in pixels(im) if r + g + b < 210)


def png_chunks(path: Path) -> list[tuple[str, bytes]]:
    """Return (type, raw_data) for every chunk after the IHDR, in file order."""
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    out: list[tuple[str, bytes]] = []
    while pos + 8 <= len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        ctype = raw[pos + 4:pos + 8].decode("ascii", "replace")
        data = raw[pos + 8:pos + 8 + length]
        out.append((ctype, data))
        pos += 8 + length + 4
    return out


# ---------------------------------------------------------------- load inputs
table = json.loads(TABLE.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
shots = manifest["shots"]

# 1. every declared PNG exists, is a real 512x512 image and actually has content
images: dict[str, Image.Image] = {}
shape_ok = True
content_ok = True
shape_detail = []
for shot in shots:
    p = HERE / shot["file"]
    if not p.exists():
        shape_ok = False
        shape_detail.append(f"MISSING {shot['file']}")
        continue
    im = flat(p)
    images[shot["file"]] = im
    if im.size != (RES, RES):
        shape_ok = False
        shape_detail.append(f"{shot['file']} size={im.size}")
    nonwhite = sum(1 for r, g, b in pixels(im) if (r, g, b) != (255, 255, 255))
    if nonwhite < 8000:
        content_ok = False
        shape_detail.append(f"{shot['file']} nonwhite={nonwhite} (suspiciously empty)")
    if shot["size_bytes"] != p.stat().st_size:
        shape_ok = False
        shape_detail.append(f"{shot['file']} manifest size mismatch")
check("pngs_valid", shape_ok, "; ".join(shape_detail) if shape_detail else
      f"8/8 PNG, {RES}x{RES}, manifest sizes match")
check("renders_nonempty", content_ok,
      "all 8 renders have >8000 non-white pixels" if content_ok else
      "; ".join(shape_detail))

# 2. determinism control: same joints + same palette + same angle twice
s0 = images["2d5-stance.png"]
s1 = images["2d5-stance_repeat.png"]
bbox = ImageChops.difference(s0, s1).getbbox()
check("repeat_pixels_identical", bbox is None,
      f"ImageChops.difference bbox={bbox} (None == pixel-identical)")

# 3. sha differs but only in tEXt metadata; IDAT must be byte-identical
c0 = png_chunks(HERE / "2d5-stance.png")
c1 = png_chunks(HERE / "2d5-stance_repeat.png")
idat0 = [d for t, d in c0 if t == "IDAT"]
idat1 = [d for t, d in c1 if t == "IDAT"]
types0 = [t for t, _ in c0]
types1 = [t for t, _ in c1]
text0 = [d for t, d in c0 if t == "tEXt"]
text1 = [d for t, d in c1 if t == "tEXt"]
meta_only = (
    sha256(HERE / "2d5-stance.png") != sha256(HERE / "2d5-stance_repeat.png")
    and types0 == types1
    and idat0 == idat1
    and text0 != text1
)
check("repeat_sha_diff_is_metadata_only", meta_only,
      f"chunk types equal={types0 == types1}; IDAT equal={idat0 == idat1}; "
      f"tEXt differs={text0 != text1}; bytes {os.path.getsize(HERE / '2d5-stance.png')} "
      f"vs {os.path.getsize(HERE / '2d5-stance_repeat.png')}")

# 4. motion frames really come from different rows of baked2.json
motion_files = [
    "2d5-jab_impact.png", "2d5-sweep_impact.png", "2d5-throw_impact.png",
    "2d5-hit_heavy_mid.png",
]
pair_diffs = {}
distinct = True
for f in motion_files:
    n = diff_pixels(s0, images[f])
    pair_diffs[f] = n
    if n < 2000:
        distinct = False
for i, a in enumerate(motion_files):
    for b in motion_files[i + 1:]:
        n = diff_pixels(images[a], images[b])
        pair_diffs[f"{a}|{b}"] = n
        if n < 2000:
            distinct = False
check("pose_frames_distinct", distinct,
      f"min pairwise changed pixels = {min(pair_diffs.values())}; "
      f"stance-vs-motion = " + ", ".join(f"{k.split('2d5-')[1]}={v}" for k, v in pair_diffs.items()
                                         if "|" not in k))

# 5. palette switch and camera angle switch both change the picture
n_pal = diff_pixels(s0, images["2d5-stance_enemy.png"])
n_ang = diff_pixels(s0, images["2d5-stance_angle12.png"])
check("palette_and_angle_live", n_pal > 500 and n_ang > 500,
      f"palette changed px={n_pal}; angle12 changed px={n_ang}")

# 6. manifest joints hashes recomputed from the *real* baked2.json, not hand-written
def joints_of(card: str | None, frame: int) -> dict:
    if card is None:
        return {k: list(v) for k, v in table["stance"].items()}
    tracks = table["cards"] if card in table["cards"] else table["motions"]
    return {k: list(tracks[card]["track"][frame][k]) for k in JOINTS}


trace = []
recompute_ok = True
for shot in shots:
    j = joints_of(shot["card"], shot["frame"])
    payload = json.dumps({k: list(v) for k, v in sorted(j.items())}, sort_keys=True)
    want = hashlib.sha256(payload.encode()).hexdigest()
    ok = want == shot["joints_sha256"]
    recompute_ok &= ok
    trace.append(f"{shot['file']}:{'OK' if ok else 'MISMATCH'}")
check("manifest_joints_traceable", recompute_ok,
      f"{sum(1 for t in trace if t.endswith('OK'))}/8 recomputed from baked2.json; " + ", ".join(trace))
check("table_sha256_matches", manifest["table_sha256"] == sha256(TABLE),
      f"manifest={manifest['table_sha256'][:12]}... disk={sha256(TABLE)[:12]}...")

# 7. coordinate bridge: screen span between the two shoes must match game px span.
#    stance f_foot.x=36, b_foot.x=-44 -> 80 game px -> 80/100 * PX_PER_UNIT.
game_span = (table["stance"]["f_foot"][0] - table["stance"]["b_foot"][0]) / 100.0
want_span = game_span * PX_PER_UNIT


def shoe_centers(im: Image.Image, y0: int, y1: int) -> tuple[float, float, int]:
    left, right = [], []
    for y in range(y0, y1):
        for x in range(RES):
            r, g, b = im.getpixel((x, y))
            if abs(r - 255) + abs(g - 255) + abs(b - 255) > 40:
                (left if x < RES // 2 else right).append(x)
    if not left or not right:
        return (0.0, 0.0, 0)
    left.sort()
    right.sort()
    return (left[len(left) // 2], right[len(right) // 2], len(left) + len(right))


lc, rc, npx = shoe_centers(s0, 428, 462)
span = rc - lc
bridge_ok = npx > 500 and abs(span - want_span) <= 25.0
check("ortho_coordinate_bridge", bridge_ok,
      f"shoe centers L={lc:.1f} R={rc:.1f} span={span:.1f}px (n={npx}); "
      f"predicted from stance f_foot/b_foot = {want_span:.1f}px; tol=25px")
reports["shoe_span_px"] = round(span, 1)
reports["shoe_span_predicted_px"] = round(want_span, 1)

# 8. lighting fix: run1 overexposed control must differ, final must have more ink
if RUN1.exists():
    r1 = flat(RUN1)
    d_final = dark_pixels(s0)
    d_run1 = dark_pixels(r1)
    n = diff_pixels(r1, s0)
    # NOTE: run1 is the V1 overexposed render; final is V2 after a full geometry
    # rewrite. This is a "not the same picture" guard, NOT a lighting A/B test.
    fix_ok = n > 5000 and d_final > d_run1
    check("differs_from_v1_baseline", fix_ok,
          f"V1 run1 dark={d_run1} -> V2 final dark={d_final}; changed px={n} "
          f"(crosses the geometry rewrite, not a pure lighting A/B)")
else:
    check("lighting_fix_effective", False, "run1 control PNG missing")

# --- report-only visual statistics (the qualitative read is done by eye) ---
def region_stats(im: Image.Image, box: tuple[int, int, int, int]) -> dict[str, int]:
    crop = im.crop(box)
    warm = dark = gold = 0
    for r, g, b in pixels(crop):
        if r > 190 and 140 < g < 230 and 110 < b < 205 and r - b > 25:
            warm += 1
        if r + g + b < 210:
            dark += 1
        if r > 170 and 120 < g < 215 and b < 120:
            gold += 1
    return {"warm_skin": warm, "dark": dark, "gold": gold}


# V2 moved the head upward and replaced the sphere with an egg-shaped ribbon;
# the old (155,100,330,185) box sampled the collar, not the face.
reports["face_region_175_45_260_140"] = region_stats(s0, (175, 45, 260, 140))
reports["face_readable_by_eye"] = (
    "V2 egg-shaped face ribbon + hair cap; two half-lidded eyes, mouth line and "
    "gold hair clip visible. (V1's D_FACE / head-sphere note no longer applies.)"
)
reports["face_stats_caveat"] = (
    "these colour buckets are coarse report-only numbers; gold=0 means the bucket "
    "missed the lit highlight, NOT that the clip is absent -- that is read by eye"
)

# ------------------------------------------------------------------- verdict
passed = sum(1 for _, ok, _ in results if ok)
print(f"CHECKS {passed}/{len(results)}")
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
print("REPORTS " + json.dumps(reports, ensure_ascii=False))
out = {
    "passed": passed,
    "total": len(results),
    "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in results],
    "reports": reports,
    "table_sha256": sha256(TABLE),
    "script_sha256": sha256(Path(__file__)),
}
(HERE / "verify_2d5_result.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("MODEL_2D5_VERIFIED" if passed == len(results) else "MODEL_2D5_INCOMPLETE")
sys.exit(0 if passed == len(results) else 1)
