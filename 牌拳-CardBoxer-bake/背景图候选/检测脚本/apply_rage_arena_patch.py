"""Wire the Rage/EX gauge into the Taikou round state machine (arena.gd).

Byte-safe, pure-LF needles, every anchor must match exactly once.
No text-mode newline normalisation; sha256 + CR check after writing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ARENA = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\scripts\arena.gd")


def b(text: str) -> bytes:
    return text.encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


PATCHES: list[tuple[str, str]] = [
    (
        'const Rules = preload("res://scripts/taikou_rules.gd")\n'
        'const TaikouAI = preload("res://scripts/taikou_ai.gd")\n',
        'const Rules = preload("res://scripts/taikou_rules.gd")\n'
        'const TaikouAI = preload("res://scripts/taikou_ai.gd")\n'
        'const Rage = preload("res://scripts/taikou_rage.gd")\n',
    ),
    (
        'var tk_bot := false               # CARD_BOXER_TAIKOU_BOT：无输入自动对战，仅供验收\n',
        'var tk_bot := false               # CARD_BOXER_TAIKOU_BOT：无输入自动对战，仅供验收\n'
        '\n'
        '## 怒火槽：挨打攒怒，满槽时本回亮出的 3 张牌升 EX（见 taikou_rage.gd）。\n'
        '## 跨「局」保留、只在 _start_match() 清零——三回制一局太短，每局清零就几乎用不上。\n'
        'var tk_player_rage := 0.0\n'
        'var tk_enemy_rage := 0.0\n'
        'var tk_player_ex := false          # 本回是否消耗怒火触发了 EX\n'
        'var tk_enemy_ex := false\n'
        'var tk_player_ex_boosted := false # 升级是否真被采用（保底时 false）\n'
        'var tk_enemy_ex_boosted := false\n',
    ),
    (
        'func _start_match() -> void:\n'
        '\tround_wins = [0, 0]\n'
        '\tround_index = 1\n'
        '\t_deck = _shuffled_deck()\n',
        'func _start_match() -> void:\n'
        '\tround_wins = [0, 0]\n'
        '\tround_index = 1\n'
        '\ttk_player_rage = 0.0\n'
        '\ttk_enemy_rage = 0.0\n'
        '\t_deck = _shuffled_deck()\n',
    ),
    (
        '\ttk_bot = OS.get_environment("CARD_BOXER_TAIKOU_BOT") != ""\n'
        '\t_start_match()\n',
        '\ttk_bot = OS.get_environment("CARD_BOXER_TAIKOU_BOT") != ""\n'
        '\t_start_match()\n'
        '\t# 验收钩子：只在设了环境变量时把双方怒火直接灌满，用来截 EX 亮牌帧。\n'
        '\tvar rage_start := OS.get_environment("CARD_BOXER_RAGE_START")\n'
        '\tif rage_start != "":\n'
        '\t\ttk_player_rage = clampf(float(rage_start), 0.0, Rage.MAX)\n'
        '\t\ttk_enemy_rage = tk_player_rage\n',
    ),
    (
        '\ttk_winner = ""\n'
        '\ttk_damage = 0\n'
        '\t_banner(\n',
        '\ttk_winner = ""\n'
        '\ttk_damage = 0\n'
        '\ttk_player_ex = false\n'
        '\ttk_enemy_ex = false\n'
        '\ttk_player_ex_boosted = false\n'
        '\ttk_enemy_ex_boosted = false\n'
        '\t_banner(\n',
    ),
    (
        '\ttk_player_result = Rules.evaluate(tk_player_reveal)\n'
        '\ttk_enemy_result = Rules.evaluate(tk_enemy_reveal)\n',
        '\t# 满槽 → 本回 3 张牌升 EX（rank+1 封顶 9），消耗后清空；保底见 Rage.best()。\n'
        '\ttk_player_ex = Rage.is_full(tk_player_rage)\n'
        '\ttk_enemy_ex = Rage.is_full(tk_enemy_rage)\n'
        '\tif tk_player_ex:\n'
        '\t\tvar p_ex: Dictionary = Rage.best(tk_player_reveal)\n'
        '\t\ttk_player_reveal = p_ex["ranks"]\n'
        '\t\ttk_player_result = p_ex["result"]\n'
        '\t\ttk_player_ex_boosted = bool(p_ex["boosted"])\n'
        '\t\ttk_player_rage = 0.0\n'
        '\telse:\n'
        '\t\ttk_player_result = Rules.evaluate(tk_player_reveal)\n'
        '\t\ttk_player_ex_boosted = false\n'
        '\tif tk_enemy_ex:\n'
        '\t\tvar e_ex: Dictionary = Rage.best(tk_enemy_reveal)\n'
        '\t\ttk_enemy_reveal = e_ex["ranks"]\n'
        '\t\ttk_enemy_result = e_ex["result"]\n'
        '\t\ttk_enemy_ex_boosted = bool(e_ex["boosted"])\n'
        '\t\ttk_enemy_rage = 0.0\n'
        '\telse:\n'
        '\t\ttk_enemy_result = Rules.evaluate(tk_enemy_reveal)\n'
        '\t\ttk_enemy_ex_boosted = false\n',
    ),
    (
        '\t\t"亮牌",\n',
        '\t\t"EX 亮牌" if tk_player_ex or tk_enemy_ex else "亮牌",\n',
    ),
    (
        '\t\tenemy.apply_hit(tk_damage, "taikou", "", false)\n',
        '\t\tenemy.apply_hit(tk_damage, "taikou", "", false)\n'
        '\t\ttk_enemy_rage = Rage.gain(tk_enemy_rage, tk_damage)\n',
    ),
    (
        '\t\tplayer.apply_hit(tk_damage, "taikou", "", false)\n',
        '\t\tplayer.apply_hit(tk_damage, "taikou", "", false)\n'
        '\t\ttk_player_rage = Rage.gain(tk_player_rage, tk_damage)\n',
    ),
    (
        '\t\tplayer.apply_hit(3, "taikou", "", false)\n'
        '\t\tenemy.apply_hit(3, "taikou", "", false)\n'
        '\t\t_banner("平局", "双方各受 3 点", Color(0.86, 0.88, 0.95), 1.6)\n',
        '\t\tplayer.apply_hit(3, "taikou", "", false)\n'
        '\t\tenemy.apply_hit(3, "taikou", "", false)\n'
        '\t\ttk_player_rage = Rage.gain(tk_player_rage, 3)\n'
        '\t\ttk_enemy_rage = Rage.gain(tk_enemy_rage, 3)\n'
        '\t\t_banner("平局", "双方各受 3 点", Color(0.86, 0.88, 0.95), 1.6)\n',
    ),
    (
        '\t\tprint("[TAIKOU] turn=%d hp=%d/%d | 你 %s %s vs 青岚 %s %s | winner=%s dmg=%d" % [\n'
        '\t\t\ttk_turn, player.hp, enemy.hp,\n'
        '\t\t\tString(tk_player_result["name"]), str(tk_player_reveal),\n'
        '\t\t\tString(tk_enemy_result["name"]), str(tk_enemy_reveal),\n'
        '\t\t\ttk_winner, tk_damage\n'
        '\t\t])\n',
        '\t\tprint("[TAIKOU] turn=%d hp=%d/%d rage=%d/%d ex=%s/%s | 你 %s %s vs 青岚 %s %s | winner=%s dmg=%d" % [\n'
        '\t\t\ttk_turn, player.hp, enemy.hp,\n'
        '\t\t\tint(tk_player_rage), int(tk_enemy_rage),\n'
        '\t\t\t"EX" if tk_player_ex else "-", "EX" if tk_enemy_ex else "-",\n'
        '\t\t\tString(tk_player_result["name"]), str(tk_player_reveal),\n'
        '\t\t\tString(tk_enemy_result["name"]), str(tk_enemy_reveal),\n'
        '\t\t\ttk_winner, tk_damage\n'
        '\t\t])\n',
    ),
]


def main() -> int:
    data = ARENA.read_bytes()
    before = sha(data)
    for idx, (old_text, new_text) in enumerate(PATCHES, 1):
        old, new = b(old_text), b(new_text)
        count = data.count(old)
        if count != 1:
            raise SystemExit("ANCHOR_MISMATCH #%d count=%d" % (idx, count))
        data = data.replace(old, new, 1)
        print("  arena anchor #%d OK" % idx)
    ARENA.write_bytes(data)
    written = ARENA.read_bytes()
    if b"\r" in written or sha(written) == before:
        raise SystemExit("NEWLINE_DAMAGED_OR_UNCHANGED")
    print("arena.gd %s -> %s | pure-LF kept" % (before[:12], sha(written)[:12]))
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
