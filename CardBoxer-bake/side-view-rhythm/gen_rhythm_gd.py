"""Generate scripts/battle_rhythm.gd from battle_rhythm_spec.json.

Single source of truth: the JSON. The generated GDScript is pure constants +
pure static functions (no nodes, no state), so it can be unit-checked and
mutated without touching the game's state machine.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
SPEC = HERE / "battle_rhythm_spec.json"
OUT = GAME / "scripts" / "battle_rhythm.gd"


def f(v) -> str:
    s = repr(float(v))
    return s if "." in s else s + ".0"


def build() -> str:
    d = json.loads(SPEC.read_text(encoding="utf-8"))
    t, c, r = d["timing"], d["constants"], d["canvas_remap"]
    L: list[str] = []
    add = L.append
    add("extends RefCounted")
    add("## 由 side-view-rhythm/gen_rhythm_gd.py 从 battle_rhythm_spec.json 生成，勿手改。")
    add("## KOF 式命中节奏：赢家三角脉冲前压、输家击退后仰、星芒火花、短斜速度线、HIT! 停顿。")
    add("## 纯常量 + 纯函数，无节点无状态；数值真相来源只有那份 JSON。")
    add("## 视觉位移由 arena.gd 写进 fighter.visual_shift / visual_tilt，")
    add("## 只在 _draw() 的 draw_set_transform 内生效，不碰 position 与任何判定。")
    add("")
    add('const SPEC_VERSION := "%s"' % d["spec_version"])
    for key, gd in [
        ("frame_s", "FRAME_S"), ("attack_s", "ATTACK_S"),
        ("settle_s", "SETTLE_S"), ("recover_s", "RECOVER_S"),
        ("total_s", "TOTAL_S"), ("hit_at_s", "HIT_AT_S"),
        ("hitstop_s", "HITSTOP_S"),
    ]:
        add("const %s := %s" % (gd, f(t[key])))
    add("")
    for key in c:
        if key == "hitstop_label":
            continue
        add("const %s := %s" % (key.upper(), f(c[key])))
    add('const HITSTOP_LABEL := "%s"' % c["hitstop_label"])
    add("")
    add("# 画布重映射（游戏 1280x720；离线 880x500 的绝对坐标不共用）")
    for key in ["game_player_x", "game_foe_x", "game_ground_y",
                "game_spark_y_offset", "game_speed_line_mid_x",
                "game_speed_line_y0", "game_hit_label_size"]:
        add("const %s := %s" % (key.upper(), f(r[key])))
    add("const GAME_HIT_LABEL_POS := Vector2(%s, %s)" % (
        f(r["game_hit_label_pos"][0]), f(r["game_hit_label_pos"][1])))
    add("")
    add("static func pulse(t: float) -> float:")
    add("\treturn maxf(0.0, 1.0 - absf(t - PRESS_CENTER) / PRESS_HALF_WIDTH)")
    add("")
    add("static func press_px(t: float) -> float:")
    add("\treturn PRESS_PX * pulse(t)")
    add("")
    add("static func knock_px(t: float) -> float:")
    add("\treturn KNOCK_PX * maxf(0.0, 1.0 - t * KNOCK_DECAY)")
    add("")
    add("static func tilt_rad(t: float) -> float:")
    add("\treturn deg_to_rad(TILT_DEG) * maxf(0.0, 1.0 - t * TILT_DECAY)")
    add("")
    add("static func spark_alpha01(t: float) -> float:")
    add("\treturn (SPARK_ALPHA / 255.0) * maxf(0.0, 1.0 - t * SPARK_ALPHA_DECAY)")
    add("")
    add("static func speed_alpha01(t: float) -> float:")
    add("\treturn (SPEED_LINE_ALPHA / 255.0) * maxf(0.0, 1.0 - t * SPEED_LINE_DECAY)")
    add("")
    add("static func speed_len(t: float, k: int) -> float:")
    add("\treturn SPEED_LINE_LEN_BASE + SPEED_LINE_LEN_AMP * sin(PI * minf(1.0, t * SPEED_LINE_DECAY + float(k) * SPEED_LINE_PHASE_STEP))")
    add("")
    add("static func phase_at(elapsed: float) -> String:")
    add('\tif elapsed < 0.0: return "off"')
    add('\tif elapsed <= ATTACK_S: return "attack"')
    add('\tif elapsed <= ATTACK_S + SETTLE_S: return "settle"')
    add('\tif elapsed <= TOTAL_S: return "recover"')
    add('\treturn "off"')
    add("")
    add("## attack 窗内 t∈[0,1]；settle 窗内淡出；recover 后归零。")
    add("static func fade_at(elapsed: float) -> float:")
    add('\tif elapsed < 0.0 or elapsed > TOTAL_S: return 0.0')
    add("\tif elapsed <= ATTACK_S: return 1.0")
    add("\treturn clampf(1.0 - (elapsed - ATTACK_S) / SETTLE_S, 0.0, 1.0)")
    add("")
    add("static func attack_t(elapsed: float) -> float:")
    add("\treturn clampf(elapsed / ATTACK_S, 0.0, 1.0)")
    add("")
    add("## 命中帧起的 spark 尾窗（离线 f <= HIT_FRAME + 3）。")
    add("static func spark_active(elapsed: float) -> bool:")
    add("\treturn elapsed >= HIT_AT_S and elapsed <= HIT_AT_S + FRAME_S * SPARK_TAIL_FRAMES")
    add("")
    add("static func speed_active(elapsed: float) -> bool:")
    add("\treturn elapsed >= 0.0 and attack_t(elapsed) <= SPEED_LINE_CUTOFF")
    add("")
    add("static func hit_label_active(elapsed: float) -> bool:")
    add("\treturn elapsed >= HIT_AT_S and elapsed <= HIT_AT_S + HITSTOP_S")
    return "\n".join(L) + "\n"


def main() -> int:
    a = build()
    OUT.write_bytes(a.encode("utf-8"))
    b = OUT.read_bytes().decode("utf-8")
    ok = a == b
    print("GEN %s bytes=%d stable=%s" % ("OK" if ok else "FAILED", len(a.encode("utf-8")), ok))
    print("GEN_RHYTHM_OK" if ok else "GEN_RHYTHM_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
