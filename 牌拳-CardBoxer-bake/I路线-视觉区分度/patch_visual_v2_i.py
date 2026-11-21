"""I 路线 v2：v1 改灯失败，改成「绝不碰灯 + 2D 合成层调色」。

v1 负结果（data/v1-failed/、boards/I-V1失败-全局变暗.png）：
玩家层灯能量三态恒 1.9/0.75/0.55/0.95、override 恒 0，
但玩家 ROI 仍暗 20.08；GL Compatibility 多 SubViewport 平行光串扰，
改灯 = 把两人一起压暗，区分度反而更差。

v2 用 CanvasItem.material 上的 canvas_item shader 对最终贴回 2D 的
ViewportTexture 调色。material 是每层独立属性，物理上不可能串到玩家层；
透明像素 alpha=0，不会盖出方块。保留 3D 材质 tint / metallic 与轮廓缩放。

用法：python patch_visual_v2_i.py（一次性，逐锚点 count==1）
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
OUT = HERE / "data" / "patch_visual_v2_i.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


PATCHES = [
    ("lights_retired_canvas_shader_added",
     "const FOE_LIGHT_ENERGY := 0.58\n"
     "const FOE_LIGHT_SHIFT := [0.78, 0.86, 1.0]\n",
     "# v2：灯光常量退役。v1 实测改灯会串到另一个 SubViewport，\n"
     "# 视觉区分改由 2D 合成层 shader 完成（每层 material 独立）。\n"
     "const FOE_CANVAS_TINT := [0.42, 0.30, 0.28]\n"
     "const FOE_CANVAS_SHADER_CODE := \"shader_type canvas_item;\\nvoid fragment() {\\n\\tvec4 c = texture(TEXTURE, UV);\\n\\tCOLOR = vec4(c.rgb * vec3(0.42, 0.30, 0.28), c.a);\\n}\\n\"\n"),

    ("canvas_material_var",
     "var _foe_materials: Array = []\n",
     "var _foe_materials: Array = []\n"
     "var _foe_canvas_mat: ShaderMaterial = null\n"),

    ("light_loop_removed_canvas_applied",
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
     "\tqueue_redraw()\n",
     "\t# I 路线 v2：灯光一个都不碰。v1 实测 GL Compatibility 下改一个\n"
     "\t# SubViewport 的 DirectionalLight3D 会让另一个 SubViewport 的角色\n"
     "\t# 一起变暗（玩家层灯能量恒定，玩家 ROI 仍暗 20.08）。\n"
     "\t# 改用每层独立的 CanvasItem.material，物理上不会串到玩家层。\n"
     "\tif enabled:\n"
     "\t\tif _foe_canvas_mat == null:\n"
     "\t\t\tvar sh := Shader.new()\n"
     "\t\t\tsh.code = FOE_CANVAS_SHADER_CODE\n"
     "\t\t\tvar sm := ShaderMaterial.new()\n"
     "\t\t\tsm.shader = sh\n"
     "\t\t\t_foe_canvas_mat = sm\n"
     "\t\tmaterial = _foe_canvas_mat\n"
     "\telse:\n"
     "\t\tmaterial = null\n"
     "\tqueue_redraw()\n"),
]


def main() -> int:
    before = {str(p.relative_to(GAME)).replace("\\", "/"): sha(p)
              for p in (LAYER, ARENA, FIGHTER)}
    data = LAYER.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    work = data.replace(eol, b"\n")
    # 幂等：已应用时跳过补丁，只按盘上源码复算判据（便于收口重跑）。
    applied = []
    if b"FOE_CANVAS_SHADER_CODE" not in work:
        for name, old, new in PATCHES:
            o, n = old.encode("utf-8"), new.encode("utf-8")
            assert work.count(o) == 1, (
                f"anchor not unique: {name} count={work.count(o)}")
            work = work.replace(o, n, 1)
            applied.append(name)
        LAYER.write_bytes(work.replace(b"\n", eol))
    else:
        applied = ["ALREADY_APPLIED"]

    src = LAYER.read_text(encoding="utf-8")
    checks = {
        "arena_untouched": sha(ARENA) == before["scripts/arena.gd"],
        "fighter_untouched": sha(FIGHTER) == before["scripts/fighter.gd"],
        "three_patches_or_idempotent": (
            len(applied) == 3 or applied == ["ALREADY_APPLIED"]),
        # 只禁「运行时改灯」；_add_light() 里创建灯的赋值是合法且必需的。
        "no_runtime_light_energy_write": (
            'l.light_energy = float(row["energy"])' not in src),
        "no_runtime_light_color_write": (
            'l.light_color = lc * Color(' not in src),
        "light_creation_assignments_present": (
            "l.light_energy = energy" in src
            and "l.light_color = col" in src),
        "retired_constants_gone": ("const FOE_LIGHT_ENERGY" not in src
                                   and "const FOE_LIGHT_SHIFT" not in src),
        "canvas_shader_present": "shader_type canvas_item" in src,
        "canvas_material_set": "material = _foe_canvas_mat" in src,
        "canvas_material_cleared": "material = null" in src,
        "shader_tint_matches_spec": "vec3(0.42, 0.30, 0.28)" in src,
        "still_has_3d_tint": "dup.albedo_color = b.albedo_color * Color(" in src,
        "still_has_draw_scale": "FOE_DRAW_SCALE_X if foe_visual else 1.0" in src,
        "restore_clears_override": (
            "set_surface_override_material(i, null)" in src),
        "G_shape_preserved": all(s in src for s in [
            "const DEFAULT_SIDE_YAW := 55.0",
            "drv.apply_frame(c, f)", "_apply_stance_bias()"]),
    }
    after = {str(p.relative_to(GAME)).replace("\\", "/"): sha(p)
             for p in (LAYER, ARENA, FIGHTER)}
    report = {"before": before, "after": after, "applied": applied,
              "eol": "CRLF" if eol == b"\r\n" else "LF",
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
    print("PATCH_VISUAL_V2_I_OK" if report["ok"]
          else "PATCH_VISUAL_V2_I_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
