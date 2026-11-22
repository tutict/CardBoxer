"""生成可复现的文件清单与新增脚本 diff。

条目数由 build_list() 现算并写进头部，绝不手写数字。
排除两类自指/易变文件：
  · logs/make_filelist_c.log 是生成器自身 stdout 日志（写入中哈希会变）；
  · probe_project/.godot/ 是 Godot 引擎缓存（每次开编辑器都会重写，
    且含时间戳），不是交付物。
生成器在清单生成之后自己写日志，跑时不要把 stdout 重定向进 WORK。

STABLE_OK 只证「两次生成一致」；「清单与实物一致」由独立的
crosscheck_filelist_c.py 逐行重算 size + sha256 并反向查漏项来证明。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / "file-list.txt"
DIFF = HERE / "new-files.diff"
EMPTY = HERE / "logs" / "empty_marker.bin"
EMPTY.parent.mkdir(parents=True, exist_ok=True)
EMPTY.write_bytes(b"")

DIFF_SCRIPTS = [
    "make_baseline_c.py", "probe_blend_structure.py", "export_gltf.py",
    "inspect_gltf.py", "run_godot_import.py", "run_pose_probe.py",
    "make_cost_board.py", "verify_c.py", "mutation_c.py",
    "make_filelist_c.py", "crosscheck_filelist_c.py",
    "probe_project/project.godot",
    "probe_project/probes/inspect_import.gd",
    "probe_project/probes/pose_probe.gd",
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
        if rel in ("file-list.txt", "new-files.diff",
                   "logs/make_filelist_c.log"):
            continue
        if rel.startswith("probe_project/.godot/") or rel.endswith(".tmp"):
            continue
        rows.append(("WORK/" + rel, p))
    return rows


def build_list() -> bytes:
    rows = tracked()
    lines = [
        "《牌拳》C 路线 · glTF → Godot 4.5 导入成本量测 · 文件清单",
        f"条目数由脚本现算：{len(rows)}（WORK=本工作区）",
        "复算命令：python make_filelist_c.py  # 连续生成两次比对 STABLE_OK",
        "排除：probe_project/.godot/ 引擎缓存；logs/make_filelist_c.log 生成器自身日志",
        "",
        f"{'PATH':<80} {'BYTES':>12}  SHA256",
        "-" * 118,
    ]
    for rel, p in rows:
        lines.append(f"{rel:<80} {p.stat().st_size:>12}  {sha256(p)}")
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
    (HERE / "logs" / "make_filelist_c.log").write_bytes(
        summary.encode("utf-8"))
    print(summary, end="")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
