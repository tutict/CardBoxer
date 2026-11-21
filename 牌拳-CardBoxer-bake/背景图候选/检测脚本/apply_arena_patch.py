"""把太阁 IV 回合制状态机接进 arena.gd —— 带锚点断言的字节补丁。

原则：原实时格斗代码一行不删，只在入口分流；把 BATTLE_MODE 改回
"realtime" 就是改造前的完整玩法。每个锚点必须恰好命中 1 次。
"""

import hashlib
import re
from pathlib import Path

ARENA = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\scripts\arena.gd")
SNIPPET = Path(
    r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\背景图候选\检测脚本"
    r"\taikou_battle_snippet.txt"
)

PATCHES = [
    (
        "## 一场对局：三局两胜，每回合 60 秒。玩家与对手各有 5 张手牌，出牌即出招；\n"
        "## 牌序命中连招表就有加成，三张特定牌 + 3 点气触发大招。\n",
        "## 一场对局：三局两胜，双方各有 5 张手牌。\n"
        "## 玩法骨架由 BATTLE_MODE 决定：\n"
        "##   \"taikou\"（默认）= 太阁 IV 合战，回合制同时亮 3 张比牌型；\n"
        "##   \"realtime\"      = 原实时格斗，出牌即出招，按牌序结算连招与大招。\n",
        "顶部注释说明两种骨架",
    ),
    (
        'const BackdropTexture = preload("res://background/arena.png")\n\n'
        "const HAND_SIZE := 5\n",
        'const BackdropTexture = preload("res://background/arena.png")\n'
        'const Rules = preload("res://scripts/taikou_rules.gd")\n'
        'const TaikouAI = preload("res://scripts/taikou_ai.gd")\n\n'
        '## 玩法骨架："taikou" = 太阁 IV 回合制比牌（默认）；"realtime" = 原实时格斗兜底。\n'
        "## 改成 realtime 即可完整回到改造前的玩法，不需要回滚任何代码。\n"
        'const BATTLE_MODE := "taikou"\n'
        "const TK_PLAY := 3\n"
        "const TK_DISCARD_MAX := 3\n"
        "const TK_MAX_TURNS := 12\n\n"
        "const HAND_SIZE := 5\n",
        "preload 与回合制常量",
    ),
    (
        "# 演示模式：把玩家侧也交给 AI，用于自动跑完整局（只看流程，不算玩法）。\n"
        "var demo_ai = null\n",
        "# 演示模式：把玩家侧也交给 AI，用于自动跑完整局（只看流程，不算玩法）。\n"
        "var demo_ai = null\n\n"
        "## 太阁 IV 合战（回合制）状态。\n"
        "var battle_mode: String = BATTLE_MODE\n"
        'var tk_phase := "discard"        # discard / select / reveal / resolve\n'
        "var tk_turn := 1\n"
        "var tk_phase_time := 0.0\n"
        "var tk_marks: Array = []          # 当前阶段勾选的手牌下标\n"
        "var tk_player_reveal: Array = []  # 亮出的 3 个 rank\n"
        "var tk_enemy_reveal: Array = []\n"
        "var tk_player_ids: Array = []     # 亮出的牌 id，只用于播动画\n"
        "var tk_enemy_ids: Array = []\n"
        "var tk_player_result: Dictionary = {}\n"
        "var tk_enemy_result: Dictionary = {}\n"
        'var tk_winner := ""\n'
        "var tk_damage := 0\n"
        "var tk_bot := false               # CARD_BOXER_TAIKOU_BOT：无输入自动对战，仅供验收\n",
        "回合制状态变量",
    ),
    (
        '\tif OS.get_environment("CARD_BOXER_BOT") != "":\n'
        "\t\tdemo_ai = AIScript.new(player, 3)\n"
        "\t_start_match()\n",
        '\tif OS.get_environment("CARD_BOXER_BOT") != "":\n'
        "\t\tdemo_ai = AIScript.new(player, 3)\n"
        '\ttk_bot = OS.get_environment("CARD_BOXER_TAIKOU_BOT") != ""\n'
        "\t_start_match()\n",
        "读自动对战开关",
    ),
    (
        '\t_banner("第 %d 回合" % round_index, "1-5 出牌 · A/D 移动", Color(0.96, 0.90, 0.74), 1.0)\n',
        '\tif battle_mode == "taikou":\n'
        "\t\t_reset_taikou_turn(true)\n"
        "\telse:\n"
        '\t\t_banner("第 %d 回合" % round_index, "1-5 出牌 · A/D 移动", Color(0.96, 0.90, 0.74), 1.0)\n',
        "开局进入弃牌阶段",
    ),
    (
        '\t\t_banner(_intro_label, "" if step > 0 else "1-5 出牌 · A/D 移动", color, 0.8)\n',
        '\t\tvar intro_hint := "1-5 选牌 · 空格确认" if battle_mode == "taikou" else "1-5 出牌 · A/D 移动"\n'
        '\t\t_banner(_intro_label, "" if step > 0 else intro_hint, color, 0.8)\n',
        "开场提示按模式切换",
    ),
    (
        "func _tick_fight(dt: float) -> void:\n"
        "\tround_time_left = maxf(0.0, round_time_left - dt)\n",
        "func _tick_fight(dt: float) -> void:\n"
        '\tif battle_mode == "taikou":\n'
        "\t\t_tick_taikou(dt)\n"
        "\t\treturn\n"
        "\tround_time_left = maxf(0.0, round_time_left - dt)\n",
        "每帧分流到回合制",
    ),
    (
        "\tvar key: int = (event as InputEventKey).keycode\n"
        "\tmatch key:\n"
        "\t\tKEY_1, KEY_2, KEY_3, KEY_4, KEY_5:\n"
        "\t\t\t_try_play(key - KEY_1)\n"
        "\t\tKEY_R:\n"
        "\t\t\t_start_match()\n"
        "\t\tKEY_SPACE:\n"
        "\t\t\tpaused = not paused\n",
        "\tvar key: int = (event as InputEventKey).keycode\n"
        '\tif battle_mode == "taikou" and round_phase == "fight":\n'
        "\t\tmatch key:\n"
        "\t\t\tKEY_1, KEY_2, KEY_3, KEY_4, KEY_5:\n"
        "\t\t\t\tif not tk_bot:\n"
        "\t\t\t\t\t_taikou_toggle(key - KEY_1)\n"
        "\t\t\tKEY_SPACE, KEY_ENTER:\n"
        "\t\t\t\tif not tk_bot:\n"
        "\t\t\t\t\t_taikou_confirm()\n"
        "\t\t\tKEY_R:\n"
        "\t\t\t\t_start_match()\n"
        "\t\t\tKEY_P:\n"
        "\t\t\t\tpaused = not paused\n"
        "\t\treturn\n"
        "\tmatch key:\n"
        "\t\tKEY_1, KEY_2, KEY_3, KEY_4, KEY_5:\n"
        "\t\t\t_try_play(key - KEY_1)\n"
        "\t\tKEY_R:\n"
        "\t\t\t_start_match()\n"
        "\t\tKEY_SPACE:\n"
        "\t\t\tpaused = not paused\n",
        "输入按模式分流",
    ),
]


