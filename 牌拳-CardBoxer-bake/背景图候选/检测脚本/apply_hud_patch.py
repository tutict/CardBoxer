"""HUD 接太阁 IV 合战界面 + project.godot 描述订正。

回合制下：卡面显示 rank、勾选态、双方亮牌区、轮数；实时模式一切保持原样。
锚点必须恰好命中 1 次。
"""

import hashlib
import re
from pathlib import Path

HUD = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\scripts\hud.gd")
PROJ = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\project.godot")
SNIPPET = Path(
    r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\背景图候选\检测脚本"
    r"\taikou_hud_snippet.txt"
)

PATCHES = [
    (
        "\t_draw_center()\n\t_draw_hand()\n\t_draw_banner()\n",
        "\t_draw_center()\n\t_draw_hand()\n\t_draw_taikou_reveal()\n\t_draw_banner()\n",
        "_draw 调用亮牌区",
    ),
    (
        '\t_draw_bar_v2(Vector2(44, 44), p.hp_ratio(), float(_hp_shown["p"]), false, p.display_name, true)\n'
        "\t_draw_meter(Vector2(44, 76), p.meter_ratio(), 5)\n"
        "\tdraw_string(\n"
        '\t\tfont, Vector2(44, 104), "气 %d/5" % int(p.meter), HORIZONTAL_ALIGNMENT_LEFT, -1, 13,\n'
        "\t\tColor(0.60, 0.72, 0.88)\n"
        "\t)\n",
        '\t_draw_bar_v2(Vector2(44, 44), p.hp_ratio(), float(_hp_shown["p"]), false, p.display_name, true)\n'
        '\tif arena.battle_mode == "taikou":\n'
        "\t\tdraw_string(\n"
        '\t\t\tfont, Vector2(44, 104), "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)],\n'
        "\t\t\tHORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(0.60, 0.72, 0.88)\n"
        "\t\t)\n"
        "\telse:\n"
        "\t\t_draw_meter(Vector2(44, 76), p.meter_ratio(), 5)\n"
        "\t\tdraw_string(\n"
        '\t\t\tfont, Vector2(44, 104), "气 %d/5" % int(p.meter), HORIZONTAL_ALIGNMENT_LEFT, -1, 13,\n'
        "\t\t\tColor(0.60, 0.72, 0.88)\n"
        "\t\t)\n",
        "玩家侧：轮数替代气槽",
    ),
    (
        '\t_draw_bar_v2(Vector2(1280 - 44 - BAR_W, 44), e.hp_ratio(), float(_hp_shown["e"]), true, e.display_name, false)\n'
        "\t_draw_meter(Vector2(1280 - 44 - BAR_W, 76), e.meter_ratio(), 5)\n"
        '\tvar meter_label := "气 %d/5" % int(e.meter)\n'
        "\tvar ml_w := font.get_string_size(meter_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x\n"
        "\tdraw_string(\n"
        "\t\tfont, Vector2(1280 - 44 - ml_w, 104), meter_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13,\n"
        "\t\tColor(0.60, 0.72, 0.88)\n"
        "\t)\n",
        '\t_draw_bar_v2(Vector2(1280 - 44 - BAR_W, 44), e.hp_ratio(), float(_hp_shown["e"]), true, e.display_name, false)\n'
        '\tif arena.battle_mode == "taikou":\n'
        '\t\tvar turn_label := "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)]\n'
        "\t\tvar tl_w := font.get_string_size(turn_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x\n"
        "\t\tdraw_string(\n"
        "\t\t\tfont, Vector2(1280 - 44 - tl_w, 104), turn_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13,\n"
        "\t\t\tColor(0.60, 0.72, 0.88)\n"
        "\t\t)\n"
        "\telse:\n"
        "\t\t_draw_meter(Vector2(1280 - 44 - BAR_W, 76), e.meter_ratio(), 5)\n"
        '\t\tvar meter_label := "气 %d/5" % int(e.meter)\n'
        "\t\tvar ml_w := font.get_string_size(meter_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x\n"
        "\t\tdraw_string(\n"
        "\t\t\tfont, Vector2(1280 - 44 - ml_w, 104), meter_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13,\n"
        "\t\t\tColor(0.60, 0.72, 0.88)\n"
        "\t\t)\n",
        "对手侧：轮数替代气槽",
    ),
    (
        "\tvar secs: int = int(ceil(maxf(0.0, float(arena.round_time_left))))\n"
        '\tvar t := "%02d" % secs\n'
        "\tvar tw := font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, 30).x\n"
        "\tdraw_string(\n"
        "\t\tfont, center + Vector2(-tw * 0.5, 11), t, HORIZONTAL_ALIGNMENT_LEFT, -1, 30,\n"
        "\t\tColor(1.0, 0.28, 0.28) if secs <= 10 else Color(0.94, 0.95, 1.0)\n"
        "\t)\n",
        "\tvar secs: int = int(ceil(maxf(0.0, float(arena.round_time_left))))\n"
        '\tvar t := "%02d" % secs\n'
        "\tvar num_color := Color(0.94, 0.95, 1.0)\n"
        '\tif arena.battle_mode == "taikou":\n'
        '\t\tt = "%d" % int(arena.tk_turn)\n'
        "\telif secs <= 10:\n"
        "\t\tnum_color = Color(1.0, 0.28, 0.28)\n"
        "\tvar tw := font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, 30).x\n"
        "\tdraw_string(\n"
        "\t\tfont, center + Vector2(-tw * 0.5, 11), t, HORIZONTAL_ALIGNMENT_LEFT, -1, 30, num_color\n"
        "\t)\n",
        "中央计时换成轮数",
    ),
    (
        "\tvar affordable := int(arena.player.meter) >= cost\n",
        '\tvar affordable := true if arena.battle_mode == "taikou" else int(arena.player.meter) >= cost\n',
        "回合制不按气耗压暗卡面",
    ),
    (
        "\tvar hover := float(arena.selected_index) == float(index)\n"
        "\tvar lift := -10.0 if hover else 0.0\n",
        "\tvar hover := float(arena.selected_index) == float(index)\n"
        '\tvar marked := arena.battle_mode == "taikou" and arena.tk_marks.has(index)\n'
        "\tvar lift := -22.0 if marked else (-10.0 if hover else 0.0)\n",
        "勾选牌抬高",
    ),
    (
        "\tif hover:\n\t\tdraw_rect(rect.grow(3.0), accent, false, 2.0)\n",
        "\tif hover:\n\t\tdraw_rect(rect.grow(3.0), accent, false, 2.0)\n"
        "\tif marked:\n"
        '\t\tvar mark_color := Color(0.98, 0.42, 0.36) if arena.tk_phase == "discard" else Color(0.98, 0.80, 0.36)\n'
        "\t\tdraw_rect(rect.grow(4.0), mark_color, false, 3.0)\n"
        '\t\tvar tag := "换" if arena.tk_phase == "discard" else "出"\n'
        "\t\tdraw_string(\n"
        "\t\t\tfont, rect.position + Vector2(CARD_W - 30, 52), tag,\n"
        "\t\t\tHORIZONTAL_ALIGNMENT_LEFT, -1, 20, mark_color\n"
        "\t\t)\n",
        "勾选边框与换/出标记",
    ),
    (
        '\t# 气耗\n\tvar cost_text := "%d气" % cost if cost > 0 else "免费"\n'
        "\tdraw_string(\n"
        "\t\tfont, rect.position + Vector2(CARD_W - 48, 30), cost_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 14,\n"
        "\t\taccent if affordable else Color(0.55, 0.30, 0.30)\n"
        "\t)\n",
        "\t# 回合制显示点数 rank（比牌只看它）；实时模式显示气耗。\n"
        '\tif arena.battle_mode == "taikou":\n'
        '\t\tvar rank_text := str(int(card.get("rank", 0)))\n'
        "\t\tvar rw := font.get_string_size(rank_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 30).x\n"
        "\t\tdraw_string(\n"
        "\t\t\tfont, rect.position + Vector2(CARD_W - rw - 14, 40), rank_text,\n"
        "\t\t\tHORIZONTAL_ALIGNMENT_LEFT, -1, 30, Color(1.0, 0.90, 0.62)\n"
        "\t\t)\n"
        "\telse:\n"
        '\t\tvar cost_text := "%d气" % cost if cost > 0 else "免费"\n'
        "\t\tdraw_string(\n"
        "\t\t\tfont, rect.position + Vector2(CARD_W - 48, 30), cost_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 14,\n"
        "\t\t\taccent if affordable else Color(0.55, 0.30, 0.30)\n"
        "\t\t)\n",
        "卡面显示点数",
    ),
    (
        '\tvar hint := "1-5 出牌    A/D 或 ←/→ 移动    R 重开    空格 暂停"\n',
        '\tvar hint := "1-5 出牌    A/D 或 ←/→ 移动    R 重开    空格 暂停"\n'
        '\tif arena.battle_mode == "taikou":\n'
        "\t\tmatch arena.tk_phase:\n"
        '\t\t\t"discard":\n'
        '\t\t\t\thint = "弃牌：1-5 标记要换的牌（最多 3 张，可不换）   空格确认   R 重开   P 暂停"\n'
        '\t\t\t"select":\n'
        '\t\t\t\thint = "选牌：1-5 选 3 张凑牌型   空格亮牌   R 重开   P 暂停"\n'
        '\t\t\t"reveal":\n'
        '\t\t\t\thint = "比牌：三同 > 三连 > 散牌   111 最大 · 123 最大 · 同张恒压连张"\n'
        '\t\t\t"resolve":\n'
        '\t\t\t\thint = "结算：牌型底数 + 点数和零头"\n'
        "\t\t\t_:\n"
        '\t\t\t\thint = "回合制合战"\n',
        "底部提示按阶段切换",
    ),
    (
        "\tif arena.combo_shown > 0:\n",
        '\tif arena.combo_shown > 0 and arena.battle_mode != "taikou":\n',
        "回合制不弹连击数",
    ),
]


