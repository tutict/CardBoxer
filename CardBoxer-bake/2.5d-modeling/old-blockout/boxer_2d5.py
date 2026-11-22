"""CardBoxer 2.5D character: volumetric parts driven by the game's own joint table.

Design decision (measured, not assumed)
--------------------------------------
The game already owns a 228-frame joint table (`data/card_motion.json`, baked by
`boxer_bake2.py`). Re-skinning a Blender armature would create a SECOND source of
truth for poses and force a "render frame <-> hitbox frame" sync guard. Instead
this script places a set of thick, layered meshes directly from each frame's 11
joint coordinates. One JSON, one index, no sync problem: a rendered frame IS the
frame the game uses for hit detection.

Coordinate bridge (matches boxer_rig.pt and fighter.gd::_build_pose):
    game px:  origin at the feet, +x forward, -y UP
    blender : (x, depth, z) = (gx / 100, layer_depth, -gy / 100)
so a pure-frontal orthographic camera has screen x == game x with zero
projection error. That matters: hit detection uses position.x + reach, and an
angled camera would compress x by cos(angle) and put the glove visually off the
hitbox. `angle_deg` exists for a look-dev comparison shot, not for shipped frames.

2.5D comes from geometry, not perspective: every part has real thickness along
Blender Y, parts sit on front/back layers, and a raking key light produces edges
and self-shadowing. No flat sprites were authored by hand.

Run:
  blender -b --factory-startup --python boxer_2d5.py -- --out <dir>
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys

import bpy
from mathutils import Vector

TABLE = r"D:\Projects\CardBoxer\CardBoxer-bake\baked2.json"
DEFAULT_OUT = r"D:\Projects\CardBoxer\CardBoxer-bake\2.5d-modeling"

# fighter_skin.gd constants, kept byte-for-byte comparable.
WHITE = (0.94, 0.94, 0.91)
INK = (0.055, 0.055, 0.085)          # deepened: strong world light washed 0.11 to mid grey
SLEEVE = (0.74, 0.76, 0.76)         # forearm shade separates the arm from the torso
RED = (0.72, 0.15, 0.16)
GOLD = (0.86, 0.68, 0.30)
FACE = (0.90, 0.72, 0.58)           # warmed so the head does not read as white torso
HOLE = (0.05, 0.045, 0.065)
SILVER = (0.85, 0.88, 0.92)
PLAYER_GLOVE = (0.95, 0.48, 0.14)   # warm amber
ENEMY_GLOVE = (0.22, 0.70, 0.88)    # cold cyan

# Exposure measured from run 1: world 0.75 + sun 2.4 + fill 320 over-lit every
# Principled surface. Dark materials came out mid-grey and the skin came out
# white, which made the head vanish against the white outer layer.

# Layer depths in metres. -Y is towards the camera.
D_BACK_LIMB = 0.055
D_TORSO = 0.0
D_FRONT_LIMB = -0.055
D_HEAD = -0.030
# The head sphere's front surface sits at D_HEAD - 0.18*0.62 = -0.142. Facial
# details must be IN FRONT of that or the sphere hides them (run 3: eyes in the
# scene, invisible in the render).
D_FACE = -0.155
D_GLOVE_F = -0.105
D_GLOVE_B = 0.020
D_DETAIL = -0.075

PARTS = [
    "white_outer", "ink_collar", "red_sash", "gold_clasp",
    "chinese_knot", "double_bun", "pom_pom", "hair_clip",
    "half_lidded_eye", "glove", "platform_shoe", "ring_blade",
]

JOINTS = [
    "hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
    "f_knee", "f_foot", "b_knee", "b_foot",
]


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def option(name: str, default: str) -> str:
    args = argv()
    return args[args.index(name) + 1] if name in args else default


def material(name: str, rgb, metallic: float = 0.0, roughness: float = 0.88):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def sphere(name: str, mat, segments: int = 20, rings: int = 12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    return ob


def box(name: str, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    return ob


def torus(name: str, mat, major: float, minor: float):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major, minor_radius=minor,
        major_segments=24, minor_segments=8,
    )
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    # Torus lies in XY by default; stand it up into the XZ screen plane.
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)
    return ob


def set_ball(ob, centre_px, radius_px, depth, squash=1.0):
    """Ellipsoid centred at a game-px point; radius_px is the screen-plane radius."""
    ob.location = (centre_px[0] / 100.0, depth, -centre_px[1] / 100.0)
    ob.rotation_euler = (0.0, 0.0, 0.0)
    r = radius_px / 100.0
    ob.scale = (r, r * 0.62, r * squash)


def set_segment(ob, a_px, b_px, width_px, depth, thickness=0.62):
    """Stretch an ellipsoid/box between two game-px joints (a capsule-like limb)."""
    ax, az = a_px[0] / 100.0, -a_px[1] / 100.0
    bx, bz = b_px[0] / 100.0, -b_px[1] / 100.0
    dx, dz = bx - ax, bz - az
    length = math.hypot(dx, dz)
    ob.location = ((ax + bx) / 2.0, depth, (az + bz) / 2.0)
    # Local +Z follows the limb; local +Y stays the depth axis, so thickness
    # never rotates into the screen plane.
    ob.rotation_euler = (0.0, math.atan2(dx, dz), 0.0)
    half_w = width_px / 200.0
    if ob.type == "MESH" and len(ob.data.polygons) == 6:  # cube -> full length
        ob.scale = (half_w * 2.0, half_w * 2.0 * thickness, length)
    else:  # uv sphere -> radius along local Z
        ob.scale = (half_w, half_w * thickness, length / 2.0)


def set_box(ob, centre_px, w_px, h_px, depth, thick_px=8.0, tilt_deg=0.0):
    ob.location = (centre_px[0] / 100.0, depth, -centre_px[1] / 100.0)
    ob.rotation_euler = (0.0, math.radians(tilt_deg), 0.0)
    ob.scale = (w_px / 100.0, thick_px / 100.0, h_px / 100.0)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def offset(p, dx=0.0, dy=0.0):
    return (p[0] + dx, p[1] + dy)


class Model:
    def __init__(self):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        for datablock in list(bpy.data.meshes):
            if datablock.users == 0:
                bpy.data.meshes.remove(datablock)

        m_white = material("white_outer", WHITE)
        m_ink = material("ink_collar", INK)
        m_sleeve = material("sleeve", SLEEVE)
        m_red = material("red_sash", RED)
        m_gold = material("gold_clasp", GOLD, metallic=0.55, roughness=0.42)
        m_face = material("face", FACE)
        m_hole = material("half_lidded_eye", HOLE, roughness=1.0)
        m_silver = material("ring_blade", SILVER, metallic=0.65, roughness=0.35)
        m_glove = material("glove", PLAYER_GLOVE, roughness=0.62)
        self.m_glove = m_glove
        self.o: dict[str, object] = {}

        # --- back layer (drawn behind the torso) ---
        for side in ("b", "f"):
            d = D_BACK_LIMB if side == "b" else D_FRONT_LIMB
            self.o[f"{side}_upperarm"] = sphere(f"{side}_upperarm", m_white)
            self.o[f"{side}_forearm"] = sphere(f"{side}_forearm", m_sleeve)
            self.o[f"{side}_thigh"] = sphere(f"{side}_thigh", m_ink)
            self.o[f"{side}_shin"] = sphere(f"{side}_shin", m_ink)
            self.o[f"{side}_shoe"] = box(f"platform_shoe_{side}", m_ink)
            self.o[f"{side}_shoe_sole"] = box(f"platform_shoe_sole_{side}", m_gold)
            self.o[f"{side}_glove"] = sphere(f"glove_{side}", m_glove, 24, 16)

        # --- torso and clothing ---
        self.o["white_outer"] = box("white_outer", m_white)
        self.o["shoulder_pad"] = sphere("shoulder_pad", m_white, 20, 12)
        self.o["ink_collar_l"] = box("ink_collar_l", m_ink)
        self.o["ink_collar_r"] = box("ink_collar_r", m_ink)
        self.o["red_sash"] = box("red_sash", m_red)
        self.o["gold_clasp_a"] = torus("gold_clasp_a", m_gold, 0.050, 0.013)
        self.o["gold_clasp_b"] = torus("gold_clasp_b", m_gold, 0.050, 0.013)
        self.o["chinese_knot"] = box("chinese_knot", m_red)
        self.o["knot_tassel_l"] = box("chinese_knot_tassel_l", m_red)
        self.o["knot_tassel_r"] = box("chinese_knot_tassel_r", m_red)
        self.o["ring_blade_l"] = torus("ring_blade_l", m_silver, 0.130, 0.012)
        self.o["ring_blade_r"] = torus("ring_blade_r", m_silver, 0.130, 0.012)

        # --- head / hair / face ---
        self.o["head"] = sphere("head", m_face, 24, 16)
        self.o["hair_cap"] = sphere("hair_cap", m_ink, 24, 12)
        self.o["double_bun_l"] = torus("double_bun_l", m_ink, 0.070, 0.022)
        self.o["double_bun_r"] = torus("double_bun_r", m_ink, 0.070, 0.022)
        self.o["pom_pom_l"] = sphere("pom_pom_l", m_red, 12, 8)
        self.o["pom_pom_r"] = sphere("pom_pom_r", m_red, 12, 8)
        self.o["hair_clip"] = box("hair_clip", m_gold)
        self.o["half_lidded_eye_l"] = box("half_lidded_eye_l", m_hole)
        self.o["half_lidded_eye_r"] = box("half_lidded_eye_r", m_hole)
        self.o["mouth"] = box("mouth", m_hole)

        self._assert_parts()

    def _assert_parts(self) -> None:
        """Every V4-02 part must exist as a REAL Blender object.

        Checking the dict keys instead would be a vacuous guard: keys are our own
        labels (b_shoe / f_glove) while the spec names real meshes
        (platform_shoe / glove). It reported a false failure on the first run and,
        worse, would have missed a genuinely mis-named mesh.
        """
        real = [ob.name for ob in bpy.data.objects]
        matched = {p: sorted(n for n in real if n.startswith(p)) for p in PARTS}
        missing = [p for p, hits in matched.items() if not hits]
        if missing:
            raise RuntimeError(f"missing spec parts: {missing}")
        print(f"PARTS_OK spec={len(PARTS)} meshes={len(real)}", flush=True)
        for part, hits in matched.items():
            print(f"  {part}: {','.join(hits)}", flush=True)

    def set_palette(self, rgb) -> None:
        self.m_glove.diffuse_color = (*rgb, 1.0)
        self.m_glove.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*rgb, 1.0)

    def pose(self, j: dict) -> None:
        """Place every part from one frame's 11 joint coordinates (game px)."""
        hip, sh, head = j["hip"], j["shoulder"], j["head"]

        # Limbs. Front limbs sit nearer the camera; widths taper towards the wrist.
        for side in ("b", "f"):
            d = D_BACK_LIMB if side == "b" else D_FRONT_LIMB
            el, hand = j[f"{side}_elbow"], j[f"{side}_hand"]
            knee, foot = j[f"{side}_knee"], j[f"{side}_foot"]
            set_segment(self.o[f"{side}_upperarm"], sh, el, 26.0, d)
            set_segment(self.o[f"{side}_forearm"], el, hand, 22.0, d)
            set_segment(self.o[f"{side}_thigh"], hip, knee, 30.0, d)
            set_segment(self.o[f"{side}_shin"], knee, foot, 24.0, d)
            set_box(self.o[f"{side}_shoe"], offset(foot, 6.0, -2.0), 30.0, 13.0, d, 12.0)
            set_box(self.o[f"{side}_shoe_sole"], offset(foot, 6.0, -7.0), 31.0, 4.0, d, 12.0)
            gd = D_GLOVE_B if side == "b" else D_GLOVE_F
            set_ball(self.o[f"{side}_glove"], hand, 14.0, gd)

        # Torso: a real rectangular coat panel, not an ellipsoid. With the old
        # white ball the white sleeves merged into it and the arms disappeared.
        set_segment(self.o["white_outer"], hip, sh, 48.0, D_TORSO, 0.34)
        set_ball(self.o["shoulder_pad"], sh, 15.0, D_TORSO - 0.005, squash=0.62)

        # Black crossed collar: two slanted bars forming a V.
        collar = lerp(hip, sh, 0.78)
        set_box(self.o["ink_collar_l"], offset(collar, -9.0, 2.0), 9.0, 30.0, D_DETAIL, 6.0, 28.0)
        set_box(self.o["ink_collar_r"], offset(collar, 9.0, 2.0), 9.0, 30.0, D_DETAIL, 6.0, -28.0)

        # Red sash + gold figure-eight clasp + hanging Chinese knot.
        waist = lerp(hip, sh, 0.28)
        set_box(self.o["red_sash"], waist, 52.0, 11.0, D_DETAIL, 7.0)
        for name, dx in (("gold_clasp_a", -5.0), ("gold_clasp_b", 5.0)):
            ob = self.o[name]
            ob.location = (offset(waist, dx, 0.0)[0] / 100.0, D_DETAIL - 0.012, -waist[1] / 100.0)
            ob.rotation_euler = (math.radians(90), 0.0, 0.0)
            ob.scale = (1.0, 1.0, 1.0)
        knot = offset(waist, 0.0, 16.0)
        set_box(self.o["chinese_knot"], knot, 13.0, 13.0, D_DETAIL - 0.014, 6.0, 45.0)
        set_box(self.o["knot_tassel_l"], offset(knot, -4.0, 12.0), 3.0, 16.0, D_DETAIL - 0.014, 5.0, 8.0)
        set_box(self.o["knot_tassel_r"], offset(knot, 4.0, 12.0), 3.0, 16.0, D_DETAIL - 0.014, 5.0, -8.0)

        # Two ring blades at the hips, one black one white in the concept art;
        # here two silver arcs, kept as side ornaments so they never occlude a glove.
        for name, dx in (("ring_blade_l", -30.0), ("ring_blade_r", 30.0)):
            ob = self.o[name]
            p = offset(waist, dx, 2.0)
            ob.location = (p[0] / 100.0, D_BACK_LIMB, -p[1] / 100.0)
            ob.rotation_euler = (math.radians(90), 0.0, math.radians(18))
            ob.scale = (1.0, 1.0, 1.0)

        # Head, twin buns, pom-poms, hair clip, half-lidded eyes.
        face_c = offset(head, 0.0, 12.0)
        set_ball(self.o["head"], face_c, 18.0, D_HEAD, squash=1.06)
        # A dark hair cap over the upper skull is what makes the head readable
        # against a white coat; without it the face washed into the torso.
        set_ball(self.o["hair_cap"], offset(head, 0.0, -5.0), 18.0, D_HEAD - 0.022, squash=0.52)
        for name, dx in (("double_bun_l", -13.0), ("double_bun_r", 13.0)):
            ob = self.o[name]
            p = offset(head, dx, -7.0)
            ob.location = (p[0] / 100.0, D_HEAD, -p[1] / 100.0)
            ob.rotation_euler = (math.radians(90), 0.0, 0.0)
            ob.scale = (1.0, 1.0, 1.0)
        for name, dx in (("pom_pom_l", -21.0), ("pom_pom_r", 21.0)):
            set_ball(self.o[name], offset(head, dx, -6.0), 6.0, D_HEAD - 0.01)
        set_box(self.o["hair_clip"], offset(head, 8.0, -1.0), 12.0, 3.0, D_FACE, 4.0, -18.0)
        for name, dx in (("half_lidded_eye_l", -7.0), ("half_lidded_eye_r", 7.0)):
            set_box(self.o[name], offset(face_c, dx, 1.0), 8.0, 4.0, D_FACE, 3.0)
        set_box(self.o["mouth"], offset(face_c, 0.0, 9.0), 7.0, 2.0, D_FACE, 3.0)

        bpy.context.view_layer.update()


