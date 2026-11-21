"""A1 成本探针：如果坚持「重烘 UV/PBR」，本机到底要付多少代价。

只测最小可行链路：Cycles + 选中态 + 512² diffuse bake 到自身 UV，
量 poll / 成功 / 耗时。不做高模->连续壳的 selected_to_active 全量烘焙
（那还要给连续壳 Smart UV、逐张 4096² 重烘 3 张贴图），因为 A2 已证
「贴图一张不动」即可达成资产目标，A1 只是把成本账量出来。

只读源 .blend；产物写本工作区。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "对手怪Blender建模V1" / "对手怪V1.blend"


def log(*a):
    print(*a, flush=True)


def main() -> int:
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    src = next(o for o in scene.objects if o.type == "MESH")
    engine_before = scene.render.engine
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    bpy.ops.object.select_all(action="DESELECT")
    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    if src.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    poll = bool(bpy.ops.object.bake.poll())

    mat = next(s.material for s in src.material_slots if s.material)
    img = bpy.data.images.new("a1_bake_probe", width=512, height=512,
                              alpha=False, float_buffer=False)
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    mat.node_tree.nodes.active = node
    node.select = True

    out = {"engine_before": engine_before, "engine_used": "CYCLES",
           "bake_poll_after_setup": poll,
           "image_size": [512, 512], "samples": scene.cycles.samples,
           "use_selected_to_active": False}
    err = None
    ok = False
    if poll:
        ts = time.time()
        try:
            scene.render.bake.use_selected_to_active = False
            bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"})
            ok = True
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
        out["bake_seconds"] = round(time.time() - ts, 2)
    out["bake_ok"] = ok
    out["error"] = err

    png = None
    if ok:
        p = HERE / "frames" / "a1-bake-probe.png"
        img.filepath_raw = str(p)
        img.file_format = "PNG"
        img.save()
        b = p.read_bytes()
        png = {"file": p.name, "bytes": len(b),
               "sha256": hashlib.sha256(b).hexdigest(),
               "valid_png": b[:8] == b"\x89PNG\r\n\x1a\n"}
    out["png"] = png
    out["elapsed_seconds"] = round(time.time() - t0, 2)
    (HERE / "bake_probe.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log("BAKE_PROBE " + json.dumps(out, ensure_ascii=False))
    log("BAKE_PROBE_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
