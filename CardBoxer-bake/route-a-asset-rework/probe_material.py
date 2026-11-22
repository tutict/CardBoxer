"""A 路线 P0：量清源资产到底有什么，重做会丢什么。

决定走「重烘 UV/PBR」还是「连续壳 Surface Deform 驱动原高模」之前，
先把材质节点、贴图 socket、UV、连通壳、bake 可用性全部落到 JSON。
只读源 .blend，产物全写本工作区。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "foe-blender-modeling-v1" / "foe-V1.blend"


def log(*a):
    print(*a, flush=True)


def shell_count(mesh):
    n = len(mesh.vertices)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in mesh.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[b] = a
    return len({find(i) for i in range(n)})


def describe_material(mat):
    out = {"name": mat.name, "use_nodes": mat.use_nodes, "nodes": [], "links": []}
    if not mat.use_nodes:
        return out
    for n in mat.node_tree.nodes:
        row = {"name": n.name, "type": n.type}
        if n.type == "TEX_IMAGE" and n.image:
            im = n.image
            row["image"] = {"name": im.name, "size": list(im.size),
                            "channels": im.channels,
                            "filepath": im.filepath,
                            "packed": bool(im.packed_file),
                            "source": im.source,
                            "colorspace": im.colorspace_settings.name}
        if n.type == "BSDF_PRINCIPLED":
            row["inputs"] = {
                i.name: (round(i.default_value, 4)
                         if isinstance(i.default_value, float) else None)
                for i in n.inputs if i.name in ("Metallic", "Roughness")
            }
        out["nodes"].append(row)
    for l in mat.node_tree.links:
        out["links"].append({"from": f"{l.from_node.name}:{l.from_socket.name}",
                             "to": f"{l.to_node.name}:{l.to_socket.name}"})
    return out


def main() -> int:
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    mesh_obj = next(o for o in scene.objects if o.type == "MESH")
    mesh = mesh_obj.data
    log(f"ENGINE={scene.render.engine} BLENDER={bpy.app.version_string}")
    log(f"MESH name={mesh_obj.name} verts={len(mesh.vertices)} "
        f"faces={len(mesh.polygons)} uv_layers={len(mesh.uv_layers)} "
        f"modifiers={[m.type for m in mesh_obj.modifiers]}")

    mats = [describe_material(s.material) for s in mesh_obj.material_slots
            if s.material]
    bake_info = {
        "has_render_bake": hasattr(scene.render, "bake"),
        "bake_poll": None,
        "surfacedeform_bind_poll": None,
        "smart_uv_poll": None,
    }
    if bake_info["has_render_bake"]:
        b = scene.render.bake
        bake_info["use_selected_to_active_attr"] = hasattr(b, "use_selected_to_active")
        bake_info["margin_attr"] = hasattr(b, "margin")
    try:
        bake_info["bake_poll"] = bool(bpy.ops.object.bake.poll())
    except Exception as exc:
        bake_info["bake_poll"] = f"ERR {exc}"
    try:
        bake_info["surfacedeform_bind_poll"] = bool(
            bpy.ops.object.surfacedeform_bind.poll())
    except Exception as exc:
        bake_info["surfacedeform_bind_poll"] = f"ERR {exc}"
    try:
        bake_info["smart_uv_poll"] = bool(bpy.ops.uv.smart_project.poll())
    except Exception as exc:
        bake_info["smart_uv_poll"] = f"ERR {exc}"

    shells = shell_count(mesh)
    report = {
        "blend_sha256": hashlib.sha256(BLEND.read_bytes()).hexdigest(),
        "blender": bpy.app.version_string,
        "engine": scene.render.engine,
        "mesh": {"name": mesh_obj.name, "verts": len(mesh.vertices),
                 "faces": len(mesh.polygons), "edges": len(mesh.edges),
                 "uv_layers": len(mesh.uv_layers),
                 "uv_names": [u.name for u in mesh.uv_layers],
                 "materials": len(mesh.materials),
                 "modifiers": [m.type for m in mesh_obj.modifiers],
                 "shells": shells},
        "materials": mats,
        "bake": bake_info,
        "images": [{"name": im.name, "size": list(im.size),
                    "packed": bool(im.packed_file), "source": im.source,
                    "filepath": im.filepath}
                   for im in bpy.data.images],
    }
    (HERE / "material_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log("MATERIALS " + json.dumps(
        [{"name": m["name"], "tex": [n.get("image", {}).get("name")
                                     for n in m["nodes"] if n["type"] == "TEX_IMAGE"]}
         for m in mats], ensure_ascii=False))
    log(f"BAKE {json.dumps(bake_info, ensure_ascii=False)}")
    log(f"SHELLS={shells} UV={[u.name for u in mesh.uv_layers]}")
    log("MATERIAL_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
