"""回合制改造的字节级补丁（P0 第一步）：card_data.gd 加 rank、fighter.gd 加纯表演入口。

纪律：每个锚点必须恰好命中 1 次，否则立刻报错；纯 LF 文件，不做换行归一化；
改完打印每处命中与最终 sha256，便于读盘核对。
"""

import hashlib
from pathlib import Path

ROOT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\scripts")

RANKS = {
    "jab": 1,
    "cross": 2,
    "uppercut": 3,
    "sweep": 4,
    "wave": 5,
    "throw": 6,
    "rush": 7,
    "backstep": 8,
    "guard": 9,
    # 守御/蓄力牌复用中间点数，让三同/三连在 5 张手牌里真的凑得出来。
    "sidestep": 2,
    "focus": 3,
    "recover": 4,
}

FIGHTER_PATCHES = [
    (
        "var _has_hit := false\nvar _combo_bonus := 0\n",
        "var _has_hit := false\n"
        "## 回合制合战：只播招式动画，不跑实时命中结算（伤害由 arena 统一结算）。\n"
        "var _visual_only := false\n"
        "var _combo_bonus := 0\n",
        "新增 _visual_only 变量",
    ),
    (
        "\t_has_hit = false\n\t_combo_bonus = 0\n",
        "\t_has_hit = false\n\t_visual_only = false\n\t_combo_bonus = 0\n",
        "reset_for_round 清标志",
    ),
    (
        "func freeze() -> void:\n\t_action = {}\n\t_action_phase = \"\"\n\t_clear_slide()\n",
        "func freeze() -> void:\n\t_action = {}\n\t_action_phase = \"\"\n"
        "\t_visual_only = false\n\t_clear_slide()\n",
        "freeze 清标志",
    ),
    (
        "func _on_active_start() -> void:\n\tvar card := _action\n",
        "func _on_active_start() -> void:\n\tif _visual_only:\n\t\treturn\n\tvar card := _action\n",
        "纯表演跳过位移",
    ),
    (
        "func _resolve_active_hit() -> void:\n\tvar card := _action\n",
        "func _resolve_active_hit() -> void:\n\tif _visual_only:\n\t\treturn\n\tvar card := _action\n",
        "纯表演跳过实时命中",
    ),
    (
        "func _end_action() -> void:\n\t_action = {}\n\t_action_phase = \"\"\n\t_phase_time = 0.0\n",
        "func _end_action() -> void:\n\t_action = {}\n\t_action_phase = \"\"\n"
        "\t_phase_time = 0.0\n\t_visual_only = false\n",
        "动作结束清标志",
    ),
    (
        "\tif card.get(\"kind\", \"\") == Defs.KIND_GUARD:\n"
        "\t\tif id == \"guard\":\n\t\t\t_guard_hold = 0.55\n"
        "\t\telif id == \"sidestep\":\n\t\t\t_sidestep_time = 0.18\n"
        "\treturn true\n\n\nfunc _resolve_combo(current_id: String, current_cost: int) -> void:\n",
        "\tif card.get(\"kind\", \"\") == Defs.KIND_GUARD:\n"
        "\t\tif id == \"guard\":\n\t\t\t_guard_hold = 0.55\n"
        "\t\telif id == \"sidestep\":\n\t\t\t_sidestep_time = 0.18\n"
        "\treturn true\n\n\n"
        "## 回合制合战专用：只把招式动画放出来，不做任何实时结算。\n"
        "## play_card() 那条链（扣气 / 连招 / 前摇命中判定 / 位移）一步都不走，\n"
        "## 伤害由 arena 在比牌后统一调 apply_hit()，避免双重结算。\n"
        "func perform_visual(id: String) -> void:\n"
        "\tvar card: Dictionary = Defs.card(id)\n"
        "\tif card.is_empty():\n\t\treturn\n"
        "\t_visual_only = true\n"
        "\t_combo_bonus = 0\n"
        "\t_combo_name = \"\"\n"
        "\t_combo_extra = \"\"\n"
        "\t_is_super = false\n"
        "\t_guard_hold = 0.0\n"
        "\t_sidestep_time = 0.0\n"
        "\t_clear_slide()\n"
        "\t_action = card.duplicate()\n"
        "\t_action[\"id\"] = id\n"
        "\t_action_phase = \"windup\"\n"
        "\t_phase_time = 0.0\n"
        "\t_has_hit = false\n"
        "\tstate = State.ACTION\n"
        "\tstate_time = 0.0\n"
        "\tcard_played.emit(id, is_player)\n\n\n"
        "func _resolve_combo(current_id: String, current_cost: int) -> void:\n",
        "新增 perform_visual()",
    ),
]


def patch_card_data() -> None:
    path = ROOT / "card_data.gd"
    text = path.read_bytes().decode("utf-8")
    assert "\r" not in text, "card_data.gd 不是纯 LF"
    assert '"rank"' not in text, "rank 已经加过了，别重复跑"

    old_header = "## 一套牌。字段单位：时间用帧（60fps），距离用像素，气用整点。\n"
    new_header = (
        old_header
        + "## rank 是太阁 IV 合战模式的数字点数（1..9），与实时模式的伤害/气耗无关；\n"
        + "## 回合制只按 rank 比三同/三连/散牌，牌名与动作只作表现。\n"
    )
    assert text.count(old_header) == 1
    text = text.replace(old_header, new_header, 1)
    print("OK   卡表注释补 rank 说明")

    for cid, rank in RANKS.items():
        needle = '\t"%s": {\n' % cid
        assert text.count(needle) == 1, (cid, text.count(needle))
        text = text.replace(needle, needle + '\t\t"rank": %d,\n' % rank, 1)
        print(f"OK   {cid:<10} rank={rank}")

    path.write_bytes(text.encode("utf-8"))
    print(f"card_data.gd sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")


def patch_fighter() -> None:
    path = ROOT / "fighter.gd"
    text = path.read_bytes().decode("utf-8")
    assert "\r" not in text, "fighter.gd 不是纯 LF"
    assert "perform_visual" not in text, "perform_visual 已经加过了，别重复跑"

    for old, new, label in FIGHTER_PATCHES:
        n = text.count(old)
        assert n == 1, f"{label}: 锚点命中 {n} 次（应为 1）"
        text = text.replace(old, new, 1)
        print(f"OK   {label}")

    path.write_bytes(text.encode("utf-8"))
    print(f"fighter.gd  sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    patch_card_data()
    patch_fighter()
    print("PATCH_OK")
