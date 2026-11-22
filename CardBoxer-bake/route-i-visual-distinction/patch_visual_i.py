"""I 路线 P2：把「对手侧专属视觉层」接进 fighter_3d_layer.gd。

一次性补丁；逐锚点 count==1 断言，二进制读写（保留原 EOL），
补丁前后 sha256 落盘到 data/patch_visual_i.json。
arena.gd / fighter.gd / 任何资产一律不碰。

玩法：configure("foe", ...) 自动启用；CARD_BOXER_FOE_VISUAL=none 或
set_foe_visual(false) 完整还原；玩家层与未配置层逐像素不变。

用法：python patch_visual_i.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
LAYER = GAME / "scripts" / "fighter_3d_layer.gd"
ARENA = GAME / "scripts" / "arena.gd"
FIGHTER = GAME / "scripts" / "fighter.gd"
ORIG = HERE / "orig" / "pre-visual" / "scripts"
OUT = HERE / "data" / "patch_visual_i.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# (名字, 原文, 新文)；全部按 LF 写，运行时按文件实际 EOL 转换。
PATCHES = [
    ("foe_visual_constants",
     "const DEFAULT_FOE_YAW := -55.0\n",
     "const DEFAULT_FOE_YAW := -55.0\n"
     "\n"
     "# ── I 路线「视觉区分度」：只作用于 foe ──────────────────────\n"
     "# rootcause_i.json：贴图 UV 岛亮度差 70.99 被四盏高强度灯 +\n"
     "# metallic 乘数 1.0 吃成渲染 -11.18。这里改渲染链，不动 GLB。\n"
     "# 数值与 data/visual_diff_spec.json 逐项对应，改一处要改两处。\n"
     "const FOE_TINT := [0.46, 0.34, 0.30]\n"
     "const FOE_METALLIC_MULT := 0.35\n"
     "const FOE_LIGHT_ENERGY := 0.58\n"
     "const FOE_LIGHT_SHIFT := [0.78, 0.86, 1.0]\n"
     "const FOE_DRAW_SCALE_X := 1.16\n"
     "const FOE_DRAW_SCALE_Y := 0.94\n"),

    ("foe_visual_state_vars",
     "var view_changes := 0\n",
     "var view_changes := 0\n"
     "# I 路线：foe 专属视觉开关与可还原的原始资源表。\n"
     "var foe_visual := false\n"
     "var _mesh_rows: Array = []\n"
     "var _light_rows: Array = []\n"
     "var _foe_materials: Array = []\n"),

    ("light_rows_recorded",
     "\tvar l := DirectionalLight3D.new()\n"
     "\tl.rotation_degrees = rot\n"
     "\tl.light_energy = energy\n"
     "\tl.light_color = col\n"
     "\tl.shadow_enabled = shadow\n"
     "\tsv.add_child(l)\n",
     "\tvar l := DirectionalLight3D.new()\n"
     "\tl.rotation_degrees = rot\n"
     "\tl.light_energy = energy\n"
     "\tl.light_color = col\n"
     "\tl.shadow_enabled = shadow\n"
     "\tsv.add_child(l)\n"
     "\t# I 路线：记下原始能量/颜色，set_foe_visual(false) 要逐项还原。\n"
     "\t_light_rows.append({\"light\": l, \"energy\": energy,\n"
     "\t\t\t\"color\": col})\n"),

    ("configure_enables_foe_visual",
     "\tview_yaw_deg = p_yaw\n"
     "\tview_flip = p_flip\n"
     "\n"
     "\n"
     "## 探针/运行时改视角",
     "\tview_yaw_deg = p_yaw\n"
     "\tview_flip = p_flip\n"
     "\t# I 路线：只有 foe 启用视觉区分；none 用于同进程 A/B 还原 H 原样。\n"
     "\tif p_role == \"foe\" and OS.get_environment(\n"
     "\t\t\t\"CARD_BOXER_FOE_VISUAL\") != \"none\":\n"
     "\t\tfoe_visual = true\n"
     "\n"
     "\n"
     "## 探针/运行时改视角"),

    ("collect_meshes_after_instantiate",
     "\tvar inst: Node3D = (res as PackedScene).instantiate()\n"
     "\tsv.add_child(inst)\n",
     "\tvar inst: Node3D = (res as PackedScene).instantiate()\n"
     "\tsv.add_child(inst)\n"
     "\t# I 路线：收集基础材质，运行时 tint 只在副本上做。\n"
     "\t_collect_meshes(inst)\n"),

    ("apply_visual_after_lights",
     "\t_add_light(Vector3(-25.0, 200.0, 0.0), 0.95,\n"
     "\t\t\tColor(0.76, 0.85, 1.00), false)\n"
     "\n"
     "\tapply(\"stance\", 0)\n",
     "\t_add_light(Vector3(-25.0, 200.0, 0.0), 0.95,\n"
     "\t\t\tColor(0.76, 0.85, 1.00), false)\n"
     "\n"
     "\tif foe_visual:\n"
     "\t\tset_foe_visual(true)\n"
     "\tapply(\"stance\", 0)\n"),

    ("visual_methods_inserted",
     "func apply(card: String, frame: int) -> void:\n",
     "## I 路线：递归收集 MeshInstance3D 的 surface 基础材质。\n"
     "func _collect_meshes(n: Node) -> void:\n"
     "\tif n is MeshInstance3D:\n"
     "\t\tvar mi := n as MeshInstance3D\n"
     "\t\tif mi.mesh != null:\n"
     "\t\t\tfor i in range(mi.mesh.get_surface_count()):\n"
     "\t\t\t\t_mesh_rows.append({\"mi\": mi, \"surface\": i,\n"
     "\t\t\t\t\t\t\"base\": mi.mesh.surface_get_material(i)})\n"
     "\tfor c in n.get_children():\n"
     "\t\t_collect_meshes(c)\n"
     "\n"
     "\n"
     "## I 路线：可反复切换。true = 压暗偏锈红 + 降金属度 + 降灯能量 +\n"
     "## 加宽压矮轮廓；false = 逐项还原到 H 路线原样（玩家层恒定 false）。\n"
     "func set_foe_visual(enabled: bool) -> void:\n"
     "\tfoe_visual = enabled\n"
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
     "\tfor row in _light_rows:\n"
     "\t\tvar l: DirectionalLight3D = row[\"light\"]\n"
     "\t\tvar lc: Color = row[\"color\"]\n"
     "\t\tif enabled:\n"
     "\t\t\tl.light_energy = float(row[\"energy\"]) * FOE_LIGHT_ENERGY\n"
     "\t\t\tl.light_color = lc * Color(\n"
     "\t\t\t\t\tFOE_LIGHT_SHIFT[0], FOE_LIGHT_SHIFT[1],\n"
     "\t\t\t\t\tFOE_LIGHT_SHIFT[2], 1.0)\n"
     "\t\telse:\n"
     "\t\t\tl.light_energy = float(row[\"energy\"])\n"
     "\t\t\tl.light_color = lc\n"
     "\tqueue_redraw()\n"
     "\n"
     "\n"
     "## 探针读回状态，避免靠画面猜开关有没有生效。\n"
     "func visual_state() -> Dictionary:\n"
     "\treturn {\"role\": role_id, \"foe_visual\": foe_visual,\n"
     "\t\t\t\"mesh_rows\": _mesh_rows.size(),\n"
     "\t\t\t\"light_rows\": _light_rows.size(),\n"
     "\t\t\t\"foe_materials\": _foe_materials.size()}\n"
     "\n"
     "\n"
     "func apply(card: String, frame: int) -> void:\n"),

    ("draw_scaled_only_for_foe",
     "\tvar w := float(SV_W) * DRAW_SCALE\n"
     "\tvar h := float(SV_H) * DRAW_SCALE\n",
     "\t# I 路线：只有启用 foe 视觉时改绘制尺寸；玩家侧乘 1.0 精确不变。\n"
     "\tvar sx := FOE_DRAW_SCALE_X if foe_visual else 1.0\n"
     "\tvar sy := FOE_DRAW_SCALE_Y if foe_visual else 1.0\n"
     "\tvar w := float(SV_W) * DRAW_SCALE * sx\n"
     "\tvar h := float(SV_H) * DRAW_SCALE * sy\n"),
]


def main() -> int:
    before = {str(p.relative_to(GAME)).replace("\\", "/"): sha(p)
              for p in (LAYER, ARENA, FIGHTER)}
    backup = {str(p.relative_to(GAME)).replace("\\", "/"):
              sha(ORIG / p.name) for p in (LAYER, ARENA, FIGHTER)}
    data = LAYER.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    work = data.replace(eol, b"\n")
    applied = []
    for name, old, new in PATCHES:
        o = old.encode("utf-8")
        n = new.encode("utf-8")
        assert work.count(o) == 1, f"anchor not unique: {name} count={work.count(o)}"
        work = work.replace(o, n, 1)
        applied.append(name)
    LAYER.write_bytes(work.replace(b"\n", eol))

    src = LAYER.read_text(encoding="utf-8")
    checks = {
        "arena_untouched": sha(ARENA) == before["scripts/arena.gd"],
        "fighter_untouched": sha(FIGHTER) == before["scripts/fighter.gd"],
        "backup_matches_before": all(
            backup[k] == before[k] for k in before),
        "eight_patches_applied": len(applied) == 8,
        "switch_default_off": (
            "var use_3d := false" in ARENA.read_text(encoding="utf-8")),
        "foe_visual_auto_on": (
            'p_role == "foe" and OS.get_environment(' in src),
        "off_switch_present": 'CARD_BOXER_FOE_VISUAL' in src,
        "tint_uses_duplicate": ".duplicate()" in src,
        "restore_clears_override": (
            "set_surface_override_material(i, null)" in src),
        "lights_restored": ('l.light_energy = float(row["energy"])'
                            in src),
        "draw_scale_conditional": (
            "FOE_DRAW_SCALE_X if foe_visual else 1.0" in src),
        "spec_values_present": all(s in src for s in [
            "const FOE_TINT := [0.46, 0.34, 0.30]",
            "const FOE_METALLIC_MULT := 0.35",
            "const FOE_LIGHT_ENERGY := 0.58",
            "const FOE_DRAW_SCALE_X := 1.16"]),
        "visual_state_probe": "func visual_state()" in src,
        "G_shape_preserved": all(s in src for s in [
            "const DEFAULT_SIDE_YAW := 55.0",
            "drv.apply_frame(c, f)", "_apply_stance_bias()"]),
    }
    after = {str(p.relative_to(GAME)).replace("\\", "/"): sha(p)
             for p in (LAYER, ARENA, FIGHTER)}
    report = {"before": before, "backup": backup, "after": after,
              "applied": applied, "eol": "CRLF" if eol == b"\r\n" else "LF",
              "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for a in applied:
        print("PATCH", a)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PATCH_VISUAL_I_OK" if report["ok"] else "PATCH_VISUAL_I_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
