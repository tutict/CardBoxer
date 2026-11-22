"""hud.gd 低血量分支的临时变异 / 逐字节还原工具。

背景：正常对局在 20s 时血量仍在 71/70，触发不到 `r < 0.3` 的危险态，
所以临时把判定改成恒真 `r < 2.0`，用一张满血截图把该分支照出来，
随后立刻按 sha256 逐字节还原。

纪律：全程二进制读写，绝不用 read_text/write_text（会做换行归一化，
看起来还原了其实字节已变）。备份是持久文件 hud_v2.gd，不依赖 %TEMP%。

用法：python hud_mutate.py status | mutate | restore
"""

import hashlib
import sys
from pathlib import Path

HUD = Path(r"D:\Projects\CardBoxer\CardBoxer\scripts\hud.gd")
BACKUP = Path(r"D:\Projects\CardBoxer\CardBoxer-bake\orig\hud_v2.gd")
EXPECTED_V2 = "3c44ed217f39dd7afa3da9cf02b17c5f3b9530c1c26f615f0d6bb0cf36ae8257"
NEEDLE = b"r < 0.3"
MUTANT = b"r < 2.0"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def status() -> None:
    data = HUD.read_bytes()
    print(f"hud.gd sha256   = {sha(data)}")
    print(f"r < 0.3 count   = {data.count(NEEDLE)}")
    print(f"r < 2.0 count   = {data.count(MUTANT)}")
    print(f"size            = {len(data)}")


def mutate() -> None:
    data = HUD.read_bytes()
    if sha(data) != EXPECTED_V2:
        raise SystemExit(f"REFUSE: hud.gd 不是已验证的 V2 版本: {sha(data)}")
    if data.count(NEEDLE) != 2:
        raise SystemExit(f"REFUSE: 锚点数不是 2: {data.count(NEEDLE)}")
    changed = data.replace(NEEDLE, MUTANT)
    if len(changed) != len(data):
        raise SystemExit("REFUSE: 变异改变了文件长度")
    HUD.write_bytes(changed)
    after = HUD.read_bytes()
    print(f"MUTATED sha256  = {sha(after)}")
    print(f"r < 2.0 count   = {after.count(MUTANT)}")
    print(f"r < 0.3 count   = {after.count(NEEDLE)}")
    print("MUTATE_OK")


def restore() -> None:
    data = BACKUP.read_bytes()
    if sha(data) != EXPECTED_V2:
        raise SystemExit(f"REFUSE: 备份不是 V2 版本: {sha(data)}")
    HUD.write_bytes(data)
    actual = sha(HUD.read_bytes())
    print(f"RESTORED sha256 = {actual}")
    if actual != EXPECTED_V2:
        raise SystemExit("RESTORED HASH MISMATCH")
    print("RESTORE_OK")


if __name__ == "__main__":
    {"status": status, "mutate": mutate, "restore": restore}[sys.argv[1]]()
