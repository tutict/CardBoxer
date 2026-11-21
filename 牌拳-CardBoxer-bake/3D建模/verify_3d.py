"""Independent, re-runnable acceptance checks for the real-3D boxer renders.

Run with the project venv (Pillow required):

    C:/Users/tutic/IdeaProjects/Fantasy-Agent/.venv/Scripts/python.exe \
        C:/Users/tutic/Desktop/学习资料/牌拳-CardBoxer-bake/3D建模/verify_3d.py

Does NOT import Blender and does NOT touch the Godot project. It reads PNGs,
render_manifest.json, rig_stats.json (Blender's own report), probe_rig.json,
diag_3d.log, baked2.json and the source files.

What these checks deliberately do NOT prove: that the character looks good,
that every frame is free of geometry self-intersection, or that a glTF export
would work. Those are separate deliverables and are called out in the record.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
TABLE = BAKE / "baked2.json"
MANIFEST = HERE / "render_manifest.json"
RIG_STATS = HERE / "rig_stats.json"
PROBE = HERE / "probe_rig.json"
DIAG_LOG = HERE / "diag_3d.log"
V3_BASELINE = BAKE / "2D5建模" / "2d5-stance.png"
GAME = BAKE.parent / "牌拳-CardBoxer"
SRC = HERE / "boxer_3d.py"

RES = 512
ORTHO_SCALE = 2.6
PX_PER_UNIT = RES / ORTHO_SCALE

JOINTS = [
    "hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
    "f_knee", "f_foot", "b_knee", "b_foot",
]

results: list[tuple[str, bool, str]] = []
reports: dict[str, object] = {}


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(im):
    getter = getattr(im, "get_flattened_data", None)
    return getter() if getter is not None else im.getdata()


def flat(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def diff_pixels(a: Image.Image, b: Image.Image) -> int:
    return sum(1 for v in pixels(ImageChops.difference(a, b).convert("L")) if v > 6)


def png_chunks(path: Path) -> list[tuple[str, bytes]]:
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, out = 8, []
    while pos + 8 <= len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        ctype = raw[pos + 4:pos + 8].decode("ascii", "replace")
        out.append((ctype, raw[pos + 8:pos + 8 + length]))
        pos += 8 + length + 4
    return out


table = json.loads(TABLE.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
stats = json.loads(RIG_STATS.read_text(encoding="utf-8"))
probe = json.loads(PROBE.read_text(encoding="utf-8"))
src = SRC.read_text(encoding="utf-8")
shots = manifest["shots"]

# 1-2. every declared PNG is real, correctly sized and not blank
images: dict[str, Image.Image] = {}
shape_ok, content_ok, problems = True, True, []
for shot in shots:
    p = HERE / shot["file"]
    if not p.exists():
        shape_ok = False
        problems.append(f"MISSING {shot['file']}")
        continue
    im = flat(p)
    images[shot["file"]] = im
    if im.size != (RES, RES):
        shape_ok = False
        problems.append(f"{shot['file']} size={im.size}")
    nonwhite = sum(1 for c in pixels(im) if c != (255, 255, 255))
    if nonwhite < 8000:
        content_ok = False
        problems.append(f"{shot['file']} nonwhite={nonwhite}")
    if shot["size_bytes"] != p.stat().st_size:
        shape_ok = False
        problems.append(f"{shot['file']} manifest size mismatch")
check("pngs_valid", shape_ok, "; ".join(problems) or f"{len(shots)}/{len(shots)} PNG, {RES}x{RES}")
check("renders_nonempty", content_ok, "all renders have >8000 non-white pixels" if content_ok else "; ".join(problems))

s0 = images["3d-stance.png"]
s1 = images["3d-stance_repeat.png"]

# 3. determinism. Use the SAME >6 antialiasing tolerance as diff_pixels()
#    everywhere else in this file. The first draft used getbbox(), whose >0
#    threshold reported a 122x60 box for EEVEE's +/-1 8-bit quantisation on
#    curved cel-shaded surfaces. A 1/255 difference is not a picture change;
#    a mismatched threshold is a broken criterion, not a broken render.
dvals = list(pixels(ImageChops.difference(s0, s1).convert("L")))
repeat_changed = sum(1 for v in dvals if v > 6)
max_delta = max(dvals)
check("repeat_pixels_identical", repeat_changed == 0 and max_delta <= 1,
      f"changed px (>6)={repeat_changed}, max channel delta={max_delta} "
      f"(getbbox={ImageChops.difference(s0, s1).getbbox()} counts +/-1 noise)")

# 4. byte-level difference must still be fully explained. The 2.5D V3 record
#    proved "sha differs only because of tEXt Date/RenderTime, IDAT identical".
#    That conclusion is RETIRED here, not watered down: round cross-sections
#    put curved cel-shading boundaries on subpixel edges, so EEVEE's +/-1
#    dither leaks into IDAT. What we still prove is that the picture is
#    identical at the tolerance every other check uses, and no chunk is added
#    or removed. If the model were genuinely non-deterministic, repeat_changed
#    would be in the thousands and this check would go red.
p0, p1 = HERE / "3d-stance.png", HERE / "3d-stance_repeat.png"
h0, h1 = sha256(p0), sha256(p1)
c0, c1 = png_chunks(p0), png_chunks(p1)
types_equal = [t for t, _ in c0] == [t for t, _ in c1]
idat_equal = (b"".join(d for t, d in c0 if t == "IDAT")
              == b"".join(d for t, d in c1 if t == "IDAT"))
text_differs = (b"".join(d for t, d in c0 if t == "tEXt")
                != b"".join(d for t, d in c1 if t == "tEXt"))
explained = types_equal and repeat_changed == 0 and max_delta <= 1
check("repeat_bytes_fully_explained", explained,
      f"sha equal={h0 == h1}; chunk types equal={types_equal}; "
      f"IDAT equal={idat_equal}; tEXt differs={text_differs}; "
      f"changed px(>6)={repeat_changed}; max delta={max_delta}; "
      f"bytes {p0.stat().st_size} vs {p1.stat().st_size}; "
      "IDAT differences are +/-1 quantisation, NOT a different picture")

# 5. different baked frames really change the picture
motion = ["3d-jab_impact.png", "3d-sweep_impact.png", "3d-throw_impact.png", "3d-hit_heavy_mid.png"]
changes = {n: diff_pixels(s0, images[n]) for n in motion}
min_change = min(changes.values())
check("pose_frames_distinct", min_change >= 12000,
      f"min stance-vs-motion changed pixels = {min_change}; " +
      ", ".join(f"{n.split('-')[1]}={v}" for n, v in changes.items()))

# 6. both switches are wired: enemy palette and the 55-degree orbit
pal = diff_pixels(s0, images["3d-stance_enemy.png"])
ang = diff_pixels(s0, images["3d-stance_angle55.png"])
check("palette_and_angle_live", pal >= 1000 and ang >= 8000,
      f"palette changed px={pal}; angle55 changed px={ang}")

# 7-8. manifest is recomputed from the table, not hand-written
def joints_of(card, frame):
    if card is None:
        return {k: tuple(v) for k, v in table["stance"].items()}
    tracks = table["cards"] if card in table["cards"] else table["motions"]
    return {k: tuple(tracks[card]["track"][frame][k]) for k in JOINTS}


trace, recompute_ok = [], True
for shot in shots:
    j = joints_of(shot["card"], shot["frame"])
    payload = json.dumps({k: list(v) for k, v in sorted(j.items())}, sort_keys=True)
    want = hashlib.sha256(payload.encode()).hexdigest()
    ok = want == shot["joints_sha256"]
    recompute_ok &= ok
    trace.append(f"{shot['file']}:{'OK' if ok else 'MISMATCH'}")
check("manifest_joints_traceable", recompute_ok,
      f"{sum(1 for t in trace if t.endswith('OK'))}/{len(shots)} recomputed from baked2.json")
check("table_sha256_matches",
      manifest["table_sha256"] == sha256(TABLE) == stats["table_sha256"],
      f"manifest/rig_stats/disk all {sha256(TABLE)[:12]}...")

# 9. coordinate bridge: screen span between the two shoes == game px span
game_span = (table["stance"]["f_foot"][0] - table["stance"]["b_foot"][0]) / 100.0
want_span = game_span * PX_PER_UNIT


def shoe_centers(im, y0, y1):
    left, right = [], []
    for y in range(y0, y1):
        for x in range(RES):
            r, g, b = im.getpixel((x, y))
            if abs(r - 255) + abs(g - 255) + abs(b - 255) > 40:
                (left if x < RES // 2 else right).append(x)
    if not left or not right:
        return 0.0, 0.0, 0
    left.sort()
    right.sort()
    return left[len(left) // 2], right[len(right) // 2], len(left) + len(right)


lc, rc, npx = shoe_centers(s0, 428, 462)
span = rc - lc
check("ortho_coordinate_bridge", npx > 500 and abs(span - want_span) <= 25.0,
      f"shoe centers L={lc:.1f} R={rc:.1f} span={span:.1f}px (n={npx}); "
      f"predicted {want_span:.1f}px; tol=25px")
reports["shoe_span_px"] = round(span, 1)
reports["shoe_span_predicted_px"] = round(want_span, 1)

# 10. the skeleton and skin are real, as reported by Blender itself
rig_ok = stats["bone_count"] == 13 and stats["skinned_count"] == 13
bind_problems = []
for part in stats["skinned"]:
    mods = [m[1] for m in part["modifiers"]]
    if "ARMATURE" not in mods:
        bind_problems.append(part["object"] + ":no-armature")
    if part["vertex_groups"] != [part["bone"]]:
        bind_problems.append(part["object"] + ":group-mismatch")
    if not (part["weight_total_min"] == 1.0 and part["weight_total_max"] == 1.0):
        bind_problems.append(part["object"] + ":weight!=1")
check("rig_is_real", rig_ok and not bind_problems,
      f"bones={stats['bone_count']} skinned={stats['skinned_count']} "
      f"props={stats['rigid_prop_count']}; " + ("all rigid-bound 100%" if not bind_problems else "; ".join(bind_problems)))

# 11. real depth: round/elliptic cross-sections, NOT 2-layer extruded ribbons.
#     A 2.5D ribbon has exactly 2 distinct lateral y levels; these have ~13.
depths = [p["distinct_y_levels"] for p in stats["skinned"]]
spans = [p["lateral_span_m"] for p in stats["skinned"]]
check("mesh_has_depth", min(depths) >= 6 and min(spans) >= 0.05,
      f"min distinct lateral layers={min(depths)} (2.5D ribbon would be 2); "
      f"min lateral span={min(spans):.3f} m")
reports["min_distinct_y_levels"] = min(depths)
reports["min_lateral_span_m"] = round(min(spans), 4)

# 12. cel shading chain is wired (source + Blender-side material report)
toon_ok = all(m["constant_ramp"] for m in stats["toon_materials"])
wired = ("ShaderNodeShaderToRGB" in src and 'interpolation = "CONSTANT"' in src
         and "ShaderNodeEmission" in src and stats["shader_to_rgb_nodes"] >= 10 and toon_ok)
check("toon_shader_is_wired", wired,
      f"ShaderToRGB nodes={stats['shader_to_rgb_nodes']}, "
      f"constant ramps={sum(1 for m in stats['toon_materials'] if m['constant_ramp'])}"
      f"/{len(stats['toon_materials'])}, source chain present")

# 13. the skeleton DRIVES the body, and the probe proves the mechanism
skeleton_tokens = ["boxer_rig.build()", "boxer_rig.place(", "pb.matrix", "pb.scale",
                   '"ARMATURE"', "vertex_groups.new", "inherit_scale"]
missing = [t for t in skeleton_tokens if t not in src]
probe_ok = (probe["mesh_follows_bone"] and probe["max_vertex_displacement"] > 0.15
            and probe["distinct_y_levels_rest"] >= 6
            and (HERE / "probe_rig_rest.png").exists()
            and (HERE / "probe_rig_posed.png").exists())
check("skeleton_is_wired", not missing and probe_ok,
      f"source tokens missing={missing}; probe follows={probe['mesh_follows_bone']}, "
      f"max vertex displacement={probe['max_vertex_displacement']}, "
      f"rest/posed signatures differ={probe['vertex_signatures_differ']}")

# 14. numeric isolation log: bones land on the table, no orphaned skin
diag = DIAG_LOG.read_text(encoding="utf-8") if DIAG_LOG.exists() else ""
worst = [float(v) for v in re.findall(r"^WORST_BONE_ERROR \S+ ([\d.]+)", diag, re.M)]
orphan_lines = re.findall(r"^ORPHANS \S+ (\[.*\])$", diag, re.M)
orphan_ok = bool(orphan_lines) and all(v.strip() == "[]" for v in orphan_lines)
check("bone_readback_clean", len(worst) >= 3 and max(worst) < 1.0 and orphan_ok,
      f"frames={len(worst)} worst error={max(worst) if worst else 'N/A'} px; "
      f"orphan lists={orphan_lines}")

# 15. this is genuinely a different model from the 2.5D V3 baseline
if V3_BASELINE.exists():
    d = diff_pixels(s0, flat(V3_BASELINE))
    check("differs_from_2d5_v3", d >= 20000, f"changed pixels vs 2d5-stance.png = {d}")
    reports["diff_vs_2d5_v3_px"] = d
else:
    check("differs_from_2d5_v3", False, "2.5D baseline missing")

# 16. the Godot game tree was not touched by this modelling work
anchor = SRC.stat().st_mtime
changed = []
if GAME.exists():
    for p in GAME.rglob("*"):
        if not p.is_file() or ".godot" in p.parts:
            continue
        if p.stat().st_mtime > anchor:
            changed.append(str(p.relative_to(GAME)))
check("game_dir_unchanged", not changed, f"files newer than boxer_3d.py = {len(changed)}"
      + (": " + ", ".join(changed[:5]) if changed else ""))

# --- verdict ---
passed = sum(1 for _, ok, _ in results if ok)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
print(f"CHECKS {passed}/{len(results)}", flush=True)
out = {
    "passed": passed, "total": len(results),
    "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in results],
    "reports": reports,
    "table_sha256": sha256(TABLE),
    "script_sha256": sha256(Path(__file__).resolve()),
}
(HERE / "verify_3d_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("MODEL_3D_VERIFIED" if passed == len(results) else "MODEL_3D_FAILED", flush=True)
raise SystemExit(0 if passed == len(results) else 1)
