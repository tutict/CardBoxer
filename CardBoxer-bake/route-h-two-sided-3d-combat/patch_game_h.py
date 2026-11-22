"""H 路线 P2：把双侧 3D 接线写进可运行游戏工程（二进制精确替换）。

纪律：
  · 每个 needle 必须在目标文件里**恰好命中 1 次**，否则整脚本不改任何文件；
  · 二进制读写，不碰换行口径（本仓工作树 CRLF/LF 混合）；
  · 改前 sha256 与 orig/pre-3d-foe 备份逐项核对；
  · 改后断言 G 路线的 A 组源码形状仍在（双轨机制没被破坏）。

只改 scripts/arena.gd 与 scripts/fighter_3d_layer.gd；
scripts/fighter.gd 一字不动（draw_3d_override 已经存在，只需给 enemy 也置 true）。
用法：python patch_game_h.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
BACKUP = HERE / "orig" / "pre-3d-foe"
OUT = HERE / "data" / "patch_game_h.json"

ARENA = GAME / "scripts" / "arena.gd"
LAYER = GAME / "scripts" / "fighter_3d_layer.gd"
FIGHTER = GAME / "scripts" / "fighter.gd"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(s: str) -> bytes:
    return s.replace("\r\n", "\n").encode("utf-8")


PATCHES: list[tuple[Path, str, str, str]] = [
    (LAYER, "foe_glb_const",
     'const RigDriverScript := preload("res://scripts/rig_driver.gd")\n'
     'const GLB_PATH := "res://assets/3d/player-rigged.glb"\n',
     'const RigDriverScript := preload("res://scripts/rig_driver.gd")\n'
     'const GLB_PATH := "res://assets/3d/player-rigged.glb"\n'
     '# H 路线：对手怪是另一份带 skin 的 GLB（13 骨同名、rest 更矮更宽）。\n'
     'const FOE_GLB_PATH := "res://assets/3d/foe-rigged.glb"\n'),

    (LAYER, "foe_yaw_const",
     'const DEFAULT_SIDE_YAW := 55.0\n'
     'const DEFAULT_SIDE_FLIP := false\n',
     'const DEFAULT_SIDE_YAW := 55.0\n'
     'const DEFAULT_SIDE_FLIP := false\n'
     '# H 路线：对手在画面右侧，脸要朝左；相机放到角色右前方（yaw 取负）。\n'
     '# 不用 -90°：与玩家同理，零厚度壳会退化成线且出拳幅度被压成 0。\n'
     'const DEFAULT_FOE_YAW := -55.0\n'),

    (LAYER, "role_vars",
     'var drv = null\n'
     'var motion: Dictionary = {}\n',
     'var drv = null\n'
     'var motion: Dictionary = {}\n'
     '# H 路线：同一个层类服务两个角色；默认仍是 G 的玩家形态。\n'
     'var glb_path := GLB_PATH\n'
     'var role_id := "player"\n'),

    (LAYER, "configure_hook",
     '## 探针/运行时改视角；不动骨架，只摆相机 + 决定贴图是否镜像。\n'
     'func set_view(p_yaw_deg: float, p_flip: bool) -> void:\n',
     '## H 路线：在 setup() 之前指定角色资产与朝向。\n'
     '## 不传 = G 路线原样（玩家 / player-rigged.glb / +55° / 不翻）。\n'
     'func configure(p_role: String, p_glb: String, p_yaw: float,\n'
     '\t\tp_flip: bool) -> void:\n'
     '\trole_id = p_role\n'
     '\tglb_path = p_glb\n'
     '\tview_yaw_deg = p_yaw\n'
     '\tview_flip = p_flip\n'
     '\n'
     '\n'
     '## 探针/运行时改视角；不动骨架，只摆相机 + 决定贴图是否镜像。\n'
     'func set_view(p_yaw_deg: float, p_flip: bool) -> void:\n'),

    (LAYER, "probe_env_player_only",
     '\t# 环境变量只用于探针扫角度；默认走源码常量，双轨开关默认关不受影响。\n'
     '\tvar yaw_env := OS.get_environment("CARD_BOXER_3D_YAW")\n'
     '\tif yaw_env != "":\n'
     '\t\tview_yaw_deg = float(yaw_env)\n'
     '\tvar flip_env := OS.get_environment("CARD_BOXER_3D_FLIP")\n'
     '\tif flip_env != "":\n'
     '\t\tview_flip = flip_env != "0"\n',
     '\t# 环境变量只用于玩家侧探针扫角度；对手侧由 configure() 定死朝向，\n'
     '\t# 避免玩家探针的环境变量把对手一起转了。\n'
     '\tif role_id == "player":\n'
     '\t\tvar yaw_env := OS.get_environment("CARD_BOXER_3D_YAW")\n'
     '\t\tif yaw_env != "":\n'
     '\t\t\tview_yaw_deg = float(yaw_env)\n'
     '\t\tvar flip_env := OS.get_environment("CARD_BOXER_3D_FLIP")\n'
     '\t\tif flip_env != "":\n'
     '\t\t\tview_flip = flip_env != "0"\n'),

    (LAYER, "load_glb_path",
     '\tvar res := load(GLB_PATH)\n',
     '\tvar res := load(glb_path)\n'),

    (ARENA, "foe_vars",
     'var use_3d := false\n'
     'var layer_3d = null\n'
     'var motion_3d: Dictionary = {}\n',
     'var use_3d := false\n'
     'var layer_3d = null\n'
     'var layer_3d_foe = null\n'
     'var motion_3d: Dictionary = {}\n'
     'var motion_3d_foe: Dictionary = {}\n'),

    (ARENA, "create_two_layers",
     '\tif use_3d:\n'
     '\t\tvar mf3 := FileAccess.open("res://data/motion_input.json", FileAccess.READ)\n'
     '\t\tif mf3 != null:\n'
     '\t\t\tvar parsed3: Variant = JSON.parse_string(mf3.get_as_text())\n'
     '\t\t\tmf3.close()\n'
     '\t\t\tif parsed3 is Dictionary:\n'
     '\t\t\t\tmotion_3d = parsed3\n'
     '\t\tif not motion_3d.is_empty():\n'
     '\t\t\tvar l3 := Fighter3DLayerScript.new()\n'
     '\t\t\tworld.add_child(l3)\n'
     '\t\t\tif l3.setup(motion_3d):\n'
     '\t\t\t\tlayer_3d = l3\n'
     '\t\t\t\tplayer.draw_3d_override = true\n'
     '\t\t\t\tprint("F3D_READY bones=%d cards=%d" % [\n'
     '\t\t\t\t\tl3.drv.bone_names.size(), motion_3d["cards"].size()])\n'
     '\t\t\telse:\n'
     '\t\t\t\tworld.remove_child(l3)\n'
     '\t\t\t\tl3.queue_free()\n',
     '\tif use_3d:\n'
     '\t\tvar mf3 := FileAccess.open("res://data/motion_input.json", FileAccess.READ)\n'
     '\t\tif mf3 != null:\n'
     '\t\t\tvar parsed3: Variant = JSON.parse_string(mf3.get_as_text())\n'
     '\t\t\tmf3.close()\n'
     '\t\t\tif parsed3 is Dictionary:\n'
     '\t\t\t\tmotion_3d = parsed3\n'
     '\t\t# H 路线：两套骨架 rest 不同，旋转中心 apose_points 必须各用各的。\n'
     '\t\tvar mf3f := FileAccess.open("res://data/motion_input_foe.json", FileAccess.READ)\n'
     '\t\tif mf3f != null:\n'
     '\t\t\tvar parsed3f: Variant = JSON.parse_string(mf3f.get_as_text())\n'
     '\t\t\tmf3f.close()\n'
     '\t\t\tif parsed3f is Dictionary:\n'
     '\t\t\t\tmotion_3d_foe = parsed3f\n'
     '\t\tif not motion_3d.is_empty() and not motion_3d_foe.is_empty():\n'
     '\t\t\tvar l3 := Fighter3DLayerScript.new()\n'
     '\t\t\tworld.add_child(l3)\n'
     '\t\t\tif l3.setup(motion_3d):\n'
     '\t\t\t\tlayer_3d = l3\n'
     '\t\t\t\tplayer.draw_3d_override = true\n'
     '\t\t\t\tprint("F3D_READY bones=%d cards=%d" % [\n'
     '\t\t\t\t\tl3.drv.bone_names.size(), motion_3d["cards"].size()])\n'
     '\t\t\telse:\n'
     '\t\t\t\tworld.remove_child(l3)\n'
     '\t\t\t\tl3.queue_free()\n'
     '\t\t\tvar lf := Fighter3DLayerScript.new()\n'
     '\t\t\tlf.configure("foe", Fighter3DLayerScript.FOE_GLB_PATH,\n'
     '\t\t\t\t\tFighter3DLayerScript.DEFAULT_FOE_YAW, false)\n'
     '\t\t\tworld.add_child(lf)\n'
     '\t\t\tif lf.setup(motion_3d_foe):\n'
     '\t\t\t\tlayer_3d_foe = lf\n'
     '\t\t\t\tenemy.draw_3d_override = true\n'
     '\t\t\t\tprint("F3D_FOE_READY bones=%d" % [\n'
     '\t\t\t\t\tlf.drv.bone_names.size()])\n'
     '\t\t\telse:\n'
     '\t\t\t\tworld.remove_child(lf)\n'
     '\t\t\t\tlf.queue_free()\n'),

    (ARENA, "sync_two_layers",
     'func _sync_3d_layer() -> void:\n'
     '\tif layer_3d == null:\n'
     '\t\treturn\n'
     '\tlayer_3d.position = player.position + player.visual_shift\n'
     '\tvar card := "stance"\n'
     '\tvar frame := 0\n'
     '\t# 只有玩家赢下本回、节奏时钟激活、且确实有赢家动作时播攻击；\n'
     '\t# 输家 / 平局 / 亮牌阶段一律 stance（73 帧表里没有受击轨道）。\n'
     '\tif tk_rhythm_winner == "player" and tk_rhythm_t >= 0.0 \\\n'
     '\t\t\tand tk_motion_id != "" and tk_rhythm_t <= Rhythm.ATTACK_S:\n'
     '\t\tcard = tk_motion_id\n'
     '\t\tvar n: int = int(motion_3d["cards"][card]["frames"])\n'
     '\t\tframe = clampi(int(tk_rhythm_t / Rhythm.ATTACK_S * float(n - 1)), 0, n - 1)\n'
     '\tlayer_3d.apply(card, frame)\n',
     'func _sync_3d_layer() -> void:\n'
     '\t# 默认关时立刻返回：节奏时钟仍在跑，但 motion_3d 是空的，\n'
     '\t# 继续往下算帧数会撞空字典。G 路线的早退语义必须保留。\n'
     '\tif (layer_3d == null and layer_3d_foe == null) or motion_3d.is_empty():\n'
     '\t\treturn\n'
     '\tvar card := "stance"\n'
     '\tvar frame := 0\n'
     '\tvar foe_card := "stance"\n'
     '\tvar foe_frame := 0\n'
     '\t# 只有赢下本回的一方播攻击；输家 / 平局 / 亮牌阶段一律 stance\n'
     '\t# （73 帧表里没有受击轨道，硬凑会变成自造动作）。\n'
     '\tif tk_rhythm_t >= 0.0 and tk_motion_id != "" \\\n'
     '\t\t\tand tk_rhythm_t <= Rhythm.ATTACK_S:\n'
     '\t\tvar n: int = int(motion_3d["cards"][tk_motion_id]["frames"])\n'
     '\t\tvar f := clampi(int(tk_rhythm_t / Rhythm.ATTACK_S * float(n - 1)), 0, n - 1)\n'
     '\t\tif tk_rhythm_winner == "player":\n'
     '\t\t\tcard = tk_motion_id\n'
     '\t\t\tframe = f\n'
     '\t\telif tk_rhythm_winner == "enemy":\n'
     '\t\t\tfoe_card = tk_motion_id\n'
     '\t\t\tfoe_frame = f\n'
     '\tif layer_3d != null:\n'
     '\t\tlayer_3d.position = player.position + player.visual_shift\n'
     '\t\tlayer_3d.apply(card, frame)\n'
     '\tif layer_3d_foe != null:\n'
     '\t\tlayer_3d_foe.position = enemy.position + enemy.visual_shift\n'
     '\t\tlayer_3d_foe.apply(foe_card, foe_frame)\n'),
]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    before = {}
    for p in (ARENA, LAYER, FIGHTER):
        rel = str(p.relative_to(GAME)).replace("\\", "/")
        q = BACKUP / rel
        before[rel] = {"sha256": sha(p),
                       "backup_sha256": sha(q) if q.is_file() else None,
                       "backup_matches": q.is_file() and sha(q) == sha(p)}
    assert all(v["backup_matches"] for v in before.values()), before

    # 先全文预检：所有 needle 都必须在当前盘上恰好命中 1 次。
    resolved = []
    for path, name, old, new in PATCHES:
        data = path.read_bytes()
        o_lf, n_lf = norm(old), norm(new)
        hits = []
        for eol in (b"\n", b"\r\n"):
            o = o_lf.replace(b"\n", eol)
            if data.count(o) == 1:
                hits.append((eol, o, n_lf.replace(b"\n", eol)))
        assert len(hits) >= 1, f"anchor not found: {name}"
        resolved.append((path, name, hits[0]))
    applied = []
    for path, name, (eol, o, n) in resolved:
        data = path.read_bytes()
        assert data.count(o) == 1, name
        path.write_bytes(data.replace(o, n, 1))
        applied.append({"file": path.name, "patch": name,
                        "eol": "CRLF" if eol == b"\r\n" else "LF"})

    layer_src = LAYER.read_text(encoding="utf-8")
    arena_src = ARENA.read_text(encoding="utf-8")
    checks = {
        "fighter_gd_untouched": sha(FIGHTER) == before[
            "scripts/fighter.gd"]["sha256"],
        "switch_default_off": (
            'use_3d = OS.get_environment("CARD_BOXER_3D") != ""' in arena_src),
        "override_default_false": (
            "var draw_3d_override := false" in FIGHTER.read_text(
                encoding="utf-8")),
        "sync_hook_count": arena_src.count("_sync_3d_layer()") >= 2,
        "G_shape_side_yaw_55": "const DEFAULT_SIDE_YAW := 55.0" in layer_src,
        "G_shape_side_flip_false": (
            "const DEFAULT_SIDE_FLIP := false" in layer_src),
        "G_shape_stance_bias": (
            "var stance_bias_deg: Dictionary = DEFAULT_STANCE_BIAS.duplicate()"
            in layer_src),
        "G_shape_apply_frame_before_bias": (
            "drv.apply_frame(c, f)" in layer_src
            and "_apply_stance_bias()" in layer_src),
        "G_shape_bone_pose_rotation": (
            "drv.skel.set_bone_pose_rotation(i, cur * q)" in layer_src),
        "H_foe_yaw": "const DEFAULT_FOE_YAW := -55.0" in layer_src,
        "H_foe_glb": 'FOE_GLB_PATH := "res://assets/3d/foe-rigged.glb"'
                     in layer_src,
        "H_configure": "func configure(" in layer_src,
        "H_two_layers": ("layer_3d_foe" in arena_src
                         and "motion_3d_foe" in arena_src),
        "H_two_motions": ('res://data/motion_input_foe.json' in arena_src
                          and 'res://data/motion_input.json' in arena_src),
        "H_arena_uses_layer_constants": (
            "Fighter3DLayerScript.FOE_GLB_PATH" in arena_src
            and "Fighter3DLayerScript.DEFAULT_FOE_YAW" in arena_src),
        "H_sync_early_return_preserved": (
            "or motion_3d.is_empty():" in arena_src),
        "H_enemy_override": "enemy.draw_3d_override = true" in arena_src,
        "H_enemy_winner_branch": 'tk_rhythm_winner == "enemy"' in arena_src,
        "H_layer_loads_glb_path": "var res := load(glb_path)" in layer_src,
    }
    after = {str(p.relative_to(GAME)).replace("\\", "/"): sha(p)
             for p in (ARENA, LAYER, FIGHTER)}
    report = {"before": before, "after": after, "applied": applied,
              "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for a in applied:
        print("PATCH", a["file"], a["patch"], a["eol"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PATCH_GAME_H_OK" if report["ok"] else "PATCH_GAME_H_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