def main() -> None:
    text = HUD.read_bytes().decode("utf-8")
    assert "\r" not in text, "hud.gd 不是纯 LF"
    assert "_draw_taikou_reveal" not in text, "HUD 已经接过回合制界面，别重复跑"
    assert "_draw_reveal_side" not in text, "亮牌区已经加过了"

    snippet = SNIPPET.read_bytes().decode("utf-8")
    assert "\r" not in snippet and "\n\t" in snippet, "snippet 换行/缩进不对"
    assert snippet.count("func ") == 2, "snippet 应含 2 个函数"

    for old, new, label in PATCHES:
        n = text.count(old)
        assert n == 1, f"{label}: 锚点命中 {n} 次（应为 1）"
        text = text.replace(old, new, 1)
        print(f"OK   {label}")

    pattern = re.compile(r"\n# ── 大字横幅[^\n]*\n")
    hits = list(pattern.finditer(text))
    assert len(hits) == 1, f"横幅标题命中 {len(hits)} 次"
    m = hits[0]
    text = text[: m.start()] + "\n\n" + snippet + text[m.end() :]
    print("OK   插入亮牌区（2 个函数）")

    HUD.write_bytes(text.encode("utf-8"))
    print(f"hud.gd sha256={hashlib.sha256(HUD.read_bytes()).hexdigest()}")

    proj = PROJ.read_bytes().decode("utf-8")
    assert "\r" not in proj
    old_desc = 'config/description="卡牌驱动的 2D 横版格斗：打牌出招，连招按序结算，三张特定牌触发大招。"\n'
    new_desc = (
        'config/description="卡牌对战：默认太阁 IV 回合制合战（同时亮 3 张比三同/三连牌型）；'
        'BATTLE_MODE=realtime 可切回实时格斗出招。"\n'
    )
    assert proj.count(old_desc) == 1
    proj = proj.replace(old_desc, new_desc, 1)
    old_head = "; 2D 横版格斗，出招完全由手牌驱动。\n"
    assert proj.count(old_head) == 1
    proj = proj.replace(old_head, "; 手牌驱动的对战；玩法骨架见 arena.gd 的 BATTLE_MODE。\n", 1)
    PROJ.write_bytes(proj.encode("utf-8"))
    print(f"project.godot sha256={hashlib.sha256(PROJ.read_bytes()).hexdigest()}")
    print("HUD_PATCH_OK")


if __name__ == "__main__":
    main()
