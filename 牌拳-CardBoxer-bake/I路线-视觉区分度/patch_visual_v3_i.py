"""I 路线 v3：3D 材质 override 整套退役，只留纯 2D 合成调色。

v1 负结果：改灯 → 两人都暗（GL Compatibility 多 SubViewport 平行光串扰）。
v2 负结果：灯不改了，但改 foe 层 surface override 仍让玩家层角色
整体变暗（7940/33390 px，变化像素平均 -25；零操作同状态对照 0）。

v3：3D 渲染树（灯 / 材质 / mesh）完全保持 H 原样，视觉区分只由
foe 层自己的 CanvasItem.material（canvas_item shader）+ 绘制尺寸承担。
这两者都是 2D 层本地属性，理论上不可能影响玩家层。

幂等：已应用时跳过补丁，只按盘上源码复算判据。
用法：python patch_visual_v3_i.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
LAYER = GAME / "scripts" / "fighter_3d_layer.gd"
ARENA = GAME / "scripts" / "arena.gd"
FIGHTER = GAME / "scripts" / "fighter.gd"
OUT = HERE / "data" / "patch_visual_v3_i.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


OLD = (
    "\tfor idx in range(_mesh_rows.size()):\n"
    "\t\tvar row: Dictionary = _mesh_rows[idx]\n"
    "\t\tvar mi: MeshInstance3D = row[\"mi\"]\n"
    "\t\tvar i: int = int(row[\"surface\"])\n"
    "\t\tif not enabled:\n"
    "\t\t\tmi.set_surface_override_material(i, null)\n"
    "\t\t\tcontinue\n"
    "\t\tvar base: Material = row[\"base\"]\n"
    "\t\tif base is StandardMaterial3D:\n"
    "\t\t\tif _foe_materials.size() <= idx:\n"
    "\t\t\t\tvar dup := (base as StandardMaterial3D).duplicate()\n"
    "\t\t\t\tvar b := base as StandardMaterial3D\n"
    "\t\t\t\tdup.albedo_color = b.albedo_color * Color(\n"
    "\t\t\t\t\t\tFOE_TINT[0], FOE_TINT[1], FOE_TINT[2], 1.0)\n"
    "\t\t\t\tdup.metallic = b.metallic * FOE_METALLIC_MULT\n"
    "\t\t\t\t_foe_materials.append(dup)\n"
    "\t\t\tmi.set_surface_override_material(i, _foe_materials[idx])\n"
)
NEW = (
    "\t# I 路线 v3：3D 材质一律不动。v2 实测改 foe 层 surface override\n"
    "\t# 会让玩家层角色整体变暗（7940 px / 变化像素平均 -25），即使两层\n"
    "\t# 灯能量、玩家层 override、玩家层 CanvasItem.material 全部恒定。\n"
    "\t# 视觉区分全部交给纯 2D 合成的 canvas_item shader + 绘制尺寸。\n"
)


def main() -> int:
    before = {str(p.relative_to(GAME)).replace("\\", "/"): sha(p)
              for p in (LAYER, ARENA, FIGHTER)}
    data = LAYER.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    work = data.replace(eol, b"\n")
    applied = "SKIPPED_ALREADY_APPLIED"
    if OLD.encode("utf-8") in work:
        assert work.count(OLD.encode("utf-8")) == 1, "anchor not unique"
        work = work.replace(OLD.encode("utf-8"), NEW.encode("utf-8"), 1)
        LAYER.write_bytes(work.replace(b"\n", eol))
        applied = "V3_APPLIED"
    src = LAYER.read_text(encoding="utf-8")
    checks = {
        "arena_untouched": sha(ARENA) == before["scripts/arena.gd"],
        "fighter_untouched": sha(FIGHTER) == before["scripts/fighter.gd"],
        "no_surface_override_calls": (
            "set_surface_override_material" not in src),
        # 只禁「复制 3D 材质」；DEFAULT_STANCE_BIAS.duplicate() 是
        # G 路线本来就有的字典拷贝，不能一起禁。
        "no_3d_material_duplicate": (
            "(base as StandardMaterial3D).duplicate()" not in src),
        "no_light_energy_write": (
            'l.light_energy = float(row["energy"])' not in src),
        "canvas_shader_present": "shader_type canvas_item" in src,
        "canvas_material_set": "material = _foe_canvas_mat" in src,
        "canvas_material_cleared": "material = null" in src,
        "shader_tint_matches_spec": "vec3(0.42, 0.30, 0.28)" in src,
        "draw_scale_kept": (
            "FOE_DRAW_SCALE_X if foe_visual else 1.0" in src),
        "collect_meshes_kept_for_diagnostics": (
            "func _collect_meshes" in src),
        "G_shape_preserved": all(s in src for s in [
            "const DEFAULT_SIDE_YAW := 55.0",
            "drv.apply_frame(c, f)", "_apply_stance_bias()"]),
    }
    after = {str(p.relative_to(GAME)).replace("\\", "/"): sha(p)
             for p in (LAYER, ARENA, FIGHTER)}
    report = {"before": before, "after": after, "applied": applied,
              "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("PATCH", applied)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PATCH_VISUAL_V3_I_OK" if report["ok"]
          else "PATCH_VISUAL_V3_I_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
