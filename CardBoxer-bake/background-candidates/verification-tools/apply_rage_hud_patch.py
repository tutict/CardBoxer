"""Draw the Rage gauge and EX reveal badges (hud.gd).

Byte-safe, pure-LF needles, every anchor must match exactly once.
Real-time mode keeps its original _draw_meter / 气槽 untouched.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

HUD = Path(r"D:\Projects\CardBoxer\CardBoxer\scripts\hud.gd")


def b(text: str) -> bytes:
    return text.encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


RAGE_BAR = '''\
## 回合制专用：y=76 那条原本空着的槽位画怒火；实时模式的 _draw_meter 原样不动。
func _draw_rage_bar(pos: Vector2, ratio: float, mirrored: bool) -> void:
\tvar full: bool = ratio >= 1.0
\tdraw_rect(Rect2(pos, Vector2(BAR_W, RAGE_H)), RAGE_EMPTY)
\tvar fill_w: float = BAR_W * clampf(ratio, 0.0, 1.0)
\tif fill_w > 0.0:
\t\tvar bands: int = 5
\t\tfor i in range(bands):
\t\t\tvar t: float = float(i) / float(bands - 1)
\t\t\tvar col: Color = RAGE_LOW.lerp(RAGE_HIGH, t)
\t\t\tif full:
\t\t\t\tcol = col.lerp(RAGE_FULL, 0.55)
\t\t\tvar y: float = pos.y + float(i) * (RAGE_H / float(bands))
\t\t\tvar x: float = (pos.x + BAR_W - fill_w) if mirrored else pos.x
\t\t\tdraw_rect(Rect2(Vector2(x, y), Vector2(fill_w, RAGE_H / float(bands) + 0.5)), col)
\tvar edge: Color = Color(0.45, 0.32, 0.28, 0.85)
\tvar edge_w: float = 1.0
\tif full:
\t\tvar pulse: float = 0.55 + 0.35 * sin(_time * 9.0)
\t\tedge = Color(RAGE_FULL.r, RAGE_FULL.g, RAGE_FULL.b, pulse)
\t\tedge_w = 2.0
\tdraw_rect(Rect2(pos, Vector2(BAR_W, RAGE_H)), edge, false, edge_w)
\tvar label: String = "怒火 EX READY" if full else "怒火 %d%%" % int(round(ratio * 100.0))
\tvar lw: float = font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
\tvar lx: float = (pos.x + 6.0) if mirrored else (pos.x + BAR_W - lw - 6.0)
\tdraw_string(font, Vector2(lx, pos.y + RAGE_H - 1.0), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.98, 0.94, 0.88))


'''

PATCHES: list[tuple[str, str]] = [
    (
        'const Defs = preload("res://scripts/card_data.gd")\n',
        'const Defs = preload("res://scripts/card_data.gd")\n'
        'const Rage = preload("res://scripts/taikou_rage.gd")\n',
    ),
    (
        'const HP_GHOST := Color(1.0, 0.58, 0.40, 0.55)\n',
        'const HP_GHOST := Color(1.0, 0.58, 0.40, 0.55)\n'
        '\n'
        '## 怒火槽：暖橙→氧化红，满槽转金。与血条的阵营色词汇分开，\n'
        '## 也不复用实时模式那个蓝色分格气槽（两套资源语义不同）。\n'
        'const RAGE_EMPTY := Color(0.14, 0.11, 0.13, 0.95)\n'
        'const RAGE_LOW := Color(0.92, 0.48, 0.20)\n'
        'const RAGE_HIGH := Color(0.90, 0.20, 0.16)\n'
        'const RAGE_FULL := Color(1.0, 0.86, 0.45)\n'
        'const RAGE_H := 10.0\n',
    ),
    (
        '\tif arena.battle_mode == "taikou":\n'
        '\t\tdraw_string(\n'
        '\t\t\tfont, Vector2(44, 104), "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)],\n',
        '\tif arena.battle_mode == "taikou":\n'
        '\t\t_draw_rage_bar(Vector2(44, 76), Rage.ratio(float(arena.tk_player_rage)), false)\n'
        '\t\tdraw_string(\n'
        '\t\t\tfont, Vector2(44, 104), "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)],\n',
    ),
    (
        '\tif arena.battle_mode == "taikou":\n'
        '\t\tvar turn_label := "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)]\n',
        '\tif arena.battle_mode == "taikou":\n'
        '\t\t_draw_rage_bar(Vector2(1280 - 44 - BAR_W, 76), Rage.ratio(float(arena.tk_enemy_rage)), true)\n'
        '\t\tvar turn_label := "第 %d 轮 / 共 %d 轮" % [int(arena.tk_turn), int(arena.TK_MAX_TURNS)]\n',
    ),
    (
        # Insert BEFORE the "中央：计时与回合点" section comment, otherwise
        # that comment would end up describing the rage bar by mistake.
        '\t\tdraw_rect(Rect2(Vector2(x + 1, pos.y + 1), Vector2((seg_w - 2.0) * filled, 8)), color)\n\n\n',
        '\t\tdraw_rect(Rect2(Vector2(x + 1, pos.y + 1), Vector2((seg_w - 2.0) * filled, 8)), color)\n\n\n'
        + RAGE_BAR,
    ),
    (
        '\tvar own := "player" if not mirrored else "enemy"\n',
        '\tvar own := "player" if not mirrored else "enemy"\n'
        '\t# arena 是 untyped，属性读回来是 Variant，显式转 bool 免得 := 推不出类型。\n'
        '\tvar ex: bool = false\n'
        '\tvar boosted: bool = false\n'
        '\tif mirrored:\n'
        '\t\tex = bool(arena.tk_enemy_ex)\n'
        '\t\tboosted = bool(arena.tk_enemy_ex_boosted)\n'
        '\telse:\n'
        '\t\tex = bool(arena.tk_player_ex)\n'
        '\t\tboosted = bool(arena.tk_player_ex_boosted)\n',
    ),
    (
        '\t\tdraw_rect(rect, edge, false, 2.0)\n',
        '\t\tdraw_rect(rect, edge, false, 2.0)\n'
        '\t\tif ex:\n'
        '\t\t\tdraw_rect(rect.grow(-3.0), Color(RAGE_FULL.r, RAGE_FULL.g, RAGE_FULL.b, 0.80), false, 1.5)\n'
        '\t\t\tdraw_string(font, Vector2(x + 5, pos.y + 16), "EX", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, RAGE_FULL)\n',
    ),
    (
        '\tvar label := String(result.get("name", ""))\n',
        '\tvar label := String(result.get("name", ""))\n'
        '\tif ex:\n'
        '\t\tlabel = label + (" · EX" if boosted else " · EX 保底")\n',
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
        print("  hud anchor #%d OK" % idx)
    HUD.write_bytes(data)
    written = HUD.read_bytes()
    if b"\r" in written or sha(written) == before:
        raise SystemExit("NEWLINE_DAMAGED_OR_UNCHANGED")
    print("hud.gd %s -> %s | pure-LF kept" % (before[:12], sha(written)[:12]))
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
