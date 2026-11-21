"""CardBoxer 2.5D character: CONTINUOUS silhouette driven by the game's joint table.

Why V2 exists
-------------
V1 built 12 isolated primitives (spheres / boxes / tori) placed at joint coords.
It did not read as a human being. Two measured root causes:

  1. The white coat merged into the white compositing background (film_transparent
     + white backdrop), so only the black collar and red sash were visible. That
     looked like a floating head above a floating belt -- it was NOT a missing
     torso, it was a same-colour torso.
  2. Both legs started from the SAME hip point and were equal-width stretched
     ellipsoids, so they overlapped into one black blob at the pelvis. Same for
     arms. A bag of parts is not a body.

V2 replaces part stacking with continuous, extruded outline ribbons: a tapered
torso, a neck, tapered limb chains, an egg-shaped face. Every limb starts from
its own offset shoulder/hip point. Every white part gets a slightly larger dark
outline ribbon behind it, so the silhouette survives a white background.

Coordinate bridge (UNCHANGED, matches boxer_rig.pt and fighter.gd::_build_pose):
    game px:  origin at the feet, +x forward, -y UP
    blender : (x, depth, z) = (gx / 100, layer_depth, -gy / 100)
ORTHO ortho_scale=2.6 @512px => screen x == game x, 1.96923 px per game px.
The 228-frame joint table remains the single source of truth; no armature, no
second pose representation, no render-frame/hitbox-frame sync problem.

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

TABLE = r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\baked2.json"
DEFAULT_OUT = r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\2D5建模"

# fighter_skin.gd constants, kept byte-for-byte comparable.
WHITE = (0.94, 0.94, 0.91)
INK = (0.055, 0.055, 0.085)
SLEEVE = (0.46, 0.49, 0.54)         # clearly darker than the white coat / white bg
PANTS = (0.20, 0.21, 0.27)          # lifted off INK so two legs read separately
RED = (0.72, 0.15, 0.16)
GOLD = (0.86, 0.68, 0.30)
FACE = (0.90, 0.72, 0.58)
HOLE = (0.05, 0.045, 0.065)
SILVER = (0.85, 0.88, 0.92)
PLAYER_GLOVE = (0.95, 0.48, 0.14)
ENEMY_GLOVE = (0.22, 0.70, 0.88)

# Layer depths in metres. -Y is towards the camera (smaller == nearer).
D_BACK_LIMB = 0.052
D_TORSO = 0.0
D_FRONT_LIMB = -0.052
D_HEAD = -0.030
D_HAIR = -0.048
D_FACE_DETAIL = -0.098
D_DETAIL = -0.072
D_GLOVE_F = -0.100
D_GLOVE_B = 0.018
OUTLINE_BACK = 0.018               # how far behind its part the dark outline sits
OUTLINE_PX = 3.0                   # extra half-width, in game px

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
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)
    return ob


def ribbon(name: str, mat):
    """An empty mesh whose screen-plane outline is rewritten on every pose."""
    mesh = bpy.data.meshes.new(name + "_mesh")
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def set_ribbon(ob, pts, half_widths_px, depth, thick=0.055):
    """Build a closed, extruded tapered band from a centre line in game px.

    pts: [(game_x, game_y), ...] along the limb/torso.
    half_widths_px: half-width at each centre point, in game px.
    The band is a real volume: front cap, back cap and side walls, so the raking
    key light produces edges. No spheres are stacked to fake a limb any more.
    """
    n = len(pts)
    assert n == len(half_widths_px) and n >= 2
    P = [(p[0] / 100.0, -p[1] / 100.0) for p in pts]
    W = [w / 100.0 for w in half_widths_px]
    def unit(v):
        length = math.hypot(v[0], v[1]) or 1e-6
        return (v[0] / length, v[1] / length)

    # A plain centre-difference normal self-intersects at sharp joints: the
    # sweep frame's 90-degree knee folded the outline into a Z / bow-tie. Use a
    # proper miter (average of the two segment normals) with a clipped miter
    # length, which is exactly what 2D stroke renderers do.
    left, right = [], []
    for i in range(n):
        if i == 0 or i == n - 1 or n == 2:
            a, b = (P[0], P[1]) if i == 0 else (P[i - 1], P[i])
            t = unit((b[0] - a[0], b[1] - a[1]))
            nvec = (-t[1], t[0])
            miter = 1.0
        else:
            t0 = unit((P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]))
            t1 = unit((P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1]))
            n0, n1 = (-t0[1], t0[0]), (-t1[1], t1[0])
            summed = unit((n0[0] + n1[0], n0[1] + n1[1]))
            nvec = summed
            dot = abs(summed[0] * n0[0] + summed[1] * n0[1])
            miter = 1.0 / max(dot, 0.55)
        w = W[i] * miter
        left.append((P[i][0] + nvec[0] * w, P[i][1] + nvec[1] * w))
        right.append((P[i][0] - nvec[0] * w, P[i][1] - nvec[1] * w))

    yf, yb = depth - thick / 2.0, depth + thick / 2.0
    # index layout: L_i = i, R_i = n+i, back L_i = 2n+i, back R_i = 3n+i
    verts = (
        [(x, yf, z) for x, z in left] + [(x, yf, z) for x, z in right]
        + [(x, yb, z) for x, z in left] + [(x, yb, z) for x, z in right]
    )
    faces = []
    for i in range(n - 1):
        faces.append((i, i + 1, n + i + 1, n + i))                    # front
        faces.append((2 * n + i, 3 * n + i, 3 * n + i + 1, 2 * n + i + 1))  # back
        faces.append((i, i + 1, 2 * n + i + 1, 2 * n + i))            # left wall
        faces.append((n + i, 3 * n + i, 3 * n + i + 1, n + i + 1))    # right wall
    faces.append((0, n, 3 * n, 2 * n))                                 # start cap
    faces.append((n - 1, 3 * n - 1, 4 * n - 1, 2 * n - 1))             # end cap

    mesh = ob.data
    mesh.clear_geometry()          # keeps the material slot assigned in ribbon()
    mesh.from_pydata(verts, [], faces)
    mesh.update()


def set_ball(ob, centre_px, radius_px, depth, squash=1.0):
    ob.location = (centre_px[0] / 100.0, depth, -centre_px[1] / 100.0)
    ob.rotation_euler = (0.0, 0.0, 0.0)
    r = radius_px / 100.0
    ob.scale = (r, r * 0.62, r * squash)


def set_box(ob, centre_px, w_px, h_px, depth, thick_px=8.0, tilt_deg=0.0):
    ob.location = (centre_px[0] / 100.0, depth, -centre_px[1] / 100.0)
    ob.rotation_euler = (0.0, math.radians(tilt_deg), 0.0)
    ob.scale = (w_px / 100.0, thick_px / 100.0, h_px / 100.0)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def offset(p, dx=0.0, dy=0.0):
    return (p[0] + dx, p[1] + dy)


def up(p, n):
    return (p[0], p[1] - n)


def down(p, n):
    return (p[0], p[1] + n)


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
        m_pants = material("pants", PANTS)
        m_red = material("red_sash", RED)
        m_gold = material("gold_clasp", GOLD, metallic=0.55, roughness=0.42)
        m_face = material("face", FACE)
        m_hole = material("half_lidded_eye", HOLE, roughness=1.0)
        m_silver = material("ring_blade", SILVER, metallic=0.65, roughness=0.35)
        m_glove = material("glove", PLAYER_GLOVE, roughness=0.62)
        self.m_glove = m_glove
        self.o: dict[str, object] = {}

        def outlined(key):
            """A dark outline ribbon behind a part, so white parts survive a white bg."""
            return ribbon(key, m_ink)

        # --- continuous limb chains: ONE band per limb, not two stacked spheres ---
        for side in ("b", "f"):
            # Two straight segments + an elbow ball. A SINGLE band running through
            # the sharp V-fold of the guard stance fills its inner wedge into a
            # triangular "wing" (cape), so the arm must be split at the elbow.
            # Sleeve is grey, not white: white on the white background reads as a
            # stick with only its outline visible.
            self.o[f"{side}_upperarm_outline"] = outlined(f"{side}_upperarm_outline")
            self.o[f"{side}_upperarm"] = ribbon(f"{side}_upperarm", m_sleeve)
            self.o[f"{side}_forearm_outline"] = outlined(f"{side}_forearm_outline")
            self.o[f"{side}_forearm"] = ribbon(f"{side}_forearm", m_sleeve)
            self.o[f"{side}_cuff"] = ribbon(f"{side}_cuff", m_ink)
            self.o[f"{side}_leg_outline"] = outlined(f"{side}_leg_outline")
            self.o[f"{side}_leg"] = ribbon(f"{side}_leg", m_pants)
            self.o[f"platform_shoe_{side}"] = box(f"platform_shoe_{side}", m_ink)
            self.o[f"platform_shoe_sole_{side}"] = box(f"platform_shoe_sole_{side}", m_gold)
            self.o[f"glove_{side}"] = sphere(f"glove_{side}", m_glove, 24, 16)

        # --- torso: tapered coat + dark waistcoat, both with outlines ---
        self.o["white_outer_outline"] = outlined("white_outer_outline")
        self.o["white_outer"] = ribbon("white_outer", m_white)
        self.o["ink_collar"] = ribbon("ink_collar", m_ink)
        self.o["ink_collar_l"] = box("ink_collar_l", m_ink)
        self.o["ink_collar_r"] = box("ink_collar_r", m_ink)
        self.o["neck"] = ribbon("neck", m_face)
        self.o["neck_outline"] = outlined("neck_outline")
        self.o["red_sash"] = box("red_sash", m_red)
        self.o["gold_clasp_a"] = torus("gold_clasp_a", m_gold, 0.038, 0.010)
        self.o["gold_clasp_b"] = torus("gold_clasp_b", m_gold, 0.038, 0.010)
        self.o["chinese_knot"] = box("chinese_knot", m_red)
        self.o["chinese_knot_loop"] = torus("chinese_knot_loop", m_red, 0.028, 0.009)
        self.o["chinese_knot_tassel_l"] = box("chinese_knot_tassel_l", m_red)
        self.o["chinese_knot_tassel_r"] = box("chinese_knot_tassel_r", m_red)
        self.o["ring_blade_l"] = torus("ring_blade_l", m_silver, 0.075, 0.010)
        self.o["ring_blade_r"] = torus("ring_blade_r", m_silver, 0.075, 0.010)

        # --- head: an egg-shaped FACE outline, not a ball with a square jaw ---
        self.o["head_outline"] = outlined("head_outline")
        self.o["head"] = ribbon("head", m_face)
        self.o["hair_cap"] = ribbon("hair_cap", m_ink)
        self.o["double_bun_l"] = torus("double_bun_l", m_ink, 0.058, 0.019)
        self.o["double_bun_r"] = torus("double_bun_r", m_ink, 0.058, 0.019)
        self.o["pom_pom_l"] = sphere("pom_pom_l", m_red, 12, 8)
        self.o["pom_pom_r"] = sphere("pom_pom_r", m_red, 12, 8)
        self.o["hair_clip"] = box("hair_clip", m_gold)
        self.o["half_lidded_eye_l"] = box("half_lidded_eye_l", m_hole)
        self.o["half_lidded_eye_r"] = box("half_lidded_eye_r", m_hole)
        self.o["mouth"] = box("mouth", m_hole)

        self._assert_parts()

    def _assert_parts(self) -> None:
        """Every V4-02 part must exist as a REAL Blender object (not a dict key)."""
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

    @staticmethod
    def _outline(ob, pts, widths, depth, pad=None):
        extra = OUTLINE_PX if pad is None else pad
        set_ribbon(ob, pts, [w + extra for w in widths],
                   depth + OUTLINE_BACK, 0.055)

    def pose(self, j: dict) -> None:
        """Place the whole continuous body from one frame's 11 joint coordinates."""
        hip, sh, head = j["hip"], j["shoulder"], j["head"]

        # Limbs start from THEIR OWN shoulder/hip points. V1 started both legs at
        # the single hip joint, which fused them into one black blob at the pelvis.
        for side in ("b", "f"):
            sign = -1.0 if side == "b" else 1.0
            d = D_BACK_LIMB if side == "b" else D_FRONT_LIMB
            el, hand = j[f"{side}_elbow"], j[f"{side}_hand"]
            knee, foot = j[f"{side}_knee"], j[f"{side}_foot"]

            shoulder_pt = offset(sh, sign * 20.0, -2.0)
            # Narrow bands with a thin outline: wide arm bands + thick outlines
            # merged across the V-shaped guard into a single triangular "cape".
            # WIDTH IS THE WHOLE PROBLEM: shoulder->elbow is only ~20 game px
            # (~39 screen px). A half-width of 11 game px makes a 43 px WIDE
            # band that is wider than it is long, so two of them merge into a
            # triangular cape. Real proportions need ~1/3 of head width.
            up_pts, up_w = [shoulder_pt, el], [5.5, 5.0]
            self._outline(self.o[f"{side}_upperarm_outline"], up_pts, up_w, d, pad=1.2)
            set_ribbon(self.o[f"{side}_upperarm"], up_pts, up_w, d)
            fo_pts, fo_w = [el, hand], [5.0, 4.2]
            self._outline(self.o[f"{side}_forearm_outline"], fo_pts, fo_w, d, pad=1.2)
            set_ribbon(self.o[f"{side}_forearm"], fo_pts, fo_w, d)
            # a cuff a little above the wrist breaks the sleeve/glove join
            cuff_a, cuff_b = lerp(el, hand, 0.74), lerp(el, hand, 0.94)
            set_ribbon(self.o[f"{side}_cuff"], [cuff_a, cuff_b], [5.2, 4.5], d - 0.006, 0.058)

            # End the trouser INSIDE the shoe, otherwise a white gap appears
            # between cuff and boot at every frame.
            leg_pts = [offset(hip, sign * 12.0, 0.0), knee, offset(foot, 2.0, -4.0)]
            leg_w = [12.0, 10.0, 7.0]
            self._outline(self.o[f"{side}_leg_outline"], leg_pts, leg_w, d)
            set_ribbon(self.o[f"{side}_leg"], leg_pts, leg_w, d)

            set_box(self.o[f"platform_shoe_{side}"], offset(foot, 6.0, -2.0), 22.0, 11.0, d, 12.0)
            set_box(self.o[f"platform_shoe_sole_{side}"], offset(foot, 6.0, -7.0), 23.0, 3.5, d, 12.0)
            gd = D_GLOVE_B if side == "b" else D_GLOVE_F
            set_ball(self.o[f"glove_{side}"], hand, 9.0, gd, squash=0.86)

        # Torso: a single tapered coat band, waist narrow / shoulders wide.
        torso_pts = [hip, lerp(hip, sh, 0.5), sh]
        torso_w = [17.0, 21.0, 26.0]
        self._outline(self.o["white_outer_outline"], torso_pts, torso_w, D_TORSO)
        set_ribbon(self.o["white_outer"], torso_pts, torso_w, D_TORSO)
        # A dark waistcoat down the centre gives the white torso a readable edge.
        vest_pts = [lerp(hip, sh, 0.10), lerp(hip, sh, 0.55), lerp(sh, hip, 0.12)]
        set_ribbon(self.o["ink_collar"], vest_pts, [7.5, 10.0, 11.0], D_DETAIL, 0.060)
        collar = lerp(hip, sh, 0.80)
        set_box(self.o["ink_collar_l"], offset(collar, -8.0, 0.0), 7.0, 22.0, D_DETAIL - 0.012, 6.0, 26.0)
        set_box(self.o["ink_collar_r"], offset(collar, 8.0, 0.0), 7.0, 22.0, D_DETAIL - 0.012, 6.0, -26.0)

        # A real neck connects head to shoulders.
        hcx = head[0]
        chin = (hcx, head[1] + 14.0)
        neck_pts = [sh, chin]
        neck_w = [7.0, 7.0]
        self._outline(self.o["neck_outline"], neck_pts, neck_w, D_TORSO + 0.010)
        set_ribbon(self.o["neck"], neck_pts, neck_w, D_TORSO + 0.010)

        # Red sash, figure-eight clasp, a real knot (diamond + two short tassels,
        # NOT the giant upward arrow V1 produced).
        waist = lerp(hip, sh, 0.28)
        set_box(self.o["red_sash"], waist, 42.0, 9.0, D_DETAIL - 0.018, 7.0)
        for name, dx in (("gold_clasp_a", -4.5), ("gold_clasp_b", 4.5)):
            ob = self.o[name]
            p = offset(waist, dx, 0.0)
            ob.location = (p[0] / 100.0, D_DETAIL - 0.030, -p[1] / 100.0)
            ob.rotation_euler = (math.radians(90), 0.0, 0.0)
            ob.scale = (1.0, 1.0, 1.0)
        # A flat knot plus two hanging tassels. V1 rotated a square 45 degrees
        # with two upward legs, which read as a big red ARROW, not a knot.
        knot = down(waist, 11.0)
        set_box(self.o["chinese_knot"], knot, 9.0, 6.0, D_DETAIL - 0.032, 6.0, 0.0)
        loop = self.o["chinese_knot_loop"]
        loop.location = (knot[0] / 100.0, D_DETAIL - 0.032, -up(knot, 6.0)[1] / 100.0)
        loop.rotation_euler = (math.radians(90), 0.0, 0.0)
        loop.scale = (1.0, 1.0, 1.0)
        set_box(self.o["chinese_knot_tassel_l"], offset(down(knot, 9.0), -2.5, 0.0),
                2.4, 11.0, D_DETAIL - 0.032, 5.0, 4.0)
        set_box(self.o["chinese_knot_tassel_r"], offset(down(knot, 9.0), 2.5, 0.0),
                2.4, 11.0, D_DETAIL - 0.032, 5.0, -4.0)

        # Ring blades: smaller, at the hip, partly overlapping the body so they
        # are attached ornaments rather than floating hoops.
        for name, dx in (("ring_blade_l", -19.0), ("ring_blade_r", 19.0)):
            ob = self.o[name]
            p = offset(waist, dx, 1.0)
            ob.location = (p[0] / 100.0, D_BACK_LIMB, -p[1] / 100.0)
            ob.rotation_euler = (math.radians(90), 0.0, math.radians(18))
            ob.scale = (1.0, 1.0, 1.0)

        # Head: vertical egg outline, round skull / wide cheek / narrow chin.
        hc = up(head, 6.0)
        face_pts = [
            up(hc, 20.0), up(hc, 15.0), up(hc, 6.0),
            down(hc, 4.0), down(hc, 13.0), down(hc, 19.0),
        ]
        face_w = [8.0, 14.5, 18.5, 17.5, 12.0, 6.5]
        self._outline(self.o["head_outline"], face_pts, face_w, D_HEAD)
        set_ribbon(self.o["head"], face_pts, face_w, D_HEAD)
        # Hair covers only the upper skull; it must stop above the eyes.
        hair_pts = [up(hc, 21.0), up(hc, 17.0), up(hc, 12.0), up(hc, 9.0)]
        set_ribbon(self.o["hair_cap"], hair_pts, [9.0, 15.0, 18.0, 18.0], D_HAIR, 0.058)
        for name, dx in (("double_bun_l", -14.0), ("double_bun_r", 14.0)):
            ob = self.o[name]
            p = offset(up(hc, 20.0), dx, 0.0)
            ob.location = (p[0] / 100.0, D_HAIR, -p[1] / 100.0)
            ob.rotation_euler = (math.radians(90), 0.0, 0.0)
            ob.scale = (1.0, 1.0, 1.0)
        for name, dx in (("pom_pom_l", -21.0), ("pom_pom_r", 21.0)):
            set_ball(self.o[name], offset(up(hc, 19.0), dx, 0.0), 4.8, D_HAIR - 0.010)
        set_box(self.o["hair_clip"], offset(up(hc, 7.0), 8.0, 0.0), 10.0, 2.6,
                D_FACE_DETAIL, 3.0, -18.0)
        eye_c = up(hc, 1.0)
        for name, dx in (("half_lidded_eye_l", -7.0), ("half_lidded_eye_r", 7.0)):
            set_box(self.o[name], offset(eye_c, dx, 0.0), 7.5, 3.2, D_FACE_DETAIL, 3.0)
        set_box(self.o["mouth"], down(hc, 9.0), 6.0, 1.8, D_FACE_DETAIL, 3.0)

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
