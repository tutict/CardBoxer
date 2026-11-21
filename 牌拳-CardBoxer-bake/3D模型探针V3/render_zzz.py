"""Cel-shaded multi-angle renders of the V3 generated character.

The 3D generation service emits PBR textures, which look soft/half-realistic.
The "Zenless Zone Zero" look needs hard-edged toon bands, so we KEEP the
4096px baseColor texture (cloud hem, frog buttons, face) and multiply it by a
quantised lighting factor:

    Image(baseColor) x [Diffuse -> ShaderToRGB -> ColorRamp(CONSTANT 3 bands)]
        -> Emission -> Output

Shadow band is a lifted cool grey (not crushed black), matching the reference's
"no crushed blacks". Outlines are deliberately NOT done here: the mesh is >1000
disconnected open shells, so inverted-hull outlines would turn into porridge.
A same-hue/darker thin outline is added later in Pillow from the alpha edge.

Outputs transparent RGBA PNGs plus render_zzz.json. No game file is touched.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
TARGET_HEIGHT = 1.72
ORTHO = 2.30
RES = 768
SHOTS = [("front", 0), ("angle25", 25), ("angle55", 55), ("back35", -35)]


def find_glb():
    for p in sorted(HERE.glob("artifact_*")):
        if p.is_file() and p.read_bytes()[:4] == b"glTF":
            return p
    raise SystemExit("NO_GLB: generation artifacts not present yet")


GLB = find_glb()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert meshes, "no mesh imported"
print(f"IMPORT glb={GLB.name} meshes={len(meshes)}", flush=True)

# --- normalize to the game's 1.72 m scale ---------------------------------
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
lo = [min(p[i] for p in pts) for i in range(3)]
hi = [max(p[i] for p in pts) for i in range(3)]
scale = TARGET_HEIGHT / (hi[2] - lo[2])
cx, cy = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
for o in meshes:
    for v in o.data.vertices:
        v.co = Vector(((v.co.x - cx) * scale,
                       (v.co.y - cy) * scale,
                       (v.co.z - lo[2]) * scale))
    o.data.update()
print(f"NORMALIZE scale={scale:.6f} raw_height={hi[2]-lo[2]:.4f}", flush=True)


# --- replace each material with a texture-preserving toon shader ----------
def toonify(mat):
    nt = mat.node_tree
    base_img = None
    for link in nt.links:
        if link.to_socket.name == "Base Color" and link.from_node.type == "TEX_IMAGE":
            base_img = link.from_node.image
            break
    if base_img is None:
        for n in nt.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                base_img = n.image
                break
    if base_img is None:
        return False

    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = base_img
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    diff.inputs["Roughness"].default_value = 1.0
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position = 0.00
    els[0].color = (0.52, 0.58, 0.70, 1.0)   # lifted cool-grey shadow
    els[1].position = 0.52
    els[1].color = (0.80, 0.83, 0.90, 1.0)   # mid
    els.new(0.86).color = (1.0, 1.0, 1.0, 1.0)  # light
    nt.links.new(diff.outputs["BSDF"], s2r.inputs["Shader"])
    nt.links.new(s2r.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(tex.outputs["Color"], mix.inputs[1])
    nt.links.new(ramp.outputs["Color"], mix.inputs[2])
    nt.links.new(mix.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return True


toonified = 0
for o in meshes:
    for slot in o.material_slots:
        if slot.material and slot.material.use_nodes:
            if toonify(slot.material):
                toonified += 1
print(f"TOON materials={toonified}", flush=True)
assert toonified > 0, "no baseColor texture found; toon shader not wired"

# --- lighting / camera ----------------------------------------------------
scene = bpy.context.scene
world = bpy.data.worlds.new("zzz_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.59, 0.68, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.75
scene.world = world

sun_data = bpy.data.lights.new("zzz_key", "SUN")
sun_data.energy = 2.6
sun = bpy.data.objects.new("zzz_key", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(30), math.radians(-36), math.radians(22))

cam_data = bpy.data.cameras.new("zzz_cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = ORTHO
cam = bpy.data.objects.new("zzz_cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = RES
scene.render.resolution_y = RES
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True

target = Vector((0.0, 0.0, 0.86))
R = 4.0
t0 = time.time()
outputs = []
for name, deg in SHOTS:
    a = math.radians(deg)
    cam.location = (R * math.sin(a), -R * math.cos(a), target.z)
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    path = HERE / f"zzz-{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    outputs.append({"shot": name, "angle_deg": deg, "file": path.name,
                    "bytes": path.stat().st_size})
    print(f"RENDER {name} {path.stat().st_size} B", flush=True)

report = {
    "blender": bpy.app.version_string,
    "glb": GLB.name,
    "normalize_scale": round(scale, 6),
    "raw_height_m": round(hi[2] - lo[2], 5),
    "toon_materials": toonified,
    "shader": "baseColor x [Diffuse>ShaderToRGB>ColorRamp(CONSTANT 3)] > Emission",
    "outline": "deferred to Pillow alpha-edge pass (open-shell mesh)",
    "ortho_scale": ORTHO,
    "resolution": RES,
    "shots": outputs,
    "elapsed_seconds": round(time.time() - t0, 2),
}
(HERE / "render_zzz.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"RENDER_ZZZ_OK shots={len(outputs)} elapsed={report['elapsed_seconds']}s",
      flush=True)
