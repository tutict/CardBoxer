"""生成 侧身战斗-文件清单.txt；连续生成两次文本必须完全一致（无时间戳自指）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "侧身战斗-文件清单.txt"
SKIP = {OUT.name, "side_battle_stats.json.tmp"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def collect():
    files = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.name in SKIP:
            continue
        rel = p.relative_to(HERE).as_posix()
        if rel.startswith("logs/") or p.suffix == ".pyc" or "__pycache__" in rel:
            continue
        files.append((rel, p.stat().st_size, sha(p)))
    return files


def render(files):
    lines = [
        "《牌拳》KOF 式侧身战斗 · 文件清单",
        "生成：make_filelist.py（连续两次生成文本完全一致 = FILELIST_STABLE_OK）",
        "格式：相对路径 | bytes | sha256",
        "-" * 78,
    ]
    lines += [f"{r} | {b} | {s}" for r, b, s in files]
    lines += ["-" * 78, f"TOTAL {len(files)} files"]
    return "\n".join(lines) + "\n"


def main() -> int:
    a = render(collect())
    b = render(collect())
    OUT.write_text(a, encoding="utf-8")
    stable = a == b and OUT.read_text(encoding="utf-8") == a
    print(f"FILELIST files={len(collect())} chars={len(a)} "
          f"{'FILELIST_STABLE_OK' if stable else 'FILELIST_UNSTABLE'}")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
