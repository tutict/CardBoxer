"""I 路线 final：让源码与 visual_diff_spec.json r2 逐项对齐。

r1（draw_scale_x=1.16）实测宽 ROI 轮廓比 1.0889 < spec 目标 1.1。
按项目规矩**不放宽阈值**，把实现从 1.16 提到 1.22，再重跑同进程 A/B。

顺带清掉 v1/v2/v3 留在源码里的过期债：
  - 退役常量 FOE_TINT / FOE_METALLIC_MULT / FOE_CANVAS_TINT
  - 仍写着「改 3D 材质 / 降灯能量 / 运行时 tint 在副本上做」的注释
  - 让 FOE_CANVAS_SHADER_CODE 成为 canvas tint 的唯一真相来源

幂等：已应用时跳过替换，只按盘上源码 + spec + baseline_i.json 复算判据。
用法：python patch_visual_final_i.py
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
SPEC = HERE / "data" / "visual_diff_spec.json"
BASELINE = HERE / "baseline_i.json"
OUT = HERE / "data" / "patch_visual_final_i.json"

SHADER_LINE = (
    'const FOE_CANVAS_SHADER_CODE := '
    '"shader_type canvas_item;\\nvoid fragment() {\\n'
    '\\tvec4 c = texture(TEXTURE, UV);\\n'
    '\\tCOLOR = vec4(c.rgb * vec3(0.42, 0.30, 0.28), c.a);'
    '\\n}\\n"\n'
)

OLD_HEAD = (
    "# ── I 路线「视觉区分度」：只作用于 foe ──────────────────────\n"
    "# rootcause_i.json：贴图 UV 岛亮度差 70.99 被四盏高强度灯 +\n"
    "# metallic 乘数 1.0 吃成渲染 -11.18。这里改渲染链，不动 GLB。\n"
    "# 数值与 data/visual_diff_spec.json 逐项对应，改一处要改两处。\n"
    "const FOE_TINT := [0.46, 0.34, 0.30]\n"
    "const FOE_METALLIC_MULT := 0.35\n"
    "# v2：灯光常量退役。v1 实测改灯会串到另一个 SubViewport，\n"
    "# 视觉区分改由 2D 合成层 shader 完成（每层 material 独立）。\n"
    "const FOE_CANVAS_TINT := [0.42, 0.30, 0.28]\n"
    + SHADER_LINE
    + "const FOE_DRAW_SCALE_X := 1.16\n"
    "const FOE_DRAW_SCALE_Y := 0.94\n"
)

NEW_HEAD = (
    "# ── I 路线「视觉区分度」：只作用于 foe ──────────────────────\n"
    "# rootcause_i.json：贴图 UV 岛亮度差 70.99 被四盏高强度灯 +\n"
    "# metallic 乘数 1.0 吃成渲染 -11.18。定稿走纯 2D 合成层：\n"
    "# 3D 渲染树（灯 / 材质 / mesh）与 GLB 一个都不动。\n"
    "# 数值与 data/visual_diff_spec.json 逐项对应，改一处要改两处。\n"
    "# 已退役：3D albedo tint、metallic 乘数（v2 串扰玩家层 7940 px）、\n"
    "# 灯能量缩放（v1 跨 SubViewport 串光）；负结果见 data/v1-failed/\n"
    "# 与 data/v2-failed/。shader 字符串是 tint 的唯一真相来源。\n"
    + SHADER_LINE
    + "const FOE_DRAW_SCALE_X := 1.22\n"
    "const FOE_DRAW_SCALE_Y := 0.94\n"
)

EDITS = [
    ("head", OLD_HEAD, NEW_HEAD),
    ("collect_comment",
     "\t# I 路线：收集基础材质，运行时 tint 只在副本上做。\n",
     "\t# I 路线：收集 mesh / 灯初值，仅供 visual_state() 读回诊断；\n"
     "\t# v3 不复制、不改写任何 3D 材质。\n"),
    ("state_comment",
     "# I 路线：foe 专属视觉开关与可还原的原始资源表。\n",
     "# I 路线：foe 专属视觉开关。_mesh_rows/_light_rows 仅供诊断读回；\n"
     "# _foe_materials 恒空（v3 断言没有 3D 材质副本）；_foe_canvas_mat\n"
     "# 是本层本地的 2D 合成材质，物理上不会串到玩家层。\n"),
    ("setter_comment",
     "## I 路线：可反复切换。true = 压暗偏锈红 + 降金属度 + 降灯能量 +\n"
     "## 加宽压矮轮廓；false = 逐项还原到 H 路线原样（玩家层恒定 false）。\n",
     "## I 路线：可反复切换。true = 本层挂 canvas_item 调色 shader +\n"
     "## 加宽压矮绘制尺寸；false = 清 material、尺寸回 1.0，逐项还原到\n"
     "## H 路线原样（玩家层恒定 false，从不被本函数触碰）。\n"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def baseline_map() -> dict[str, str]:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {r["rel"]: r["sha256"] for r in payload["files"]}


def game_rels() -> set[str]:
    out = set()
    for p in GAME.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(GAME)
        if any(part in (".godot", "__pycache__") for part in rel.parts):
            continue
        out.add(str(rel).replace("\\", "/"))
    return out


def main() -> int:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    base = baseline_map()
    data = LAYER.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    work = data.replace(eol, b"\n")
    applied = []
    for tag, old, new in EDITS:
        ob, nb = old.encode("utf-8"), new.encode("utf-8")
        count = work.count(ob)
        if count == 1:
            work = work.replace(ob, nb, 1)
            applied.append(tag)
        else:
            assert count == 0, f"anchor {tag} duplicated: {count}"
    if applied:
        LAYER.write_bytes(work.replace(b"\n", eol))
    src = LAYER.read_text(encoding="utf-8")

    tint = spec["canvas_tint"]
    tint_lit = "vec3(%s)" % ", ".join(f"{v:.2f}" for v in tint)
    sx = spec["silhouette"]["draw_scale_x"]
    sy = spec["silhouette"]["draw_scale_y"]
    now = game_rels()
    changed = sorted(r for r, h in base.items()
                     if r in now and sha(GAME / r) != h)
    missing = sorted(r for r in base if r not in now)
    extra = sorted(now - set(base))

    checks = {
        "spec_revision_is_2": spec.get("revision") == 2,
        "only_existing_file_changed": (changed == ["scripts/fighter_3d_layer.gd"]
                                       and not missing),
        "arena_matches_h_baseline": sha(ARENA) == base["scripts/arena.gd"],
        "fighter_matches_h_baseline": (
            sha(FIGHTER) == base["scripts/fighter.gd"]),
        "layer_differs_from_h_baseline": (
            sha(LAYER) != base["scripts/fighter_3d_layer.gd"]),
        # 按形状放行走探针脚本，以及 Godot 4.4+ 自动生成的 .gd.uid；
        # 不按文件名字面列白名单，避免下次新增探针又误报。
        "new_files_only_probe_scripts": all(
            r.startswith("tests/")
            and (r.endswith("_probe.gd")
                 or (r.endswith(".gd.uid") and r[:-4] in now))
            for r in extra) and len(extra) <= 12,
        "no_surface_override_calls": (
            "set_surface_override_material" not in src),
        "no_3d_material_duplicate": (
            "(base as StandardMaterial3D).duplicate()" not in src),
        "no_light_energy_write": (
            'l.light_energy = float(row["energy"])' not in src),
        "retired_constants_absent": all(
            name not in src
            for name in spec["material"]["retired_constants_absent"]),
        "canvas_shader_present": "shader_type canvas_item" in src,
        "canvas_material_set": "material = _foe_canvas_mat" in src,
        "canvas_material_cleared": "material = null" in src,
        "shader_tint_matches_spec": tint_lit in src,
        "draw_scale_x_matches_spec": (
            f"const FOE_DRAW_SCALE_X := {sx:.2f}" in src),
        "draw_scale_y_matches_spec": (
            f"const FOE_DRAW_SCALE_Y := {sy:.2f}" in src),
        "player_draw_path_pixel_identity_shape": all(
            s in src for s in (
                "FOE_DRAW_SCALE_X if foe_visual else 1.0",
                "FOE_DRAW_SCALE_Y if foe_visual else 1.0")),
        # 源码里 OS.get_environment( 与字符串是跨行写法，不能按连续
        # 字面量扫；只钉「名字存在 + none 判别 + 仅 foe 分支」三个形状。
        "off_switch_present": (
            '"CARD_BOXER_FOE_VISUAL"' in src and '!= "none"' in src),
        "off_switch_scoped_to_foe": (
            'if p_role == "foe" and OS.get_environment(' in src),
        "collect_meshes_kept_for_diagnostics": (
            "func _collect_meshes" in src),
        "G_shape_preserved": all(s in src for s in [
            "const DEFAULT_SIDE_YAW := 55.0",
            "drv.apply_frame(c, f)", "_apply_stance_bias()"]),
    }
    report = {
        "applied": applied or "SKIPPED_ALREADY_APPLIED",
        "baseline_files": len(base), "changed_vs_baseline": changed,
        "missing_vs_baseline": missing, "new_files": extra,
        "spec_revision": spec.get("revision"),
        "draw_scale_x": sx, "canvas_tint_literal": tint_lit,
        "sha256_after": {
            "scripts/fighter_3d_layer.gd": sha(LAYER),
            "scripts/arena.gd": sha(ARENA),
            "scripts/fighter.gd": sha(FIGHTER)},
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("PATCH_FINAL", report["applied"])
    print("CHANGED", changed, "MISSING", missing, "NEW", extra)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PATCH_VISUAL_FINAL_I_OK" if report["ok"]
          else "PATCH_VISUAL_FINAL_I_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
