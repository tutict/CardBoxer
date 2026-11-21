"""Add load-bearing Rage assertions to taikou_flow_check.gd.

Pins: only the damaged side gains rage, draw gains for both, a full gauge
triggers EX on reveal and is consumed, EX does not leak into the next turn,
rage survives across 局 but resets for a new match.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

FLOW = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\tests\taikou_flow_check.gd")


def b(text: str) -> bytes:
    return text.encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


RAGE_CHECK = '''
## 怒火槽：只有挨打攒怒、满槽本回升 EX、触发即清空、跨局保留、新一场清零。
func _check_rage() -> void:
\ta.round_phase = "fight"
\ta.player.reset_for_round(430, 1)
\ta.enemy.reset_for_round(850, -1)
\ta.tk_player_rage = 0.0
\ta.tk_enemy_rage = 0.0

\t# 对手赢：玩家挨打攒怒，赢家不攒。
\ta.tk_player_result = Rules.evaluate([2, 3, 4])
\ta.tk_enemy_result = Rules.evaluate([1, 1, 1])
\ta._resolve_taikou()
\t_expect(a.tk_winner == "enemy", "构造的牌型应判对手赢")
\t_expect(
\t\ta.tk_player_rage == float(a.tk_damage) * Rage.PER_DAMAGE,
\t\t"挨打应按伤害攒怒，实际 %f / dmg=%d" % [a.tk_player_rage, a.tk_damage]
\t)
\t_expect(a.tk_enemy_rage == 0.0, "赢家不该攒怒")

\t# 平局：双方各受 3 点，双方都攒。
\ta.tk_player_rage = 0.0
\ta.tk_enemy_rage = 0.0
\ta.tk_player_result = Rules.evaluate([1, 1, 1])
\ta.tk_enemy_result = Rules.evaluate([1, 1, 1])
\ta._resolve_taikou()
\t_expect(a.tk_winner == "draw", "同分应判平局")
\t_expect(
\t\ta.tk_player_rage == 3.0 * Rage.PER_DAMAGE and a.tk_enemy_rage == 3.0 * Rage.PER_DAMAGE,
\t\t"平局双方都该攒怒，实际 %f/%f" % [a.tk_player_rage, a.tk_enemy_rage]
\t)

\t# 满槽 → 亮牌触发 EX 并清空；未攒满的一方不触发。
\ta.tk_player_rage = Rage.MAX
\ta.tk_enemy_rage = 0.0
\ta.tk_bot = true
\ta._do_taikou_reveal()
\t_expect(bool(a.tk_player_ex), "满槽亮牌应触发 EX")
\t_expect(not bool(a.tk_enemy_ex), "未攒满的一方不该触发 EX")
\t_expect(a.tk_player_rage == 0.0, "触发 EX 后怒火应清空")
\t_expect(a.tk_player_reveal.size() == 3, "EX 后仍是 3 张牌")
\t_expect(
\t\tRules.compare(a.tk_player_result, Rules.evaluate(a.tk_player_reveal)) == 0,
\t\t"EX 后的判定结果必须与实际显示的 rank 一致"
\t)
\ta._reset_taikou_turn(false)
\t_expect(not bool(a.tk_player_ex), "下一回不该残留 EX 标志")
\ta.tk_bot = false

\t# 跨局保留，新一场清零。
\ta.tk_player_rage = 55.0
\ta._start_round()
\t_expect(a.tk_player_rage == 55.0, "怒火应跨局保留，实际 %f" % a.tk_player_rage)
\ta._start_match()
\t_expect(a.tk_player_rage == 0.0, "新一场比赛应清空怒火")
'''


PATCHES: list[tuple[str, str]] = [
    (
        'const Rules = preload("res://scripts/taikou_rules.gd")\n',
        'const Rules = preload("res://scripts/taikou_rules.gd")\n'
        'const Rage = preload("res://scripts/taikou_rage.gd")\n',
    ),
    (
        '\t_check_turn_limit()\n\t_check_mode_switch()\n',
        '\t_check_turn_limit()\n\t_check_rage()\n\t_check_mode_switch()\n',
    ),
]


def main() -> int:
    data = FLOW.read_bytes()
    before = sha(data)
    for idx, (old_text, new_text) in enumerate(PATCHES, 1):
        old, new = b(old_text), b(new_text)
        count = data.count(old)
        if count != 1:
            raise SystemExit("ANCHOR_MISMATCH #%d count=%d" % (idx, count))
        data = data.replace(old, new, 1)
        print("  flow anchor #%d OK" % idx)
    if b"func _check_rage()" in data:
        raise SystemExit("RAGE_CHECK_ALREADY_PRESENT")
    data += b(RAGE_CHECK)
    FLOW.write_bytes(data)
    written = FLOW.read_bytes()
    if b"\r" in written or sha(written) == before:
        raise SystemExit("NEWLINE_DAMAGED_OR_UNCHANGED")
    print("taikou_flow_check.gd %s -> %s | pure-LF kept" % (before[:12], sha(written)[:12]))
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
