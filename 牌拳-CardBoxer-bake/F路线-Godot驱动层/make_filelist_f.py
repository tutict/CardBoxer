"""生成 F 路线交付文件清单与新增脚本 diff。

自指纪律：清单本身、diff 本身、logs/ 与 .godot/ 全部排除，
否则「清单写好后重跑」会自己把自己算进去，清单永远不稳定。
用法：python make_filelist_f.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / "文件清单.txt"
DIFF = HERE / "new-files.diff"
EXCLUDE_NAMES = {"文件清单.txt", "new-files.diff"}
EXCLUDE_DIRS = {"logs", ".godot", "__pycache__"}
DIFF_SCRIPTS = [
    "build_rigged_glb.py", "export_rig_frames.py",
    "crosscheck_motion_input.py", "inspect_rigged_glb.py",
    "probe_rig_basis.py", "run_probe_rig.py", "run_probe_drive.py",
    "crosscheck_godot_pose.py", "run_render_f.py", "verify_f.py",
    "mutation_f.py", "make_boards_f.py", "make_filelist_f.py",
    "crosscheck_filelist_f.py", "selftest_did_not_run_f.py",
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def entries() -> list[Path]:
    out = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(HERE)
        if p.name in EXCLUDE_NAMES:
            continue
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        out.append(p)
    return out


def main() -> int:
    rows = []
    for p in entries():
        rel = str(p.relative_to(HERE)).replace("\\", "/")
        rows.append(f"{rel}\t{p.stat().st_size}\t{sha256(p)}")
    header = [
        "# F 路线 · Godot 运行时 14 骨驱动层 · 交付文件清单",
        "# 格式: 相对路径<TAB>字节<TAB>sha256",
        "# 排除: 本清单 / new-files.diff / logs / .godot / __pycache__",
        "",
    ]
    # 二进制写：Windows 下 write_text 会把 \n 转 CRLF，而下面用 bytes
    # 逐字节比对稳定性，两者换行口径不一致会永远报 STABLE=False。
    LIST.write_bytes(("\n".join(header + rows) + "\n").encode("utf-8"))

    parts = []
    for name in DIFF_SCRIPTS:
        p = HERE / name
        if not p.is_file():
            continue
        parts.append(f"===== {name} =====\n" + p.read_text(encoding="utf-8"))
    for rel in ["probe_project_f/project.godot",
                "probe_project_f/probes/probe_rig.gd",
                "probe_project_f/probes/probe_drive.gd",
                "probe_project_f/probes/render_driven.gd",
                "probe_project_f/scenes/rig_driver.gd",
                "probe_project_f/scenes/player_driven.gd",
                "probe_project_f/scenes/player_driven.tscn"]:
        p = HERE / rel
        if p.is_file():
            parts.append(f"===== {rel} =====\n" + p.read_text(encoding="utf-8"))
    DIFF.write_text("\n\n".join(parts) + "\n", encoding="utf-8")

    # 稳定性：同一份清单连写两次内容必须逐字节相同
    again = "\n".join(header + ["%s\t%s\t%s" % (
        str(p.relative_to(HERE)).replace("\\", "/"),
        p.stat().st_size, sha256(p)) for p in entries()]) + "\n"
    stable = LIST.read_bytes() == again.encode("utf-8")
    print(f"FILELIST_ENTRIES={len(rows)} DIFF_BYTES={DIFF.stat().st_size} "
          f"STABLE={stable}")
    print("FILELIST_F_STABLE_OK" if stable else "FILELIST_F_UNSTABLE")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
