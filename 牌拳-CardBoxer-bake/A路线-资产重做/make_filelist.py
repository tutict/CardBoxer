"""生成可复现的文件清单与新增脚本 diff。

条目数由 build_list() 现算并写进头部，绝不手写数字。
diff 头用 --label 固定；Windows 的 diff.exe 不认字面 /dev/null，
改用真正的 0 字节哨兵文件当输入源（标签仍是 /dev/null）。
清单与 diff 各生成两遍逐字节比对 STABLE_OK。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / "文件清单.txt"
DIFF = HERE / "new-files.diff"
EMPTY = HERE / "logs" / "empty_marker.bin"
EMPTY.parent.mkdir(parents=True, exist_ok=True)
EMPTY.write_bytes(b"")

DIFF_SCRIPTS = [
    "make_baseline.py", "probe_material.py", "probe_surfdeform.py",
    "probe_bake.py", "a_build.py", "analyze_a.py", "make_a_board.py",
    "diag_shard.py", "verify_a.py", "mutation_a.py", "make_filelist.py",
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tracked() -> list[tuple[str, Path]]:
    rows = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(HERE).as_posix()
        # 生成器自己的 stdout 日志自指：若把它计入清单，写入过程中哈希
        # 会变（shell 先截断、进程退出才写完），STABLE_OK 会「一致地」
        # 记下空文件哈希，外部复核必然 MISMATCH。由 main() 在末尾写，
        # 明确排除，并在清单头部注明。
        if rel in ("文件清单.txt", "new-files.diff",
                   "logs/make_filelist.log") or rel.endswith(".tmp"):
            continue
        rows.append(("WORK/" + rel, p))
    return rows


def build_list() -> bytes:
    rows = tracked()
    lines = [
        "《牌拳》A 路线 · 资产重做（Voxel 连续壳 + SURFACE_DEFORM）· 文件清单",
        f"条目数由脚本现算：{len(rows)}（WORK=本工作区）",
        "复算命令：python make_filelist.py  # 连续生成两次比对 STABLE_OK",
        "排除：logs/make_filelist.log 是生成器自身 stdout 日志（自指，写入中哈希会变）",
        "",
        f"{'PATH':<76} {'BYTES':>10}  SHA256",
        "-" * 110,
    ]
    for rel, p in rows:
        lines.append(f"{rel:<76} {p.stat().st_size:>10}  {sha256(p)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_diff() -> bytes:
    chunks = []
    for name in DIFF_SCRIPTS:
        r = subprocess.run(
            ["diff", "-u", "--label", "/dev/null", "--label", "b/" + name,
             str(EMPTY), str(HERE / name)],
            capture_output=True,
        )
        if r.returncode >= 2:
            raise RuntimeError(f"diff failed for {name}: "
                               f"{r.stderr.decode(errors='replace')}")
        chunks.append(r.stdout)
    return b"".join(chunks)


def main() -> int:
    first = [(LIST, build_list()), (DIFF, build_diff())]
    for path, data in first:
        path.write_bytes(data)
    again = [(LIST, build_list()), (DIFF, build_diff())]
    stable = all(a[1] == b[1] for a, b in zip(first, again))
    summary = (f"FILELIST_ENTRIES={len(tracked())}\n"
               f"DIFF_BYTES={DIFF.stat().st_size}\n"
               + ("FILELIST_STABLE_OK\n" if stable
                  else "FILELIST_STABLE_FAILED\n"))
    # 日志在清单生成之后写，且被 tracked() 排除：不会出现「清单记了
    # 半个文件的哈希」。不要用 shell 把 stdout 重定向进这个路径。
    (HERE / "logs" / "make_filelist.log").write_bytes(
        summary.encode("utf-8"))
    print(summary, end="")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
