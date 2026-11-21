"""从玩家 V4b 可变形 .blend 导出四口径 GLB，量化 glTF 带走/丢掉什么。

口径与 C 路线完全同款，便于逐项对照：
  player-full        高模 + 代理壳 + 13 骨，材质 EXPORT
  player-stance      只高模 / 站架 / export_apply=True（烘焙 SURFACE_DEFORM）
  player-cross       只高模 / cross#10 驱动后 / export_apply=True
  player-proxy-rig   只代理壳 + 13 骨（glTF 里唯一可能保留 skin 的口径）

另外记录 3 张 packed 4096² 的字节与 sha256，供 inspect_e_gltf.py
逐字节核对「贴图零重编码」。
用法：blender.exe -b --python export_e_gltf.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = HERE / "玩家V4b-可变形连续壳.blend"
sys.path.insert(0, str(BAKE / "C路线-真3D修复"))
import c_build as C  # noqa: E402

SPEC = BAKE / "3D攻击GIF" / "apose_joints.json"
TABLE = BAKE / "baked2.json"
MAPPING = BAKE / "3D攻击GIF" / "puppet_mapping.json"
OUT = HERE / "export_e.json"


def log(*a):
    print(*a, flush=True)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def drive_pose(rig, P, table, stance, card, frame, gain=1.0):
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    if gain != 1.0:
        mapping["arm_gain_deg"] = {
            k: v * gain for k, v in mapping["arm_gain_deg"].items()}
    C.pose_frame(rig, P, table, stance, card, frame, mapping)
    bpy.context.view_layer.update()


def do_export(name, objs, *, apply_modifiers, materials, description):
    for o in bpy.context.scene.objects:
        o.hide_set(False)
        o.hide_render = False
        o.hide_viewport = False
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    path = HERE / (name + ".glb")
    if path.exists():
        path.unlink()
    t0 = time.time()
    result = bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_apply=apply_modifiers, export_animations=True,
        export_skins=True, export_materials=materials,
        export_cameras=False, export_lights=False, export_yup=True)
    elapsed = round(time.time() - t0, 3)
    assert path.is_file() and path.stat().st_size > 100, (name, result)
    row = {"name": name, "file": path.name, "description": description,
           "objects": [o.name for o in objs],
           "export_apply": apply_modifiers, "export_materials": materials,
           "export_animations": True, "export_skins": True,
           "operator_result": list(result),
           "bytes": path.stat().st_size, "sha256": sha256(path),
           "elapsed_seconds": elapsed}
    log(f"EXPORT {name} bytes={row['bytes']} elapsed={elapsed}s "
        f"result={row['operator_result']}")
    return row


def main() -> int:
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    hi = next(o for o in scene.objects
              if o.type == "MESH"
              and any(m.type == "SURFACE_DEFORM" for m in o.modifiers))
    shell = next(o for o in scene.objects
                 if o.type == "MESH"
                 and any(m.type == "ARMATURE" for m in o.modifiers))
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    P = C.apose_points({"foe": spec["player"]})
    stance = C.joints_of(table, None, 0)
    packed = []
    for im in bpy.data.images:
        if im.source == "FILE" and im.packed_file:
            data = bytes(im.packed_file.data)
            packed.append({"name": im.name, "size": list(im.size),
                           "bytes": len(data), "sha256": sha(data)})
    packed.sort(key=lambda x: x["name"])
    log(f"OBJECTS hi={hi.name} shell={shell.name} rig={rig.name} "
        f"bones={len(rig.pose.bones)} packed_images={len(packed)}")

    rows = []
    rows.append(do_export(
        "player-full", [hi, shell, rig], apply_modifiers=False,
        materials="EXPORT",
        description="完整场景口径：高模 + 代理壳 + 13 骨，PBR 贴图导出"))
    drive_pose(rig, P, table, stance, None, 0, 1.0)
    rows.append(do_export(
        "player-stance", [hi], apply_modifiers=True, materials="NONE",
        description="只高模 / 站架 / 烘焙 SURFACE_DEFORM / 无材质"))
    drive_pose(rig, P, table, stance, "cross", 10, 1.5)
    rows.append(do_export(
        "player-cross", [hi], apply_modifiers=True, materials="NONE",
        description="只高模 / cross#10 增益 x1.5 / 烘焙 SURFACE_DEFORM / 无材质"))
    drive_pose(rig, P, table, stance, None, 0, 1.0)
    rows.append(do_export(
        "player-proxy-rig", [shell, rig], apply_modifiers=False,
        materials="NONE",
        description="只代理壳 + 13 骨 / 无材质，检验 skin 是否随导出"))

    out = {
        "blender": bpy.app.version_string,
        "blend_sha256": sha256(BLEND),
        "source_object": {"high_poly": hi.name, "proxy_shell": shell.name,
                          "rig": rig.name, "rig_bones": len(rig.pose.bones)},
        "apose_table": "player",
        "packed_images": packed,
        "exports": rows,
        "total_bytes": sum(r["bytes"] for r in rows),
        "elapsed_seconds": round(time.time() - t0, 3),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    log(f"TOTAL_BYTES={out['total_bytes']} elapsed={out['elapsed_seconds']}s")
    log("GLTF_EXPORT_E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
