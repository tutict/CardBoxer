"""Owned background Blender diagnostic: import/export each frozen source unedited.

Run: blender --background --factory-startup --python this_file.py
Only writes tools/pipeline_roundtrip/ and logs its Blender version/options.
"""
import hashlib
import json
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"tools/pipeline_roundtrip"
OUT.mkdir(exist_ok=True)
OPTIONS=dict(export_format="GLB",use_selection=True,export_skins=True,
             export_morph=True,export_morph_normal=True,export_animations=False,
             export_apply=False,export_yup=True,export_materials="EXPORT")
records=[]
for role in ("player","foe"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source=ROOT/"baseline/assets/3d"/(role+"-rigged.glb")
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes=[o for o in bpy.context.scene.objects if o.type=="MESH" and any(m.type=="ARMATURE" for m in o.modifiers)]
    armatures=[o for o in bpy.context.scene.objects if o.type=="ARMATURE"]
    assert len(meshes)==len(armatures)==1,(meshes,armatures)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes+armatures:obj.select_set(True)
    raw=OUT/(role+"-roundtrip-raw.glb")
    bpy.ops.export_scene.gltf(filepath=str(raw),**OPTIONS)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before,"Source modified"
    records.append(dict(role=role,source=str(source),source_sha256=before,
                        raw=str(raw),raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                        blender_version=bpy.app.version_string,export_options=OPTIONS,
                        mesh_vertices=len(meshes[0].data.vertices),mesh_polygons=len(meshes[0].data.polygons),
                        armature_bones=[bone.name for bone in armatures[0].data.bones]))
(OUT/"blender-roundtrip-provenance.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
print("PIPELINE_UNEDITED_ROUNDTRIP_EXPORTED",json.dumps(records,indent=2))