def main() -> None:
    text = ARENA.read_bytes().decode("utf-8")
    assert "\r" not in text, "arena.gd 不是纯 LF"
    assert "_tick_taikou" not in text, "回合制状态机已经接过了，别重复跑"

    snippet = SNIPPET.read_bytes().decode("utf-8")
    assert "\r" not in snippet, "snippet 不是纯 LF"
    assert "\n\t" in snippet, "snippet 丢了 tab 缩进"
    assert snippet.count("func ") >= 9, "snippet 函数数量不对"

    for old, new, label in PATCHES:
        n = text.count(old)
        assert n == 1, f"{label}: 锚点命中 {n} 次（应为 1）"
        text = text.replace(old, new, 1)
        print(f"OK   {label}")

    # 把原「出牌」区块标题改成实时兜底标题，并在它前面插入整段回合制状态机。
    pattern = re.compile(r"\n# ── 出牌 [─]+\n")
    hits = list(pattern.finditer(text))
    assert len(hits) == 1, f"出牌区块标题命中 {len(hits)} 次"
    m = hits[0]
    replacement = "\n\n" + snippet + "\n# ── 实时格斗：出牌（realtime 兜底） " + "─" * 20 + "\n"
    text = text[: m.start()] + replacement + text[m.end() :]
    print("OK   插入回合制状态机（9 个函数）")

    ARENA.write_bytes(text.encode("utf-8"))
    print(f"arena.gd sha256={hashlib.sha256(ARENA.read_bytes()).hexdigest()}")
    print("ARENA_PATCH_OK")


if __name__ == "__main__":
    main()
