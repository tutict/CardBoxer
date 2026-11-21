"""Preflight for render_zzz.py: does the texture-preserving toon node chain
compile on this Blender, and does it keep the baseColor detail?

Uses the ALREADY EXISTING V2 GLB so it can run before V3 generation finishes.
Only writes one small PNG + a JSON into this V3 directory.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
GLB = HERE.parent / "3D模型探针V2" / "artifact_03.glb"
assert GLB.exists(), f"missing V2 probe GLB: {GLB}"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert meshes

node_types = set()
base_image = None
for o in meshes:
    for slot in o.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        nt = mat.node_tree
        for link in nt.links:
            if link.to_socket.name == "Base Color" and link.from_node.type == "TEX_IMAGE":
                base_image = link.from_node.image.name
                break
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.get(base_image) if base_image else None
        diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
        s2r = nt.nodes.new("ShaderNodeShaderToRGB")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "CONSTANT"
        els = ramp.color_ramp.elements
        els[0].position = 0.0
        els[0].color = (0.52, 0.58, 0.70, 1.0)
        els[1].position = 0.52
        els[1].color = (0.80, 0.83, 0.90, 1.0)
        els.new(0.86).color = (1.0, 1.0, 1.0, 1.0)
        nt.links.new(diff.outputs["BSDF"], s2r.inputs["Shader"])
        nt.links.new(s2r.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(tex.outputs["Color"], mix.inputs[1])
        nt.links.new(ramp.outputs["Color"], mix.inputs[2])
        nt.links.new(mix.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        node_types.update(n.bl_idname for n in nt.nodes)

scene = bpy.context.scene
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.75
scene.world = world
sun_data = bpy.data.lights.new("sun", "SUN")
sun_data.energy = 2.6
sun = bpy.data.objects.new("sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(30), math.radians(-36), math.radians(22))

# frame the raw (unnormalized) model roughly
pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
lo = [min(p[i] for p in pts) for i in range(3)]
hi = [max(p[i] for p in pts) for i in range(3)]
cz = (lo[2] + hi[2]) / 2.0
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = max(hi[2] - lo[2], 0.1) * 1.3
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -4.0, cz)
cam.rotation_euler = (Vector((0.0, 0.0, cz)) - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam

scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 320
scene.render.resolution_y = 320
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
png = HERE / "probe_zzz_shader.png"
scene.render.filepath = str(png)
bpy.ops.render.render(write_still=True)

img = bpy.data.images.load(str(png))
px = list(img.pixels[:])
# count distinct quantised colours among non-transparent pixels
seen = set()
opaque = 0
for i in range(0, len(px), 4):
    if px[i + 3] > 0.5:
        opaque += 1
        seen.add(tuple(int(px[i + j] * 8) for j in range(3)))

report = {
    "blender": bpy.app.version_string,
    "probe_glb": str(GLB.name),
    "base_color_image": base_image,
    "node_types": sorted(node_types),
    "has_shader_to_rgb": "ShaderNodeShaderToRGB" in node_types,
    "has_mix_rgb": "ShaderNodeMixRGB" in node_types,
    "color_ramp_constant": True,
    "opaque_pixels": opaque,
    "quantised_colours": len(seen),
    "png_bytes": png.stat().st_size,
    "verdict": None,
}
report["verdict"] = (
    "TOON_TEX_PROBE_OK" if report["has_shader_to_rgb"] and report["has_mix_rgb"]
    and base_image and opaque > 1000 and len(seen) > 8 else "TOON_TEX_PROBE_FAILED"
)
(HERE / "probe_zzz_shader.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False), flush=True)
