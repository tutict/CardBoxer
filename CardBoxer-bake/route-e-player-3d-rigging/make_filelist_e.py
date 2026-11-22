"""生成 E 路线可复现的文件清单与新增脚本 diff。

条目数由 build_list() 现算并写进头部，绝不手写数字。
排除：
  · probe_project_e/.godot/ 引擎缓存（含时间戳，每次开编辑器会重写）；
  · logs/make_filelist_e.log 是生成器自身 stdout（写入中哈希会变）；
  · 清单与 diff 自身。
STABLE_OK 只证「两次生成一致」；「与实物一致」由独立的
crosscheck_filelist_e.py 逐行重算 size + sha256 并反向查漏项证明。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / "file-list.txt"
DIFF = HERE / "new-files-e.diff"
EMPTY = HERE / "logs" / "empty_marker_e.bin"
EMPTY.parent.mkdir(parents=True, exist_ok=True)
EMPTY.write_bytes(b"")

DIFF_SCRIPTS = [
    "make_baseline_e.py", "probe_v4b_source.py", "e_build.py",
    "render_e_x1.py", "analyze_e.py", "export_e_gltf.py",
    "inspect_e_gltf.py", "run_godot_e.py", "make_boards_e.py",
    "verify_e.py", "mutation_e.py", "make_filelist_e.py",
    "crosscheck_filelist_e.py",
    "probe_project_e/project.godot",
    "probe_project_e/probes/inspect_e.gd",
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
        if rel in ("file-list.txt", "new-files-e.diff",
                   "logs/make_filelist_e.log"):
            continue
        if rel.startswith("probe_project_e/.godot/") or rel.endswith(".tmp"):
            continue
        rows.append(("WORK/" + rel, p))
    return rows


def build_list() -> bytes:
    rows = tracked()
    lines = [
        "《牌拳》E 路线 · 玩家 V4b 3D 绑骨 / glTF-Godot 读回 · 文件清单",
        f"条目数由脚本现算：{len(rows)}（WORK=本工作区）",
        "复算命令：python make_filelist_e.py  # 连续生成两次比对 STABLE_OK",
        "排除：probe_project_e/.godot/ 引擎缓存；"
        "logs/make_filelist_e.log 生成器自身日志",
        "",
        f"{'PATH':<84} {'BYTES':>12}  SHA256",
        "-" * 122,
    ]
    for rel, p in rows:
        lines.append(f"{rel:<84} {p.stat().st_size:>12}  {sha256(p)}")
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
    (HERE / "logs" / "make_filelist_e.log").write_bytes(
        summary.encode("utf-8"))
    print(summary, end="")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
