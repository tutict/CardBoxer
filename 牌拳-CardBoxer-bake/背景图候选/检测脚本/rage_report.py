"""Summarise natural-accumulation Taikou bot logs for the Rage/EX gauge.

Counts how often EX actually fires WITHOUT the CARD_BOXER_RAGE_START hook,
so the gauge is neither decorative (never fills) nor spammy (always full).
Also re-checks that each 局 is still exactly TK_MAX_TURNS (3) 回.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PAT = re.compile(
    r"\[TAIKOU\] turn=(\d+) hp=(\d+)/(\d+) rage=(\d+)/(\d+) ex=(\S+)/(\S+)"
)


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("NO_LOGS")
        return 2
    rounds = 0
    games = 0
    ex_rounds = 0
    player_ex = 0
    enemy_ex = 0
    rage_samples: list[int] = []
    turns_per_game: list[int] = []
    cur = 0
    script_errors = 0

    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        script_errors += text.count("SCRIPT ERROR")
        for line in text.splitlines():
            m = PAT.search(line)
            if not m:
                continue
            turn = int(m.group(1))
            p_rage, e_rage = int(m.group(4)), int(m.group(5))
            p_ex, e_ex = m.group(6), m.group(7)
            rounds += 1
            rage_samples.extend([p_rage, e_rage])
            if p_ex == "EX":
                player_ex += 1
            if e_ex == "EX":
                enemy_ex += 1
            if p_ex == "EX" or e_ex == "EX":
                ex_rounds += 1
            if turn == 1:
                if cur:
                    turns_per_game.append(cur)
                games += 1
                cur = 1
            else:
                cur += 1
        if cur:
            turns_per_game.append(cur)
            cur = 0

    print("独立对局=%d 局数=%d 回数=%d SCRIPT_ERROR=%d" % (
        len(paths), games, rounds, script_errors,
    ))
    print("EX 触发回数=%d (%.1f%%) | 玩家 EX=%d 对手 EX=%d" % (
        ex_rounds, 100.0 * ex_rounds / rounds if rounds else 0.0,
        player_ex, enemy_ex,
    ))
    print("怒火采样: min=%d max=%d mean=%.1f (结算后值，满槽触发后已清零)" % (
        min(rage_samples), max(rage_samples),
        sum(rage_samples) / float(len(rage_samples)),
    ))
    print("每局回数集合=%s" % sorted(set(turns_per_game)))
    ok = (
        script_errors == 0
        and all(n == 3 for n in turns_per_game)
        and ex_rounds > 0
        and rounds > 0
    )
    print("RAGE REPORT %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
