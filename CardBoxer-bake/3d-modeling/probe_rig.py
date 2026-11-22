"""Minimal rigid-skin feasibility probe (Blender 5.2.3 headless).

Question this answers, before any modelling work is spent:

    boxer_rig.place() poses bones by assigning `pb.matrix` directly and then
    sets `pb.scale.y` to an explicit length ratio (the game's own baked table
    needs limb stretch: k up to 2.5x). If a mesh bound 100% to that bone with
    a vertex group + ARMATURE modifier does NOT follow that transform, the
    whole "real skeleton + skinned 3D mesh" route is dead and we must know it
    now, not after building 20 parts.

Evidence produced (both numeric and visual, neither alone):
  * evaluated-mesh world centroid and lateral (y) extent in rest vs posed
  * two rendered PNGs, so a human can see the cylinder actually moved
  * probe_rig.json consumed by verify_3d.py
"""
from __future__ import annotations

import hashlib
import json
import math
import os

import bpy
from mathutils import Matrix, Vector

OUT = r"D:\Projects\CardBoxer\CardBoxer-bake\3d-modeling"
os.makedirs(OUT, exist_ok=True)

SEGMENTS = 12
R0, R1, LEN = 0.09, 0.06, 0.50


def sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def setup_scene():
    clear()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 256
    scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"

    world = bpy.data.worlds.new("ProbeWorld")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.30, 0.32, 0.38, 1.0)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.16

    cam_data = bpy.data.cameras.new("ProbeCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 1.6
    cam = bpy.data.objects.new("ProbeCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -4.0, 0.25)
    cam.rotation_euler = (Vector((0.0, 0.0, 0.25)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    light_data = bpy.data.lights.new("Key", "SUN")
    light_data.energy = 2.4
    light = bpy.data.objects.new("Key", light_data)
    scene.collection.objects.link(light)
    light.rotation_euler = (math.radians(28), math.radians(-34), math.radians(24))
    return scene


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def flat_material(name, rgb):
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


def build_rig():
    arm_data = bpy.data.armatures.new("ProbeRig")
    arm = bpy.data.objects.new("ProbeRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    bone = arm_data.edit_bones.new("seg")
    bone.head = (0.0, 0.0, 0.0)
    bone.tail = (0.0, 0.0, LEN)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.pose.bones["seg"].rotation_mode = "XYZ"
    arm.pose.bones["seg"].bone.inherit_scale = "NONE"
    return arm


def build_mesh(mat):
    """A real cylinder in rest space: round cross-section => real y thickness."""
    verts = []
    for z, r in ((0.0, R0), (LEN, R1)):
        for i in range(SEGMENTS):
            a = 2.0 * math.pi * i / SEGMENTS
            verts.append((r * math.cos(a), r * math.sin(a), z))
    faces = []
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        faces.append((i, j, SEGMENTS + j, SEGMENTS + i))
    faces.append(tuple(reversed(range(SEGMENTS))))
    faces.append(tuple(SEGMENTS + i for i in range(SEGMENTS)))
    mesh = bpy.data.meshes.new("ProbeSeg_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new("ProbeSeg", mesh)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def bind(ob, arm):
    vg = ob.vertex_groups.new(name="seg")
    vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
    mod = ob.modifiers.new("Skin", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True
    return vg, mod


def evaluated_stats(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    mesh = ev.to_mesh()
    pts = [ev.matrix_world @ v.co for v in mesh.vertices]
    centroid = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
    ys = [p.y for p in pts]
    verts = [tuple(round(c, 4) for c in p) for p in pts]
    signature = hashlib.sha256(
        "|".join(f"{x},{y},{z}" for x, y, z in sorted(verts)).encode()
    ).hexdigest()
    stats = {
        "centroid": [round(v, 4) for v in centroid],
        "y_range": [round(min(ys), 4), round(max(ys), 4)],
        "vertex_count": len(pts),
        "vertex_signature": signature,
        # A round cross-section has many distinct lateral layers; a flat
        # 2.5D ribbon has exactly two (front cap + back cap). This is the
        # hard numeric difference between "real 3D" and "extruded plane".
        "distinct_y_levels": len({round(y, 4) for y in ys}),
        "verts": verts,  # popped before the JSON dump
    }
    ev.to_mesh_clear()
    return stats


def main() -> int:
    scene = setup_scene()
    arm = build_rig()
    ob = build_mesh(flat_material("ProbeMat", (0.24, 0.38, 0.54)))
    vg, mod = bind(ob, arm)
    bpy.context.view_layer.update()

    rest = evaluated_stats(ob)
    p_rest = os.path.join(OUT, "probe_rig_rest.png")
    scene.render.filepath = p_rest
    bpy.ops.render.render(write_still=True)

    # Exactly the transform pattern boxer_rig.place() uses on every bone,
    # every frame: `u.to_track_quat("Y","Z")` so the bone's LOCAL Y (its length)
    # points along the game-space segment, then an explicit Y length scale.
    # First draft used Matrix.Rotation(...,'Y'), whose Y column is still world
    # +Y: the bone pointed straight at the camera and the render showed only a
    # circular end-cap. A probe must reproduce the real call shape, not merely
    # "a rotation", or it proves the wrong transform.
    pb = arm.pose.bones["seg"]
    u = Vector((math.sin(math.radians(52.0)), 0.0, math.cos(math.radians(52.0)))).normalized()
    mat = u.to_track_quat("Y", "Z").to_matrix().to_4x4()
    mat.translation = Vector((-0.25, 0.0, 0.05))
    pb.matrix = mat
    bpy.context.view_layer.update()
    pb.scale = (1.0, 1.4, 1.0)
    bpy.context.view_layer.update()

    posed = evaluated_stats(ob)
    p_posed = os.path.join(OUT, "probe_rig_posed.png")
    scene.render.filepath = p_posed
    bpy.ops.render.render(write_still=True)

    # A centroid check is WRONG here: a rotation about an off-centre head can
    # cancel its own translation (measured: centroid delta 0.030 while every
    # vertex had moved >0.4). The property we actually care about is whether
    # the vertices follow the bone, so compare the vertex set, not its mean.
    rest_v, posed_v = rest.pop("verts"), posed.pop("verts")
    max_disp = max(math.dist(a, b) for a, b in zip(rest_v, posed_v))
    centroid_delta = math.dist(rest["centroid"], posed["centroid"])
    signatures_differ = rest["vertex_signature"] != posed["vertex_signature"]
    weight_total = sum(g.weight for g in ob.data.vertices[0].groups)
    result = {
        "rest": rest,
        "posed": posed,
        "centroid_delta": round(centroid_delta, 4),
        "max_vertex_displacement": round(max_disp, 4),
        "vertex_signatures_differ": signatures_differ,
        "mesh_follows_bone": bool(signatures_differ and max_disp > 0.15),
        "y_thickness_rest": round(rest["y_range"][1] - rest["y_range"][0], 4),
        "y_thickness_posed": round(posed["y_range"][1] - posed["y_range"][0], 4),
        "distinct_y_levels_rest": rest["distinct_y_levels"],
        "bone_count": len(arm.data.bones),
        "vertex_group_count": len(ob.vertex_groups),
        "modifiers": [[m.name, m.type] for m in ob.modifiers],
        "first_vertex_weight_total": round(weight_total, 4),
        "rest_png_sha256": sha(p_rest),
        "posed_png_sha256": sha(p_posed),
    }
    with open(os.path.join(OUT, "probe_rig.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    for k, v in result.items():
        print(f"PROBE {k} = {v}", flush=True)
    print("RIG_PROBE_OK" if result["mesh_follows_bone"] else "RIG_PROBE_FAILED", flush=True)
    return 0 if result["mesh_follows_bone"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
