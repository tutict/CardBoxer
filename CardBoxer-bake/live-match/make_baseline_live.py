"""B 路线 · 落盘基线（纯读盘 + sha256）。

B 路线对游戏工程的既有文件是**零改动**：唯一新增的是
tests/live_match_probe.gd（只读采样探针，游戏运行时不加载）。
因此这里没有 pre-image 备份可做，改用两条可复算的对账：

  * 12 个既有文件的 sha 必须逐字等于 motion-presentation-p2/data/baseline_p2.json；
  * 两份 motion_input*.json 的 sha 必须等于 motion-presentation-p2/data/apply_p2.json
    里记录的 P2 上线后 after_sha256（即 B 路线没把 cap9 改回去）。

证据生成时的探针原字节另存 orig/live_match_probe-evidence.gd，
用于证明 2026-11-15 的注释订正只动注释行。

用法：python make_baseline_live.py
产出：data/baseline_live.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
P2 = BAKE / "motion-presentation-p2" / "data"
OUT = HERE / "data" / "baseline_live.json"
TWO = ("data/motion_input.json", "data/motion_input_foe.json")
WATCHED = (
    "scripts/arena.gd", "scripts/fighter_3d_layer.gd",
    "data/motion_input.json", "data/motion_input_foe.json",
    "scripts/fighter.gd", "scripts/rig_driver.gd",
    "scripts/battle_motion_p0.gd", "scripts/battle_rhythm.gd",
    "scripts/card_motion.gd", "scripts/hud.gd",
    "data/card_motion.json", "project.godot",
    "assets/3d/player-rigged.glb", "assets/3d/foe-rigged.glb",
)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jload(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main() -> int:
    p2_base = jload(P2 / "baseline_p2.json")
    apply_rep = jload(P2 / "apply_p2.json")
    rows = {}
    for rel in WATCHED:
        p = GAME / rel
        rows[rel] = {"exists": p.is_file(),
                     "size": p.stat().st_size if p.is_file() else 0,
                     "sha256": sha(p) if p.is_file() else ""}
    checks = {
        "all_14_watched_exist": all(r["exists"] for r in rows.values()),
        "other_12_sha_equal_p2_baseline": all(
            rows[rel]["sha256"] == p2_base["files"][rel]["sha256"]
            for rel in WATCHED if rel not in TWO),
        "two_motion_tables_equal_p2_applied_sha": all(
            rows[rel]["sha256"]
            == apply_rep["rows"][rel]["after_sha256"] for rel in TWO),
        "shipped_cap_still_9_both": all(
            jload(GAME / rel)["mapping"]["leg_cap_deg"] == 9.0
            for rel in TWO),
        "probe_is_additive_not_in_watched": (
            (GAME / "tests" / "live_match_probe.gd").is_file()
            and "tests/live_match_probe.gd" not in WATCHED),
        "evidence_probe_bytes_preserved": (
            (HERE / "orig" / "live_match_probe-evidence.gd").is_file()),
        "game_probe_matches_source_bytewise": sha(
            GAME / "tests" / "live_match_probe.gd")
        == sha(HERE / "tests" / "live_match_probe.gd"),
    }
    report = {
        "game": str(GAME),
        "files": rows,
        "p2_baseline_source": str(P2 / "baseline_p2.json"),
        "p2_apply_source": str(P2 / "apply_p2.json"),
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("BASELINE_LIVE_OK" if report["ok"] else "BASELINE_LIVE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
