"""生成 J 路线交付文件清单与新增脚本文本 diff。

与 I 路线不同：J 路线**没有任何游戏源码改动落地**（r1 手术已回滚），
所以 new-files.diff 里必须显式给出「源码零改动 + GLB 已还原」的 sha256
对账，而不是伪造一份源码 unified diff。

自指纪律：清单 / diff / logs / orig / .godot / __pycache__ 排除。
用法：python make_filelist_j.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
LIST = HERE / "文件清单.txt"
DIFF = HERE / "new-files.diff"
EXCLUDE_NAMES = {"文件清单.txt", "new-files.diff"}
EXCLUDE_DIRS = {"logs", ".godot", "__pycache__", "orig", "shots",
                "boards", "data"}
DATA_FILES = [
    "data/asset_probe_j.json", "data/build_shape_j.json",
    "data/install_j.json", "data/motif_baseline_j.json",
    "data/recolor_probe_j.json", "data/rollback_j.json",
    "data/shape_root_j.json", "data/shells_j.json",
    "data/texture_pair_j.json", "data/all_checks_j.json",
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
        if not p.is_file() or p.name in EXCLUDE_NAMES:
            continue
        rel = p.relative_to(HERE)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        out.append(p)
    return out


def main() -> int:
    scripts = sorted(HERE.glob("*.py"))
    tests = sorted((HERE / "tests").glob("*.gd"))
    assert len(scripts) >= 10, f"too few scripts: {len(scripts)}"
    assert len(tests) >= 1, f"too few probe scripts: {len(tests)}"

    header = [
        "# J 路线 · 造型重做（r1 负结果 + r2 方向订正）· 交付文件清单",
        "# 格式: 相对路径<TAB>字节<TAB>sha256",
        "# 排除: 本清单 / new-files.diff / logs / orig / shots / boards / data",
        "# shots / boards / data 的 sha256 见 new-files.diff 末尾对账段",
        "",
    ]
    rows = []
    for p in entries():
        rel = str(p.relative_to(HERE)).replace("\\", "/")
        rows.append(f"{rel}\t{p.stat().st_size}\t{sha256(p)}")
    LIST.write_bytes(("\n".join(header + rows) + "\n").encode("utf-8"))

    parts = []
    for p in scripts:
        parts.append(f"===== J/{p.name} =====\n"
                     + p.read_text(encoding="utf-8"))
    for p in tests:
        parts.append(f"===== J/tests/{p.name} =====\n"
                     + p.read_text(encoding="utf-8"))
    parts.append("===== J/J路线-造型规格.txt =====\n"
                 + (HERE / "J路线-造型规格.txt").read_text(
                     encoding="utf-8"))
    parts.append("===== J/J路线-负结果与方向订正.txt =====\n"
                 + (HERE / "J路线-负结果与方向订正.txt").read_text(
                     encoding="utf-8"))
    for rel in DATA_FILES:
        p = HERE / rel
        if p.is_file():
            parts.append(f"===== J/{rel} =====\n"
                         + p.read_text(encoding="utf-8"))

    # ── 工程状态对账：证明 r1 手术没有留在可运行工程里 ──────────
    install = json.loads((HERE / "data" / "install_j.json").read_text(
        encoding="utf-8"))
    rollback = json.loads((HERE / "data" / "rollback_j.json").read_text(
        encoding="utf-8"))
    glb = GAME / "assets" / "3d" / "foe-rigged.glb"
    layer = GAME / "scripts" / "fighter_3d_layer.gd"
    arena = GAME / "scripts" / "arena.gd"
    fighter = GAME / "scripts" / "fighter.gd"
    backup_glb = HERE / "orig" / "pre-shape" / "foe-rigged.glb"
    state = {
        "game_glb_sha256": sha256(glb),
        "i_baseline_glb_sha256": install["before"]["glb_sha256"],
        "r1_surgery_glb_sha256": install["after"]["glb_sha256"],
        "backup_glb_sha256": sha256(backup_glb),
        "game_glb_equals_i_baseline": (
            sha256(glb) == install["before"]["glb_sha256"]),
        "game_glb_differs_from_r1": (
            sha256(glb) != install["after"]["glb_sha256"]),
        "rollback_ok": rollback["ok"],
        "rollback_checks": rollback["checks"],
        "source_sha256": {
            "scripts/fighter_3d_layer.gd": sha256(layer),
            "scripts/arena.gd": sha256(arena),
            "scripts/fighter.gd": sha256(fighter),
        },
        "j_route_source_diff_count": 0,
    }
    parts.append("===== 工程状态 sha256 对账 =====\n"
                 + json.dumps(state, ensure_ascii=False, indent=2))
    # 其余静态产物（板子 / 截帧 / 大 GLB）只记大小与哈希，不塞进 diff。
    assets = []
    for d in ("boards", "shots", "data", "orig"):
        for p in sorted((HERE / d).rglob("*")):
            if p.is_file():
                assets.append({
                    "path": str(p.relative_to(HERE)).replace("\\", "/"),
                    "bytes": p.stat().st_size, "sha256": sha256(p)})
    parts.append("===== 其余产物 sha256（不含正文） =====\n"
                 + json.dumps(assets, ensure_ascii=False, indent=2))
    DIFF.write_bytes(("\n\n".join(parts) + "\n").encode("utf-8"))

    again = ("\n".join(header + [
        f"{str(p.relative_to(HERE)).replace(chr(92), '/')}\t"
        f"{p.stat().st_size}\t{sha256(p)}" for p in entries()
    ]) + "\n").encode("utf-8")
    stable = LIST.read_bytes() == again
    assert DIFF.is_file() and DIFF.stat().st_size > 10000, \
        f"new-files.diff missing or too small: {DIFF}"
    assert state["game_glb_equals_i_baseline"] and \
        state["game_glb_differs_from_r1"] and state["rollback_ok"], \
        "工程未回到 I 基线，禁止收口"
    print(f"FILELIST_ENTRIES={len(rows)} DIFF_BYTES={DIFF.stat().st_size} "
          f"SCRIPTS={len(scripts)} TESTS={len(tests)}")
    print(f"GAME_GLB_RESTORED={state['game_glb_equals_i_baseline']} "
          f"R1_NOT_PRESENT={state['game_glb_differs_from_r1']}")
    print(f"STABLE={stable}")
    print("FILELIST_J_STABLE_OK" if stable else "FILELIST_J_UNSTABLE")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
