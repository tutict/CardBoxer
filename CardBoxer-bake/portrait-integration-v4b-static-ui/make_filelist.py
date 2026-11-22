"""生成可复现的文件清单与源码 diff。

用 `diff -u --label /dev/null --label <rel>` 固定头部，避免裸
`diff -u /dev/null <file>` 把 /dev/null 的当前时间戳写进 diff 头导致
两次生成不一致。清单与 diff 各生成两遍并逐字节比对。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
BACKUP = HERE / "orig" / "pre-portrait-ui"
LIST = HERE / "file-list.txt"
DIFF = HERE / "new-files.diff"

GAME_FILES = [
    "scripts/hud.gd",
    "tests/redraw_gate_check.gd",
    "tests/portrait_wiring_check.gd",
    "tests/portrait_shot_probe.gd",
    "assets/portraits/manifest.json",
]
PORTRAIT_NAMES = [
    "card_p1.png", "card_p55.png", "avatar_player.png", "avatar_foe.png",
    "profile_front.png", "profile_25.png", "profile_55.png", "profile_back35.png",
]
GAME_FILES += [f"assets/portraits/{n}" for n in PORTRAIT_NAMES]
GAME_FILES += [f"assets/portraits/{n}.import" for n in PORTRAIT_NAMES]

# Windows 的 diff.exe 不认字面 /dev/null（会被解析成 \dev\null），
# 用真正的 0 字节哨兵文件当输入源，标签仍固定为 /dev/null。
EMPTY = HERE / "logs" / "empty_marker.bin"
EMPTY.parent.mkdir(parents=True, exist_ok=True)
EMPTY.write_bytes(b"")

DIFF_PAIRS = [
    (BACKUP / "scripts" / "hud.gd", GAME / "scripts" / "hud.gd",
     "a/scripts/hud.gd", "b/scripts/hud.gd"),
    (BACKUP / "tests" / "redraw_gate_check.gd", GAME / "tests" / "redraw_gate_check.gd",
     "a/tests/redraw_gate_check.gd", "b/tests/redraw_gate_check.gd"),
    (EMPTY, GAME / "tests" / "portrait_wiring_check.gd",
     "/dev/null", "b/tests/portrait_wiring_check.gd"),
    (EMPTY, GAME / "tests" / "portrait_shot_probe.gd",
     "/dev/null", "b/tests/portrait_shot_probe.gd"),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tracked() -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(HERE).as_posix()
        if rel in ("file-list.txt", "new-files.diff") or rel.endswith("hud_current_bytes.tmp"):
            continue
        rows.append(("WORK/" + rel, p))
    for rel in GAME_FILES:
        p = GAME / rel
        if p.is_file():
            rows.append(("GAME/" + rel, p))
    return sorted(rows, key=lambda r: r[0])


def build_list() -> bytes:
    rows = tracked()
    lines = [
        "《牌拳》V4b 立绘接入静态 UI 位 · 文件清单",
        f"条目数由脚本现算：{len(rows)}（WORK=工作区 / GAME=可运行工程）",
        "复算命令：python make_filelist.py  # 连续生成两次比对 STABLE_OK",
        "",
        f"{'PATH':<76} {'BYTES':>10}  SHA256",
        "-" * 110,
    ]
    for rel, p in rows:
        lines.append(f"{rel:<76} {p.stat().st_size:>10}  {sha256(p)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_diff() -> bytes:
    chunks = []
    for old, new, label_old, label_new in DIFF_PAIRS:
        r = subprocess.run(
            ["diff", "-u", "--label", label_old, "--label", label_new,
             str(old), str(new)],
            capture_output=True,
        )
        # diff 退出码 1 = 有差异，属正常；>=2 才是真错误
        if r.returncode >= 2:
            raise RuntimeError(f"diff failed for {label_new}: {r.stderr.decode(errors='replace')}")
        chunks.append(r.stdout)
    return b"".join(chunks)


def main() -> None:
    pairs = [(LIST, build_list()), (DIFF, build_diff())]
    for path, data in pairs:
        path.write_bytes(data)
    again = [(LIST, build_list()), (DIFF, build_diff())]
    stable = all(a[1] == b[1] for a, b in zip(pairs, again))
    print(f"FILELIST_ENTRIES={len(tracked())}")
    print(f"DIFF_BYTES={DIFF.stat().st_size}")
    print("FILELIST_STABLE_OK" if stable else "FILELIST_STABLE_FAILED")


if __name__ == "__main__":
    main()
