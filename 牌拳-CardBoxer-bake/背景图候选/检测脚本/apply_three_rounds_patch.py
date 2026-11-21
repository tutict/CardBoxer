"""Switch each Taikou IV round from 12 card duels to 3, byte-safely.

Both target files are pure CRLF; every needle is built as str -> CRLF -> UTF-8
bytes so no text-mode newline normalisation can silently rewrite the file.
Each anchor must match exactly once or the patch aborts before writing.

Changes:
  arena.gd                 TK_MAX_TURNS 12 -> 3, dynamic settlement label
  taikou_flow_check.gd     remove the stale "12" in the comment, pin 3 with
                           an assertion, and add a load-bearing test that
                           walks tk_turn 1 -> 3 continuously to the round end.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
ARENA = GAME / "scripts" / "arena.gd"
FLOW = GAME / "tests" / "taikou_flow_check.gd"


def b(text: str) -> bytes:
    # Verified by reading bytes: both targets are PURE LF (CRLF=0, lone LF=1087/162).
    # Do NOT normalise to CRLF -- a shell `grep -c $'\r'` reported 1087 and was wrong.
    return text.encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


ARENA_PATCHES = [
    (
        b("const TK_DISCARD_MAX := 3\nconst TK_MAX_TURNS := 12\n"),
        b("const TK_DISCARD_MAX := 3\n"
          "## 一局合战打满这么多回亮牌就按剩余兵力收局；HUD 与结算文案都读本常量，别在别处写死回数。\n"
          "const TK_MAX_TURNS := 3\n"),
    ),
    (
        b('\t\t_end_round(winner, "轮数耗尽 · 按兵力判定")'),
        b('\t\t_end_round(winner, "%d 回战罢 · 按兵力判定" % TK_MAX_TURNS)'),
    ),
]

OLD_LIMIT = b(
    "## 12 轮打完仍没 KO 时，必须按兵力收局，不能无限循环。\n"
    "func _check_turn_limit() -> void:\n"
    "\ta.tk_turn = ArenaScript.TK_MAX_TURNS\n"
    "\ta.player.hp = 70\n"
    "\ta.enemy.hp = 40\n"
    "\ta._finish_taikou_turn()\n"
    '\t_expect(a.round_phase == "over", "轮数耗尽应结束本局")\n'
    '\t_expect(a.round_wins[0] == 1, "兵力高的一方应拿下一局")\n'
)

NEW_LIMIT = b(
    "## 打满轮数上限仍没 KO 时，必须按兵力收局，不能无限循环。\n"
    "## 「一局 = 3 回」由下面的承重断言钉死，防止只改常量不更新预期。\n"
    "func _check_turn_limit() -> void:\n"
    '\t_expect(ArenaScript.TK_MAX_TURNS == 3, "一局卡牌对战应为 3 回，实际 %d" % ArenaScript.TK_MAX_TURNS)\n'
    "\t# 不是把 tk_turn 直接设成上限跳到末尾，而是从第一回连续推进，\n"
    "\t# 证明「打满三回」这条路径真的会在第三回收局。\n"
    '\ta.round_phase = "fight"\n'
    "\ta.round_wins = [0, 0]\n"
    "\ta.tk_turn = 1\n"
    "\ta.player.hp = 70\n"
    "\ta.enemy.hp = 40\n"
    "\tvar steps: int = 0\n"
    '\twhile a.round_phase != "over" and steps < 10:\n'
    "\t\ta._finish_taikou_turn()\n"
    "\t\tsteps += 1\n"
    '\t_expect(steps == 3, "应恰好打满 3 回收局，实际 %d 回" % steps)\n'
    '\t_expect(a.tk_turn == 4, "收局时轮数应停在 4（3+1），实际 %d" % a.tk_turn)\n'
    '\t_expect(a.round_phase == "over", "三回战罢应结束本局")\n'
    '\t_expect(a.round_wins[0] == 1, "兵力高的一方应拿下一局")\n'
)

FLOW_PATCHES = [(OLD_LIMIT, NEW_LIMIT)]


def apply(path: Path, patches: list[tuple[bytes, bytes]]) -> None:
    data = path.read_bytes()
    before = sha(data)
    crlf_before = data.count(b"\r\n")
    for idx, (old, new) in enumerate(patches, 1):
        count = data.count(old)
        if count != 1:
            raise SystemExit("ANCHOR_MISMATCH %s #%d count=%d" % (path.name, idx, count))
        data = data.replace(old, new, 1)
        print("  %s anchor #%d OK" % (path.name, idx))
    path.write_bytes(data)
    written = path.read_bytes()
    after = sha(written)
    crlf_after = written.count(b"\r\n")
    lone_after = written.count(b"\n") - crlf_after
    pure_crlf = crlf_before > 0 and (data.count(b"\n") - crlf_before) == 0
    # Keep the file's ORIGINAL style: a pure-LF file must not grow any CR,
    # a pure-CRLF file must not grow any isolated LF.
    eol_damaged = (lone_after > 0) if pure_crlf else (b"\r" in written)
    print("%s: %s -> %s | CRLF %d -> %d | lone LF %d" % (
        path.name, before[:12], after[:12], crlf_before, crlf_after, lone_after,
    ))
    if after == before or eol_damaged:
        raise SystemExit("PATCH_NOT_APPLIED_OR_NEWLINE_DAMAGED %s" % path.name)


def main() -> int:
    apply(ARENA, ARENA_PATCHES)
    apply(FLOW, FLOW_PATCHES)
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
