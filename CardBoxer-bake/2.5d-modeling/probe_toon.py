"""Minimal feasibility probe: does EEVEE in Blender 5.2.3 actually quantise
Diffuse -> ShaderToRGB -> ColorRamp(CONSTANT) into hard cel-shading bands?

Renders one sphere to probe_toon.png. Verified by counting distinct colours
with Pillow afterwards: a continuous Principled render gives hundreds, a real
toon render gives a handful of flat bands (+ antialiasing edges).
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0)
ball = bpy.context.object
for poly in ball.data.polygons:
    poly.use_smooth = True

mat = bpy.data.materials.new("ProbeToon")
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()

diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
diff.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
s2rgb = nt.nodes.new("ShaderNodeShaderToRGB")
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.interpolation = "CONSTANT"
ramp.color_ramp.elements[0].position = 0.0
ramp.color_ramp.elements[0].color = (0.16, 0.20, 0.34, 1.0)
ramp.color_ramp.elements[1].position = 0.48
ramp.color_ramp.elements[1].color = (0.42, 0.50, 0.68, 1.0)
e2 = ramp.color_ramp.elements.new(0.78)
e2.color = (0.90, 0.93, 1.0, 1.0)
emit = nt.nodes.new("ShaderNodeEmission")
out = nt.nodes.new("ShaderNodeOutputMaterial")

links = nt.links
links.new(diff.outputs["BSDF"], s2rgb.inputs["Shader"])
links.new(s2rgb.outputs["Color"], ramp.inputs["Fac"])
links.new(ramp.outputs["Color"], emit.inputs["Color"])
links.new(emit.outputs["Emission"], out.inputs["Surface"])
ball.data.materials.append(mat)

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
world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.2, 0.2, 0.25, 1.0)
world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.15

cam_data = bpy.data.cameras.new("ProbeCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 2.6
cam = bpy.data.objects.new("ProbeCam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0.0, -5.0, 0.0)
cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam

sun_data = bpy.data.lights.new("ProbeSun", "SUN")
sun_data.energy = 2.2
sun = bpy.data.objects.new("ProbeSun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(32), math.radians(-38), math.radians(20))

scene.render.filepath = os.path.join(HERE, "probe_toon.png")
bpy.ops.render.render(write_still=True)
print("TOON_PROBE_OK", flush=True)