def setup_scene(angle_deg: float):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"

    world = bpy.data.worlds.new("CardBoxerWorld") if not scene.world else scene.world
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.30, 0.32, 0.38, 1.0)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.30

    cam_data = bpy.data.cameras.new("CardBoxerCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.6
    cam = bpy.data.objects.new("CardBoxerCam", cam_data)
    scene.collection.objects.link(cam)
    target = Vector((0.25, 0.0, 0.95))
    cam.location = (
        target.x + 4.0 * math.tan(math.radians(angle_deg)),
        -4.0,
        target.z,
    )
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    key_data = bpy.data.lights.new("Key", "SUN")
    key_data.energy = 1.6
    key = bpy.data.objects.new("Key", key_data)
    scene.collection.objects.link(key)
    key.rotation_euler = (math.radians(28), math.radians(-34), math.radians(24))

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 140.0
    fill_data.size = 3.0
    fill = bpy.data.objects.new("Fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (2.0, -2.2, 2.6)
    fill.rotation_euler = (Vector((0.2, 0.0, 0.9)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    return scene


def joints_of(table: dict, card: str | None, frame: int) -> dict:
    if card is None:
        return {k: tuple(v) for k, v in table["stance"].items()}
    tracks = table["cards"] if card in table["cards"] else table["motions"]
    return {k: tuple(tracks[card]["track"][frame][k]) for k in JOINTS}


def main() -> int:
    out = option("--out", DEFAULT_OUT)
    os.makedirs(out, exist_ok=True)
    with open(TABLE, "r", encoding="utf-8") as handle:
        table = json.load(handle)

    model = Model()
    scene = setup_scene(0.0)
    manifest: list[dict] = []

    shots = [
        ("stance", None, 0, "player", 0.0),
        ("jab_impact", "jab", 7, "player", 0.0),
        ("sweep_impact", "sweep", 13, "player", 0.0),
        ("throw_impact", "throw", 9, "player", 0.0),
        ("hit_heavy_mid", "hit_heavy", 15, "player", 0.0),
        ("stance_enemy", None, 0, "enemy", 0.0),
        ("stance_angle12", None, 0, "player", 12.0),
        ("stance_repeat", None, 0, "player", 0.0),  # determinism control
    ]

    for label, card, frame, palette, angle in shots:
        j = joints_of(table, card, frame)
        model.pose(j)
        model.set_palette(PLAYER_GLOVE if palette == "player" else ENEMY_GLOVE)
        cam = scene.camera
        target = Vector((0.25, 0.0, 0.95))
        cam.location = (target.x + 4.0 * math.tan(math.radians(angle)), -4.0, target.z)
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        path = os.path.join(out, f"2d5-{label}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        payload = json.dumps({k: list(v) for k, v in sorted(j.items())}, sort_keys=True)
        manifest.append({
            "file": os.path.basename(path),
            "card": card, "frame": frame, "palette": palette, "angle_deg": angle,
            "joints_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "size_bytes": os.path.getsize(path),
        })
        print(f"SHOT_OK {label} card={card} frame={frame} palette={palette} angle={angle}", flush=True)

    # Save the model at the rest pose so it can actually be opened and inspected.
    model.pose(joints_of(table, None, 0))
    model.set_palette(PLAYER_GLOVE)
    cam = scene.camera
    cam.location = (0.25, -4.0, 0.95)
    cam.rotation_euler = (Vector((0.25, 0.0, 0.95)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    blend_path = os.path.join(out, "boxer_2d5.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"BLEND_OK {blend_path}", flush=True)

    with open(os.path.join(out, "render_manifest.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "table": TABLE,
            "table_sha256": hashlib.sha256(open(TABLE, "rb").read()).hexdigest(),
            "parts": PARTS, "joints": JOINTS,
            "camera": {"type": "ORTHO", "ortho_scale": 2.6, "res": [512, 512],
                       "target_xy_z": [0.25, 0.0, 0.95]},
            "shots": manifest,
        }, handle, ensure_ascii=False, indent=2)
    print("MODEL_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
