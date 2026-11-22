"""Summarise a Taikou bot log into per-ROUND (局) results.

[P0 naming] one 局 = TK_MAX_TURNS card duels (回). The log prints one
[TAIKOU] line per 回 with post-resolution HP. A new 局 starts when turn
resets to 1 and HP is restored.

The last HP of the 3rd 回 decides the 局: higher HP wins, equal HP is a draw.
A draw does NOT increment round_wins (see arena.gd::_end_round), so it forces
an extra 局 with no upper bound -- this script quantifies how often that is.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-three-rounds\bot_long.log")
PATTERN = re.compile(r"\[TAIKOU\] turn=(\d+) hp=(\d+)/(\d+)")


def parse(path: Path) -> list[list[tuple[int, int, int]]]:
    rows: list[tuple[int, int, int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = PATTERN.search(line)
        if m:
            rows.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    games: list[list[tuple[int, int, int]]] = []
    cur: list[tuple[int, int, int]] = []
    for row in rows:
        if row[0] == 1 and cur:
            games.append(cur)
            cur = []
        cur.append(row)
    if cur:
        games.append(cur)
    return games


def main() -> int:
    # Each file is one independent match (a fresh shuffle). Grouping must not
    # cross file boundaries, otherwise two 2-局 matches would look like one 4-局.
    paths = [Path(p) for p in sys.argv[1:]] or [DEFAULT]
    games: list[list[tuple[int, int, int]]] = []
    for path in paths:
        games.extend(parse(path))
    print("独立对局文件数=%d" % len(paths))

    tally = {"player": 0, "enemy": 0, "draw": 0, "truncated": 0}
    for idx, game in enumerate(games, 1):
        turns = ",".join(str(r[0]) for r in game)
        last_p, last_e = game[-1][1], game[-1][2]
        if len(game) < 3:
            verdict = "truncated"
        elif last_p > last_e:
            verdict = "player"
        elif last_e > last_p:
            verdict = "enemy"
        else:
            verdict = "draw"
        tally[verdict] += 1
        print("局 %d: 回=[%s] 收局血量=%d/%d -> %s%s" % (
            idx, turns, last_p, last_e, verdict,
            "  <-- 平局加赛" if verdict == "draw" else "",
        ))

    total = sum(len(g) for g in games)
    print("---")
    print("总局数=%d 玩家胜=%d 对手胜=%d 平局加赛=%d 截断=%d | 回数总计=%d" % (
        len(games), tally["player"], tally["enemy"], tally["draw"],
        tally["truncated"], total,
    ))
    complete = [g for g in games if len(g) == 3]
    decided = tally["player"] + tally["enemy"] + tally["draw"]
    if decided:
        print("平局加赛占完整局比例=%d/%d = %.1f%%" % (
            tally["draw"], decided, 100.0 * tally["draw"] / decided,
        ))
    print("完整局每局回数集合=%s" % sorted({len(g) for g in complete}))
    return 0 if complete and all(len(g) == 3 for g in complete) else 1


if __name__ == "__main__":
    raise SystemExit(main())
