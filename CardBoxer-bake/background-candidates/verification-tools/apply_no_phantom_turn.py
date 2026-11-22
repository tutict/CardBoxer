"""Fix the phantom 4th turn shown during the 3-duel settlement.

Found in the engine screenshot: the 3-duel settlement banner said
"3 回战罢 · 按兵力判定" correctly, but the HUD showed "第 4 轮 / 共 3 轮"
and the centre circle showed 4, because _finish_taikou_turn() incremented
tk_turn BEFORE checking the limit.

Fix: check the limit first and leave tk_turn on the last real duel.
The load-bearing flow assertion is updated from tk_turn==4 to tk_turn==3.

Byte-safe: both targets are pure LF (verified by reading bytes), and each
anchor must match exactly once.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
ARENA = GAME / "scripts" / "arena.gd"
FLOW = GAME / "tests" / "taikou_flow_check.gd"


def b(text: str) -> bytes:
    return text.encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


ARENA_OLD = b(
    "\ttk_turn += 1\n"
    "\tif tk_turn > TK_MAX_TURNS:\n"
    '\t\tvar winner := "draw"\n'
    "\t\tif player.hp > enemy.hp:\n"
    '\t\t\twinner = "player"\n'
    "\t\telif enemy.hp > player.hp:\n"
    '\t\t\twinner = "enemy"\n'
    '\t\t_end_round(winner, "%d 回战罢 · 按兵力判定" % TK_MAX_TURNS)\n'
    "\t\treturn\n"
    "\t_reset_taikou_turn(false)\n"
)

ARENA_NEW = b(
    "\t# 先判断是否打满：收局时 tk_turn 停在最后一回，不要自增出超过上限、\n"
    "\t# 根本不存在的轮次（否则 HUD 会显示「第 4 轮 / 共 3 轮」）。\n"
    "\tif tk_turn >= TK_MAX_TURNS:\n"
    '\t\tvar winner := "draw"\n'
    "\t\tif player.hp > enemy.hp:\n"
    '\t\t\twinner = "player"\n'
    "\t\telif enemy.hp > player.hp:\n"
    '\t\t\twinner = "enemy"\n'
    '\t\t_end_round(winner, "%d 回战罢 · 按兵力判定" % TK_MAX_TURNS)\n'
    "\t\treturn\n"
    "\ttk_turn += 1\n"
    "\t_reset_taikou_turn(false)\n"
)

FLOW_OLD = b(
    '\t_expect(a.tk_turn == 4, "收局时轮数应停在 4（3+1），实际 %d" % a.tk_turn)\n'
)
FLOW_NEW = b(
    '\t_expect(a.tk_turn == 3, "收局时轮数应停在 3，不应自增出越界轮次，实际 %d" % a.tk_turn)\n'
)


def apply(path: Path, old: bytes, new: bytes) -> None:
    data = path.read_bytes()
    before = sha(data)
    count = data.count(old)
    if count != 1:
        raise SystemExit("ANCHOR_MISMATCH %s count=%d" % (path.name, count))
    written = data.replace(old, new, 1)
    path.write_bytes(written)
    after = sha(path.read_bytes())
    damaged = b"\r" in path.read_bytes()  # both files are pure LF
    print("%s: %s -> %s | anchor OK | pure-LF kept %s" % (
        path.name, before[:12], after[:12], "NO" if damaged else "YES",
    ))
    if after == before or damaged:
        raise SystemExit("PATCH_FAILED %s" % path.name)


def main() -> int:
    apply(ARENA, ARENA_OLD, ARENA_NEW)
    apply(FLOW, FLOW_OLD, FLOW_NEW)
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
