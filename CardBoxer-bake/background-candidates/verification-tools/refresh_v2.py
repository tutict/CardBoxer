"""核对 hud.gd 的字节/换行风格，并在确认后刷新 V2 持久备份。

游戏目录不是 git 仓库，编辑后没有 diff 兜底，所以这里直接看字节：
新增注释若被写成孤立 LF（而原文件是 CRLF），会污染整份文件。
用法：python refresh_v2.py check | commit
"""

import hashlib
import shutil
import sys
from pathlib import Path

HUD = Path(r"D:\Projects\CardBoxer\CardBoxer\scripts\hud.gd")
BACKUP = Path(r"D:\Projects\CardBoxer\CardBoxer-bake\orig\hud_v2.gd")


def eol(data: bytes) -> tuple[int, int, int]:
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    return crlf, lf - crlf, lf


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    data = HUD.read_bytes()
    old = BACKUP.read_bytes()
    print(f"current : size={len(data)} sha256={sha(data)} CRLF/loneLF/LF={eol(data)}")
    print(f"backup  : size={len(old)} sha256={sha(old)} CRLF/loneLF/LF={eol(old)}")

    dc, dl, _ = eol(data)
    oc, ol, _ = eol(old)
    print(f"\nCRLF delta={dc - oc}, loneLF delta={dl - ol}")
    if oc == 0:
        # 纯 LF 文件：新增行本来就该是 LF，只要别冒出 CRLF 就行。
        line_ok = dc == 0
        print("原文件是纯 LF；判据是新文件仍为纯 LF")
    else:
        # 含 CRLF 的文件：新增行不能是孤立 LF。
        line_ok = dl == ol
        print("原文件含 CRLF；判据是不新增孤立 LF")
    print("EOL_OK" if line_ok else "WARN: 换行风格被污染，应改用二进制替换重建")

    if sys.argv[1] == "commit":
        if not line_ok:
            raise SystemExit("REFUSE: 换行被污染，不刷新备份")
        shutil.copyfile(HUD, BACKUP)
        print(f"\nBACKUP_REFRESHED sha256={sha(BACKUP.read_bytes())}")


if __name__ == "__main__":
    main()
