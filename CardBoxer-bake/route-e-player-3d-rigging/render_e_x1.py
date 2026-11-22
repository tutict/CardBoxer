"""重开交付的 .blend，按 x1.0 默认增益渲代表帧。

同时也证明「重开后仍能按另一套 mapping 驱动」，不是只存了个壳。
全帧数字在 e_build.json / metrics_e.json 里；这里只出视觉对照。
用法：blender.exe -b --python render_e_x1.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import bpy

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "route-c-real-3d-fix"))
import c_build as C  # noqa: E402

BLEND = HERE / "player-V4b-deformable-continuous-shell.blend"
SPEC = BAKE / "3d-attack-gifs" / "apose_joints.json"
TABLE = BAKE / "baked2.json"
MAPPING = BAKE / "3d-attack-gifs" / "puppet_mapping.json"
OUT = HERE / "x1_shots.json"
SHOTS = [("stance", None, 0), ("jab07", "jab", 6),
         ("cross11", "cross", 10), ("wave18", "wave", 17)]


def log(*a):
    print(*a, flush=True)


def main() -> int:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    P = C.apose_points({"foe": spec["player"]})
    stance = C.joints_of(table, None, 0)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    hi = next(o for o in scene.objects
              if o.type == "MESH" and any(m.type == "SURFACE_DEFORM"
                                          for m in o.modifiers))
    shell = next(m for m in hi.modifiers
                 if m.type == "SURFACE_DEFORM").target
    assert shell is not None
    hi.hide_render = False
    shell.hide_render = True
    rows = []
    for name, card, frame in SHOTS:
        C.pose_frame(rig, P, table, stance, card, frame, mapping)
        C.setup_camera(scene, 0.0)
        p = HERE / "frames" / f"e-{name}-x1.png"
        scene.render.filepath = str(p)
        bpy.ops.render.render(write_still=True)
        b = p.read_bytes()
        assert b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 10000
        rows.append({"shot": name, "card": card, "frame": frame,
                     "file": p.name, "bytes": len(b),
                     "sha256": hashlib.sha256(b).hexdigest()})
        log(f"X1_SHOT {name} bytes={len(b)}")
    out = {"blend": BLEND.name, "gain": 1.0, "shots": rows}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    log(f"X1_RENDER_OK shots={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
