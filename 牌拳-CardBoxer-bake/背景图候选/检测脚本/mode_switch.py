"""回退验证：临时把 BATTLE_MODE 切到 realtime，跑完原玩法后逐字节还原。

用法：python mode_switch.py mutate | restore <期望sha256>
只改一个等长可反解的字节串；restore 按外部传入的 sha256 核对，不靠 %TEMP%。
"""

import hashlib
import sys
from pathlib import Path

ARENA = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer\scripts\arena.gd")
A = b'const BATTLE_MODE := "taikou"'
B = b'const BATTLE_MODE := "realtime"'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    mode = sys.argv[1]
    data = ARENA.read_bytes()
    if mode == "mutate":
        assert data.count(A) == 1, "taikou 开关锚点应恰好 1 处"
        ARENA.write_bytes(data.replace(A, B, 1))
        print(f"MUTATED  -> realtime, sha256={sha(ARENA.read_bytes())}")
    elif mode == "restore":
        expected = sys.argv[2]
        assert data.count(B) == 1, "realtime 开关锚点应恰好 1 处"
        ARENA.write_bytes(data.replace(B, A, 1))
        actual = sha(ARENA.read_bytes())
        print(f"RESTORED -> taikou,   sha256={actual}")
        assert actual == expected, f"RESTORED HASH MISMATCH: 期望 {expected}"
        print("RESTORE_OK")
    else:
        raise SystemExit("用法: mode_switch.py mutate | restore <sha256>")


if __name__ == "__main__":
    main()
