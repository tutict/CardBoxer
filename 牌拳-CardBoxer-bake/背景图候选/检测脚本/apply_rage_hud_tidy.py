"""Tidy the rage gauge label: move it out of the 10px-tall bar.

The first cut drew a 12px string INSIDE a 10px bar, so "怒火 EX READY"
overlapped the fill and the HP bar above it. Now the bar stays clean
(gradient + pulsing full edge) and the value joins the y=104 turn line.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

HUD = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\scripts\hud.gd")


def b(text: str) -> bytes:
    return text.encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


PATCHES: list[tuple[str, str]] = [
    (
        '\tvar label: String = "怒火 EX READY" if full else "怒火 %d%%" % int(round(ratio * 100.0))\n'
        '\tvar lw: float = font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x\n'
        '\tvar lx: float = (pos.x + 6.0) if mirrored else (pos.x + BAR_W - lw - 6.0)\n'
        '\tdraw_string(font, Vector2(lx, pos.y + RAGE_H - 1.0), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.98, 0.94, 0.88))\n',
        '\t# 数值并到 y=104 的轮次行里：槽只有 10px 高，塞不下 12px 的字，\n'
        '\t# 硬画会同时压住填充色和上方血条。槽本身保持纯色带 + 满槽脉冲边框。\n',
    ),
    (
        '\t\t_draw_rage_bar(Vector2(44, 76), Rage.ratio(float(arena.tk_player_rage)), false)\n'
        '\t\tdraw_string(\n'
        '\t\t\tfont, Vector2(44, 104), "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)],\n'
        '\t\t\tHORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.84, 0.89, 0.98)\n'
        '\t\t)\n',
        '\t\t_draw_rage_bar(Vector2(44, 76), Rage.ratio(float(arena.tk_player_rage)), false)\n'
        '\t\tvar p_rage_label: String = "EX READY" if Rage.is_full(float(arena.tk_player_rage)) else "%d%%" % int(round(Rage.ratio(float(arena.tk_player_rage)) * 100.0))\n'
        '\t\tdraw_string(\n'
        '\t\t\tfont, Vector2(44, 104), "第 %d 轮 / 共 %d 轮   ·   怒火 %s" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS), p_rage_label],\n'
        '\t\t\tHORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.84, 0.89, 0.98)\n'
        '\t\t)\n',
    ),
    (
        '\t\t_draw_rage_bar(Vector2(1280 - 44 - BAR_W, 76), Rage.ratio(float(arena.tk_enemy_rage)), true)\n'
        '\t\tvar turn_label := "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)]\n',
        '\t\t_draw_rage_bar(Vector2(1280 - 44 - BAR_W, 76), Rage.ratio(float(arena.tk_enemy_rage)), true)\n'
        '\t\tvar e_rage_label: String = "EX READY" if Rage.is_full(float(arena.tk_enemy_rage)) else "%d%%" % int(round(Rage.ratio(float(arena.tk_enemy_rage)) * 100.0))\n'
        '\t\tvar turn_label := "第 %d 轮 / 共 %d 轮   ·   怒火 %s" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS), e_rage_label]\n',
    ),
]


def main() -> int:
    data = HUD.read_bytes()
    before = sha(data)
    for idx, (old_text, new_text) in enumerate(PATCHES, 1):
        old, new = b(old_text), b(new_text)
        count = data.count(old)
        if count != 1:
            raise SystemExit("ANCHOR_MISMATCH #%d count=%d" % (idx, count))
        data = data.replace(old, new, 1)
        print("  tidy anchor #%d OK" % idx)
    HUD.write_bytes(data)
    written = HUD.read_bytes()
    if b"\r" in written or sha(written) == before:
        raise SystemExit("NEWLINE_DAMAGED_OR_UNCHANGED")
    print("hud.gd %s -> %s | pure-LF kept" % (before[:12], sha(written)[:12]))
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
