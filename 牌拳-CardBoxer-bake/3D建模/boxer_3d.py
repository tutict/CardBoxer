"""CardBoxer B route: a real 3D skeleton driving a skinned round-section body.

Why this is NOT the 2.5D model with a new hat
---------------------------------------------
2D5建模/boxer_2d5.py rebuilt flat extruded ribbons from joint coordinates on
every frame -- no skeleton, no skinning, no glTF export path. Here:

  * `boxer_rig.build()` gives a genuine 13-bone Blender Armature.
  * Each body segment is a cylinder with a ROUND cross-section (many distinct
    lateral y layers), modelled once in armature rest space.
  * Every vertex is 100% weighted to one bone via a vertex group + ARMATURE
    modifier. Nothing is rebuilt per frame.
  * Each frame, `boxer_rig.place()` poses the bones from baked2.json's 11 joint
    coordinates; the skin follows. The game's own stretch factor k is preserved
    as `pb.scale.y` (the baked table needs up to 2.5x on the jab forearm).

The "render frame vs hitbox frame" worry from the V3 record was overstated:
baked2.json IS the skeleton's per-frame readback (readback_error_px = 0.0) and
the game consumes that same table. A skin driven by the same table cannot drift.

Coordinate bridge (unchanged, verified in 2.5D V1/V2/V3):
    game px: origin at the feet, +x forward, -y UP
    blender: (x, depth_y, z) = (gx/100, lateral_layer, -gy/100)
    camera : ORTHO at y=-4 looking +y, so screen x == game x.

Two classes of object, stated plainly (see rig_stats.json):
    skinned : 13 cylinders, driven ONLY by the armature
    props   : head, face, gloves, shoes, belt, knot, ring blades -- rigid
              accessories positioned from the same joint table. They are not
              skinned because bone stretch would turn a round glove into an
              ellipse; the game's own fighter.gd draws accessories this way.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

import bpy
from mathutils import Vector

BAKE = r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake"
TABLE = os.path.join(BAKE, "baked2.json")
OUT = os.path.join(BAKE, "3D建模")
sys.path.insert(0, BAKE)
import boxer_rig  # noqa: E402  -- 13-bone rest definition + place()

JOINTS = [
    "hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
    "f_knee", "f_foot", "b_knee", "b_foot",
]

# V3 palette, including the corrected white coat: those three bands keep the
# lit face away from pure white after the linear -> sRGB view transform.
WHITE = (0.94, 0.94, 0.91)
INK = (0.055, 0.055, 0.085)
SLEEVE = (0.30, 0.33, 0.40)
SLEEVE_BACK = (0.17, 0.19, 0.25)
PANTS = (0.20, 0.21, 0.27)
PANTS_BACK = (0.15, 0.16, 0.21)
RED = (0.72, 0.15, 0.16)
GOLD = (0.86, 0.68, 0.30)
FACE = (0.90, 0.72, 0.58)
SILVER = (0.30, 0.33, 0.40)
PLAYER_GLOVE = (0.95, 0.48, 0.14)
ENEMY_GLOVE = (0.22, 0.70, 0.88)

# bone -> (head radius px, tail radius px, lateral depth m, material key,
#          RY_RATIO). All radii are HALF widths in the screen plane.
#
# RY_RATIO is the cross-section's lateral half-thickness relative to its
# screen-plane half-width. Round limbs use 1.0; the torso uses 0.45 because a
# human torso is a flattened ellipse, not a cylinder of diameter = shoulder
# width. v1 used 1.0 for the torso: a round chest of radius 0.30 m put its
# front surface at y=-0.30, IN FRONT OF the arms at y=-0.07, hiding both arms.
#
# DEPTH IS ZERO EVERYWHERE. v2 tried +0.19/-0.19 layers; numeric isolation
# showed forearm_b's lateral offset came back at [-19.1,-4.2] instead of the
# expected [+12,+26] -- the pose rotation flipped the channel for that one
# bone, so front and back arms split into unrelated floating blocks. Front/back
# is encoded by VALUE (sleeve vs sleeve_back), the standard 2D-fighter trick
# already proven in 2.5D V3. Round cross-sections still give real y thickness.
SEGMENTS = {
    "hips":        (20.0, 19.0, 0.0, "coat",       0.45),
    "spine":       (19.0, 21.0, 0.0, "coat",       0.45),
    "chest":       (21.0, 27.0, 0.0, "coat",       0.45),
    "neck":        (7.0,  7.5,  0.0, "skin",        1.00),
    "head":        (7.5,  9.0,  0.0, "skin",        1.00),
    "upperarm_f":  (8.5,  7.0,  0.0, "sleeve",      1.00),
    "forearm_f":   (7.0,  6.0,  0.0, "sleeve",      1.00),
    "upperarm_b":  (8.0,  6.8,  0.0, "sleeve_back", 1.00),
    "forearm_b":   (6.8,  5.8,  0.0, "sleeve_back", 1.00),
    "thigh_f":     (13.0, 10.5, 0.0, "pants",       1.00),
    "shin_f":      (10.5, 7.0,  0.0, "pants",       1.00),
    "thigh_b":     (13.0, 10.5, 0.0, "pants_back",  1.00),
    "shin_b":      (10.5, 7.0,  0.0, "pants_back",  1.00),
}

RES = 512
ORTHO = 2.6
TARGET = Vector((0.25, 0.0, 0.95))


# ---------------------------------------------------------------------------
# materials (Street Fighter IV cel shading, carried over from V3)
# ---------------------------------------------------------------------------

def _scale(rgb, k):
    return tuple(min(1.0, c * k) for c in rgb) + (1.0,)


def toon_material(name: str, rgb, bands=(0.42, 0.76, 0.94), cuts=(0.0, 0.38, 0.68)):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    s2rgb = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position = cuts[0]
    els[1].position = cuts[1]
    if len(els) < 3:
        els.new(cuts[2])
    else:
        els[2].position = cuts[2]
    for el, k in zip(els, bands):
        el.color = _scale(rgb, k)
    emit = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(diff.outputs["BSDF"], s2rgb.inputs["Shader"])
    nt.links.new(s2rgb.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    mat["toon_bands"] = list(bands)
    mat["toon_base"] = list(rgb)
    return mat


def set_toon_color(mat, rgb) -> None:
    ramp = next(n for n in mat.node_tree.nodes if n.type == "VALTORGB")
    for el, k in zip(ramp.color_ramp.elements, mat["toon_bands"]):
        el.color = _scale(rgb, k)
    mat.diffuse_color = (*rgb, 1.0)
    mat["toon_base"] = list(rgb)


def flat_material(name: str, rgb):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*rgb, 1.0)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------
# mesh primitives, all built around their own origin so props can be placed
# with a single object.location assignment
# ---------------------------------------------------------------------------

def make_mesh(name, verts, faces, mat):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def ellipsoid(name, mat, rx, ry, rz, seg=16, rings=10):
    verts, faces = [], []
    for j in range(1, rings):
        phi = math.pi * j / rings
        for i in range(seg):
            th = 2.0 * math.pi * i / seg
            verts.append((rx * math.sin(phi) * math.cos(th),
                          ry * math.sin(phi) * math.sin(th),
                          rz * math.cos(phi)))
    top = len(verts)
    verts.append((0.0, 0.0, rz))
    bot = len(verts)
    verts.append((0.0, 0.0, -rz))
    for j in range(rings - 2):
        for i in range(seg):
            a, b = j * seg + i, j * seg + (i + 1) % seg
            c, d = (j + 1) * seg + (i + 1) % seg, (j + 1) * seg + i
            faces.append((a, b, c, d))
    last = (rings - 2) * seg
    for i in range(seg):
        faces.append((top, i, (i + 1) % seg))
        faces.append((bot, last + (i + 1) % seg, last + i))
    return make_mesh(name, verts, faces, mat)


def box_mesh(name, mat, w, h, d):
    hw, hh, hd = w / 2.0, h / 2.0, d / 2.0
    verts = [
        (-hw, -hd, -hh), (hw, -hd, -hh), (hw, hd, -hh), (-hw, hd, -hh),
        (-hw, -hd,  hh), (hw, -hd,  hh), (hw, hd,  hh), (-hw, hd,  hh),
    ]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return make_mesh(name, verts, faces, mat)


def torus_mesh(name, mat, ring_r, tube_r, seg=20, sides=8):
    verts, faces = [], []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        cx, cz = ring_r * math.cos(a), ring_r * math.sin(a)
        for j in range(sides):
            b = 2.0 * math.pi * j / sides
            verts.append((cx + tube_r * math.cos(b) * math.cos(a),
                          tube_r * math.sin(b),
                          cz + tube_r * math.cos(b) * math.sin(a)))
    for i in range(seg):
        ni = (i + 1) % seg
        for j in range(sides):
            nj = (j + 1) % sides
            faces.append((i * sides + j, ni * sides + j,
                          ni * sides + nj, i * sides + nj))
    return make_mesh(name, verts, faces, mat)


def limb_cylinder(name, bone_name, arm, h: Vector, t: Vector,
                  r0: float, r1: float, depth: float, mat, ry_ratio=1.0, seg=12):
    """An ELLIPTIC-section tapered cylinder in armature rest space, rigidly skinned.

    Cross-section basis: n1 in the screen plane (perpendicular to the bone),
    n2 == world +Y (lateral). ry_ratio < 1 flattens the torso into a real
    human-like ellipse; limbs keep ry_ratio=1 (round). Either way the mesh has
    ~13 distinct lateral layers, while a 2.5D extruded ribbon has exactly 2.
    """
    axis = (t - h).normalized()
    n2 = Vector((0.0, 1.0, 0.0))
    n1 = axis.cross(n2).normalized()
    verts, faces = [], []
    for c, r in ((h, r0), (t, r1)):
        c = c + n2 * depth
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            v = c + r * math.cos(a) * n1 + r * ry_ratio * math.sin(a) * n2
            verts.append((v.x, v.y, v.z))
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, j, seg + j, seg + i))
    faces.append(tuple(reversed(range(seg))))
    faces.append(tuple(seg + i for i in range(seg)))
    ob = make_mesh(name, verts, faces, mat)
    vg = ob.vertex_groups.new(name=bone_name)
    vg.add(list(range(len(verts))), 1.0, "REPLACE")
    mod = ob.modifiers.new("Skin", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True
    return ob


# ---------------------------------------------------------------------------
# scene
# ---------------------------------------------------------------------------

def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"

    world = bpy.data.worlds.new("CardBoxer3DWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.30, 0.32, 0.38, 1.0)
    bg.inputs["Strength"].default_value = 0.16

    cam_data = bpy.data.cameras.new("CardBoxer3DCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ORTHO
    cam = bpy.data.objects.new("CardBoxer3DCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    set_camera(cam, 0.0)

    key_data = bpy.data.lights.new("Key3D", "SUN")
    key_data.energy = 2.4
    key = bpy.data.objects.new("Key3D", key_data)
    scene.collection.objects.link(key)
    key.rotation_euler = (math.radians(28), math.radians(-34), math.radians(24))

    fill_data = bpy.data.lights.new("Fill3D", "AREA")
    fill_data.energy = 90.0
    fill_data.size = 3.0
    fill = bpy.data.objects.new("Fill3D", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (2.0, -2.2, 2.6)
    fill.rotation_euler = (Vector((0.2, 0.0, 0.9)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    return scene, cam


def set_camera(cam, angle_deg: float):
    cam.location = (TARGET.x + 4.0 * math.tan(math.radians(angle_deg)), -4.0, TARGET.z)
    cam.rotation_euler = (TARGET - cam.location).to_track_quat("-Z", "Y").to_euler()


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------

def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def down(p, n):
    return (p[0], p[1] + n)


def offset(p, dx=0.0, dy=0.0):
    return (p[0] + dx, p[1] + dy)


def to_world(p, depth=0.0):
    return (p[0] / 100.0, depth, -p[1] / 100.0)


class Model:
    def __init__(self):
        # boxer_rig.build() also clears the scene, so it must come first.
        self.arm = boxer_rig.build()
        # The original rig only disables inherit_scale on the 8 IK-solved limb
        # bones. We scale EVERY bone explicitly from joint distances, so a
        # parent's scale must never leak into a child's basis.
        for bone in self.arm.data.bones:
            bone.inherit_scale = "NONE"
        for pb in self.arm.pose.bones:
            pb.rotation_mode = "XYZ"

        self.mats = {
            # Lifted a little from V3's (0.22,0.38,0.54): the brightest band
            # now lands near sRGB 201 against a 255 background -- still well
            # clear of the "white part melts into white bg" trap, but reads as
            # a white coat rather than a grey cone.
            "coat": toon_material("m_coat", WHITE, bands=(0.28, 0.46, 0.62)),
            "skin": toon_material("m_skin", FACE),
            "sleeve": toon_material("m_sleeve", SLEEVE),
            "sleeve_back": toon_material("m_sleeve_back", SLEEVE_BACK),
            "pants": toon_material("m_pants", PANTS),
            "pants_back": toon_material("m_pants_back", PANTS_BACK),
            "glove": toon_material("m_glove", PLAYER_GLOVE),
            "shoe": toon_material("m_shoe", INK),
            "belt": toon_material("m_belt", RED),
            "hair": toon_material("m_hair", INK),
            "bun": toon_material("m_bun", RED),
            # Ring blades were glowing white hoops under toon shading in v1.
            # They are waist ornaments, not light sources: unlit dark steel.
            "steel": flat_material("m_steel", (0.22, 0.25, 0.30)),
            "gold": flat_material("m_gold", GOLD),
            "ink": flat_material("m_ink", INK),
            "white_flat": flat_material("m_white_flat", (0.97, 0.97, 0.95)),
        }

        geom = boxer_rig._bone_geom()
        self.skinned = {}
        for bone_name, (r0, r1, depth, mat_key, ry_ratio) in SEGMENTS.items():
            hx, hz = geom[bone_name][0]
            tx, tz = geom[bone_name][1]
            h = Vector((hx, 0.0, hz))
            t = Vector((tx, 0.0, tz))
            self.skinned[bone_name] = limb_cylinder(
                "sk_" + bone_name, bone_name, self.arm, h, t,
                r0 / 100.0, r1 / 100.0, depth, self.mats[mat_key], ry_ratio,
            )

        self.props = {}
        self._build_props()
        bpy.context.view_layer.update()

    def _build_props(self):
        P, M = self.props, self.mats

        P["head_ball"] = ellipsoid("p_head_ball", M["skin"], 0.160, 0.135, 0.185)
        P["hair_cap"] = ellipsoid("p_hair_cap", M["hair"], 0.166, 0.140, 0.150)
        for side in ("l", "r"):
            P["bun_" + side] = ellipsoid("p_bun_" + side, M["bun"], 0.055, 0.050, 0.055, 12, 8)
            P["bun_ring_" + side] = torus_mesh("p_bun_ring_" + side, M["white_flat"], 0.052, 0.014, 16, 6)
            P["brow_" + side] = box_mesh("p_brow_" + side, M["ink"], 0.075, 0.020, 0.012)
            P["eye_" + side] = box_mesh("p_eye_" + side, M["ink"], 0.060, 0.026, 0.012)
        P["hair_clip"] = box_mesh("p_hair_clip", M["gold"], 0.055, 0.018, 0.014)
        P["nose"] = box_mesh("p_nose", M["ink"], 0.018, 0.032, 0.012)
        P["mouth"] = box_mesh("p_mouth", M["ink"], 0.062, 0.016, 0.012)

        for side in ("f", "b"):
            P["glove_" + side] = ellipsoid("p_glove_" + side, M["glove"], 0.135, 0.110, 0.130, 14, 10)
            P["glove_cuff_" + side] = torus_mesh("p_glove_cuff_" + side, M["ink"], 0.100, 0.022, 16, 6)
            P["shoe_" + side] = box_mesh("p_shoe_" + side, M["shoe"], 0.300, 0.140, 0.190)
            P["shoe_sole_" + side] = box_mesh("p_shoe_sole_" + side, M["gold"], 0.310, 0.035, 0.200)

        # Joint balls cover the flat end-caps where two cylinders meet. Without
        # them a 32 px limb with a 8.5 px radius reads as a detached rectangle
        # (v2 contact sheet, jab/sweep/throw). This is the standard fix for a
        # segmented 3D body, and it is not a cheat: the balls are placed from
        # the SAME joint table, so they cannot drift from the skeleton.
        P["shoulder_plate"] = ellipsoid("p_shoulder_plate", M["coat"], 0.290, 0.135, 0.130, 16, 10)
        for side, mat_key in (("f", "sleeve"), ("b", "sleeve_back")):
            P["j_shoulder_" + side] = ellipsoid("p_j_shoulder_" + side, M[mat_key], 0.105, 0.095, 0.105, 12, 8)
            P["j_elbow_" + side] = ellipsoid("p_j_elbow_" + side, M[mat_key], 0.075, 0.070, 0.075, 12, 8)
            P["j_wrist_" + side] = ellipsoid("p_j_wrist_" + side, M[mat_key], 0.068, 0.062, 0.068, 12, 8)
        for side, mat_key in (("f", "pants"), ("b", "pants_back")):
            P["j_hip_" + side] = ellipsoid("p_j_hip_" + side, M[mat_key], 0.120, 0.105, 0.120, 12, 8)
            P["j_knee_" + side] = ellipsoid("p_j_knee_" + side, M[mat_key], 0.100, 0.090, 0.100, 12, 8)

        # A dark centre opening + V collar break up the big coat cone and are
        # the two most legible cues of the V4-02 character design.
        P["lapel"] = box_mesh("p_lapel", M["ink"], 0.045, 0.560, 0.020)
        for side in ("l", "r"):
            P["collar_" + side] = box_mesh("p_collar_" + side, M["ink"], 0.038, 0.170, 0.020)

        P["belt"] = box_mesh("p_belt", M["belt"], 0.390, 0.095, 0.230)
        P["gold_clasp"] = box_mesh("p_gold_clasp", M["gold"], 0.090, 0.070, 0.035)
        P["knot"] = ellipsoid("p_knot", M["belt"], 0.045, 0.030, 0.045, 12, 8)
        P["tassel"] = box_mesh("p_tassel", M["belt"], 0.026, 0.090, 0.022)
        for side in ("l", "r"):
            P["ring_blade_" + side] = torus_mesh("p_ring_blade_" + side, M["steel"], 0.115, 0.020, 20, 6)

    # -- posing -------------------------------------------------------------

    def pose(self, j: dict) -> None:
        hip, sh, hd = j["hip"], j["shoulder"], j["head"]
        A = hip
        B = lerp(hip, sh, 0.26)
        C = lerp(hip, sh, 0.60)
        D = sh
        E = lerp(sh, hd, 0.58)
        F = hd
        chain = [
            ("hips", A, B), ("spine", B, C), ("chest", C, D), ("neck", D, E),
            ("upperarm_f", sh, j["f_elbow"]), ("forearm_f", j["f_elbow"], j["f_hand"]),
            ("upperarm_b", sh, j["b_elbow"]), ("forearm_b", j["b_elbow"], j["b_hand"]),
            ("thigh_f", offset(hip, 4.0, 0.0), j["f_knee"]),
            ("shin_f", j["f_knee"], j["f_foot"]),
            ("thigh_b", offset(hip, -4.0, 0.0), j["b_knee"]),
            ("shin_b", j["b_knee"], j["b_foot"]),
        ]
        for name, h, t in chain:
            boxer_rig.place(self.arm, name, h, t, math.dist(h, t))

        # The head bone keeps scale=1: a stretched head bone would squash the
        # skull and every facial prop bound to it into an ellipse.
        dx = (F[0] - E[0]) / 100.0
        dz = -(F[1] - E[1]) / 100.0
        u = Vector((dx, 0.0, dz)).normalized()
        mat = u.to_track_quat("Y", "Z").to_matrix().to_4x4()
        mat.translation = Vector((E[0] / 100.0, 0.0, -E[1] / 100.0))
        pb = self.arm.pose.bones["head"]
        pb.matrix = mat
        bpy.context.view_layer.update()
        pb.scale = (1.0, 1.0, 1.0)
        bpy.context.view_layer.update()

        self._place_props(j, hip, sh, hd)

    def _place_props(self, j, hip, sh, hd):
        P = self.props
        # Head centre sits below the skull joint; -y is toward the camera.
        hc = down(hd, 9.0)
        hx, hy, hz = to_world(hc)
        P["head_ball"].location = (hx, 0.0, hz)
        P["hair_cap"].location = (hx, 0.012, hz + 0.072)
        P["hair_cap"].scale = (1.0, 1.0, 0.82)

        face_y = -0.148
        for side, dx in (("l", -0.070), ("r", 0.070)):
            P["bun_" + side].location = (hx + dx * 1.9, 0.0, hz + 0.170)
            P["bun_ring_" + side].location = (hx + dx * 1.9, -0.030, hz + 0.170)
            P["brow_" + side].location = (hx + dx, face_y, hz + 0.052)
            P["brow_" + side].rotation_euler = (0.0, math.radians(-18 if side == "l" else 18), 0.0)
            P["eye_" + side].location = (hx + dx, face_y, hz + 0.012)
        P["hair_clip"].location = (hx + 0.115, face_y, hz + 0.115)
        P["nose"].location = (hx, face_y - 0.006, hz - 0.010)
        P["mouth"].location = (hx, face_y, hz - 0.078)

        sx, _sy, sz = to_world(sh)
        P["shoulder_plate"].location = (sx, 0.0, sz - 0.015)
        for side in ("f", "b"):
            for tag, key in (("shoulder", "shoulder"),
                             ("elbow", side + "_elbow"), ("wrist", side + "_hand")):
                jx, _jy, jz = to_world(j[key])
                P[f"j_{tag}_{side}"].location = (jx, 0.0, jz)
            kx, _ky, kz = to_world(j[side + "_knee"])
            P["j_knee_" + side].location = (kx, 0.0, kz)
            hx2, _hy2, hz2 = to_world(hip)
            P["j_hip_" + side].location = (hx2, 0.0, hz2)

        for side, key in (("f", "f_hand"), ("b", "b_hand")):
            gx, _gy, gz = to_world(j[key])
            P["glove_" + side].location = (gx, -0.020, gz)
            P["glove_cuff_" + side].location = (gx, -0.020, gz - 0.055)
        for side, key in (("f", "f_foot"), ("b", "b_foot")):
            fx, _fy, fz = to_world(j[key])
            P["shoe_" + side].location = (fx + 0.035, 0.0, fz - 0.020)
            P["shoe_sole_" + side].location = (fx + 0.035, 0.0, fz - 0.080)

        # Centre opening follows the torso lean, so it stays on the coat when
        # the body snaps forward instead of floating at a fixed x.
        a = offset(sh, 0.0, 14.0)
        b = offset(hip, 0.0, -12.0)
        mid = lerp(a, b, 0.5)
        dx = (b[0] - a[0]) / 100.0
        dz = -(b[1] - a[1]) / 100.0
        length = math.hypot(dx, dz)
        mx, _my, mz = to_world(mid)
        P["lapel"].location = (mx, -0.145, mz)
        P["lapel"].rotation_euler = (0.0, math.atan2(dx, dz), 0.0)
        P["lapel"].scale = (1.0, 1.0, length / 0.560)
        cx, _cy, cz = to_world(offset(sh, 0.0, 8.0))
        for side, sgn in (("l", -1), ("r", 1)):
            P["collar_" + side].location = (cx + sgn * 0.070, -0.145, cz)
            P["collar_" + side].rotation_euler = (0.0, math.radians(sgn * 32.0), 0.0)

        belt_c = offset(hip, 0.0, -4.0)
        bx, by, bz = to_world(belt_c)
        P["belt"].location = (bx, 0.0, bz)
        P["gold_clasp"].location = (bx, -0.125, bz)
        P["knot"].location = (bx + 0.010, -0.140, bz - 0.080)
        P["tassel"].location = (bx + 0.010, -0.140, bz - 0.140)
        for side, dx in (("l", -0.215), ("r", 0.215)):
            P["ring_blade_" + side].location = (bx + dx, 0.020, bz - 0.010)

    def set_palette(self, glove_rgb) -> None:
        set_toon_color(self.mats["glove"], glove_rgb)

    def rig_stats(self) -> dict:
        skinned = []
        for bone_name, ob in self.skinned.items():
            ys = [round(v.co.y, 5) for v in ob.data.vertices]
            mods = [(m.name, m.type) for m in ob.modifiers]
            groups = [g.name for g in ob.vertex_groups]
            weights = [sum(g.weight for g in v.groups) for v in ob.data.vertices]
            skinned.append({
                "object": ob.name,
                "bone": bone_name,
                "vertices": len(ob.data.vertices),
                "distinct_y_levels": len(set(ys)),
                "lateral_span_m": round(max(ys) - min(ys), 5),
                "vertex_groups": groups,
                "modifiers": mods,
                "weight_total_min": round(min(weights), 4),
                "weight_total_max": round(max(weights), 4),
            })
        toon = []
        s2rgb = 0
        for name, mat in self.mats.items():
            if not mat.use_nodes:
                continue
            nodes = list(mat.node_tree.nodes)
            n = sum(1 for x in nodes if x.type == "SHADERTORGB")
            s2rgb += n
            if n:
                ramps = [x for x in nodes if x.type == "VALTORGB"]
                toon.append({
                    "key": name,
                    "constant_ramp": bool(ramps) and ramps[0].color_ramp.interpolation == "CONSTANT",
                    "bands": list(mat.get("toon_bands", [])),
                })
        return {
            "bone_count": len(self.arm.data.bones),
            "bone_names": [b.name for b in self.arm.data.bones],
            "skinned_count": len(skinned),
            "skinned": skinned,
            "rigid_props": sorted(self.props.keys()),
            "rigid_prop_count": len(self.props),
            "toon_materials": toon,
            "shader_to_rgb_nodes": s2rgb,
        }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def joints_of(table: dict, card, frame: int) -> dict:
    if card is None:
        return {k: tuple(v) for k, v in table["stance"].items()}
    tracks = table["cards"] if card in table["cards"] else table["motions"]
    return {k: tuple(tracks[card]["track"][frame][k]) for k in JOINTS}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    with open(TABLE, "r", encoding="utf-8") as handle:
        table = json.load(handle)

    model = Model()
    scene, cam = setup_scene()

    shots = [
        ("stance", None, 0, "player", 0.0),
        ("jab_impact", "jab", 7, "player", 0.0),
        ("sweep_impact", "sweep", 13, "player", 0.0),
        ("throw_impact", "throw", 9, "player", 0.0),
        ("hit_heavy_mid", "hit_heavy", 15, "player", 0.0),
        ("stance_enemy", None, 0, "enemy", 0.0),
        # A 55-degree orbit is the visual proof of real depth: a flat ribbon
        # would collapse to a thin line here, a round-section body shows its
        # side surfaces. 35 deg was too subtle to be evidence.
        ("stance_angle55", None, 0, "player", 55.0),
        ("stance_repeat", None, 0, "player", 0.0),
    ]
    manifest = []
    for label, card, frame, palette, angle in shots:
        j = joints_of(table, card, frame)
        model.pose(j)
        model.set_palette(PLAYER_GLOVE if palette == "player" else ENEMY_GLOVE)
        set_camera(cam, angle)
        path = os.path.join(OUT, f"3d-{label}.png")
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

    stats = model.rig_stats()
    stats["table_sha256"] = hashlib.sha256(open(TABLE, "rb").read()).hexdigest()
    with open(os.path.join(OUT, "rig_stats.json"), "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)

    # Leave the .blend in a useful state: neutral stance, player palette.
    model.pose(joints_of(table, None, 0))
    model.set_palette(PLAYER_GLOVE)
    set_camera(cam, 0.0)
    blend_path = os.path.join(OUT, "boxer_3d.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"BLEND_OK {blend_path}", flush=True)

    with open(os.path.join(OUT, "render_manifest.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "table": TABLE,
            "table_sha256": stats["table_sha256"],
            "parts": sorted(model.skinned.keys()),
            "rigid_props": sorted(model.props.keys()),
            "joints": JOINTS,
            "camera": {"type": "ORTHO", "ortho_scale": ORTHO,
                       "res": [RES, RES], "target_xy_z": [0.25, 0.0, 0.95]},
            "shots": manifest,
        }, handle, ensure_ascii=False, indent=2)
    print(f"RIG_OK bones={stats['bone_count']} skinned={stats['skinned_count']} "
          f"props={stats['rigid_prop_count']} s2rgb={stats['shader_to_rgb_nodes']}", flush=True)
    print("MODEL_3D_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
