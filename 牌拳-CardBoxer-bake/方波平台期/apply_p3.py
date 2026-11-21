"""P3 · 落地「atan 软限幅」最小改动（可逐字节回退）。

改 3 个文件：
  scripts/rig_driver.gd —— 新增 _leg() 分派 + leg_mode 读取 + 4 行腿骨调用；
  data/motion_input.json / motion_input_foe.json
                        —— mapping.leg_cap_deg 9→12（软限幅渐近参数，
                           不是硬上限）+ 新增 mapping.leg_mode = "atan"。

兼容性：_leg() 默认 "hard"；mapping 里没有 leg_mode 的旧动作表
（P2 备份、历史归档）配新驱动仍走硬 clamp，行为与 P2 逐值相同。

纪律：
  * 全部用二进制替换，needle 必须恰好命中 1 次；不碰中文注释与换行；
  * 落盘前备份 3 个原字节 + 记录 14 个受监控文件 sha256 基线；
  * JSON 递归逐值 diff 只允许 mapping.leg_cap_deg / mapping.leg_mode 两条；
  * --restore 用备份二进制覆盖，sha256 证明逐字节回退。

用法：python apply_p3.py [--restore]
产出：orig/pre-p3/*、data/baseline_p3.json、data/apply_p3.json
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
ORIG = HERE / "orig" / "pre-p3"
BASE_OUT = HERE / "data" / "baseline_p3.json"
OUT = HERE / "data" / "apply_p3.json"
TO_CHANGE = (
    "scripts/rig_driver.gd",
    "data/motion_input.json",
    "data/motion_input_foe.json",
)
WATCHED = (
    "scripts/arena.gd", "scripts/fighter_3d_layer.gd",
    "data/motion_input.json", "data/motion_input_foe.json",
    "scripts/fighter.gd", "scripts/rig_driver.gd",
    "scripts/battle_motion_p0.gd", "scripts/battle_rhythm.gd",
    "scripts/card_motion.gd", "scripts/hud.gd",
    "data/card_motion.json", "project.godot",
    "assets/3d/player-rigged.glb", "assets/3d/foe-rigged.glb",
)

HELPER = (
    "## 腿骨映射：hard 是 P2 上线的硬 clamp，atan 是 P3 的软限幅。\n"
    "## mapping 没有 leg_mode 时回落 hard，旧动作表配新驱动行为不变。\n"
    "func _leg(x: float, cap: float, mode: String) -> float:\n"
    "\tif mode == \"atan\":\n"
    "\t\treturn cap * (2.0 / PI) * atan((PI / 2.0) * x / cap)\n"
    "\treturn clampf(x, -cap, cap)\n\n\n"
).encode("utf-8")

RD_REPLACEMENTS = [
    (b"func retarget_delta(frame_j: Dictionary) -> Dictionary:\n",
     HELPER + b"func retarget_delta(frame_j: Dictionary) -> Dictionary:\n"),
    (b'var leg_cap := float(mapping["leg_cap_deg"])\n',
     b'var leg_cap := float(mapping["leg_cap_deg"])\n'
     b'\tvar leg_mode: String = String(mapping.get("leg_mode", "hard"))\n'),
    (b'\t\t"thigh_f": clampf(float(raw["thigh_f"]), -leg_cap, leg_cap),\n'
     b'\t\t"shin_f": clampf(float(raw["shin_f"]), -leg_cap, leg_cap),\n'
     b'\t\t"thigh_b": clampf(float(raw["thigh_b"]), -leg_cap, leg_cap),\n'
     b'\t\t"shin_b": clampf(float(raw["shin_b"]), -leg_cap, leg_cap),\n',
     b'\t\t"thigh_f": _leg(float(raw["thigh_f"]), leg_cap, leg_mode),\n'
     b'\t\t"shin_f": _leg(float(raw["shin_f"]), leg_cap, leg_mode),\n'
     b'\t\t"thigh_b": _leg(float(raw["thigh_b"]), leg_cap, leg_mode),\n'
     b'\t\t"shin_b": _leg(float(raw["shin_b"]), leg_cap, leg_mode),\n'),
]
JSON_NEEDLE = b'"leg_cap_deg":9.0}'
JSON_MUTANT = b'"leg_cap_deg":12.0,"leg_mode":"atan"}'


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def diff_paths(a, b, prefix: str = "") -> list[str]:
    if type(a) is not type(b):
        return [prefix or "<root>"]
    if isinstance(a, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            p = f"{prefix}.{k}" if prefix else k
            if k not in a or k not in b:
                out.append(p)
            else:
                out.extend(diff_paths(a[k], b[k], p))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [prefix or "<root>"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(diff_paths(x, y, f"{prefix}[{i}]"))
        return out
    return [] if a == b else [prefix or "<root>"]


def backup_name(rel: str) -> str:
    return Path(rel).name


def do_restore() -> int:
    rows = {}
    ok = True
    for rel in TO_CHANGE:
        src, dst = ORIG / backup_name(rel), GAME / rel
        if not src.is_file():
            print("MISSING BACKUP", src)
            return 1
        shutil.copyfile(src, dst)
        rows[rel] = sha(dst) == sha(src)
        ok = ok and rows[rel]
        print("RESTORE", rel, rows[rel])
    print("RESTORE_P3_OK" if ok else "RESTORE_P3_FAILED")
    return 0 if ok else 1


def main() -> int:
    if "--restore" in sys.argv:
        return do_restore()
    ORIG.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # 1) 备份 + 14 文件 sha 基线
    for rel in TO_CHANGE:
        shutil.copyfile(GAME / rel, ORIG / backup_name(rel))
    baseline_files = {}
    for rel in WATCHED:
        p = GAME / rel
        baseline_files[rel] = {"exists": p.is_file(),
                               "size": p.stat().st_size if p.is_file() else 0,
                               "sha256": sha(p) if p.is_file() else ""}
    baseline = {"game": str(GAME), "to_change": list(TO_CHANGE),
                "files": baseline_files,
                "backups": {r: str(ORIG / backup_name(r))
                            for r in TO_CHANGE},
                "checks": {
                    "all_14_watched_exist": all(
                        v["exists"] for v in baseline_files.values()),
                    "three_backups_match_live_sha": all(
                        sha(ORIG / backup_name(r)) == sha(GAME / r)
                        for r in TO_CHANGE),
                }}
    baseline["ok"] = all(baseline["checks"].values())
    BASE_OUT.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    # 2) 二进制替换
    rows, all_ok = {}, True
    rd_path = GAME / "scripts" / "rig_driver.gd"
    before_rd = rd_path.read_bytes()
    after_rd = before_rd
    rd_counts = []
    for needle, mutant in RD_REPLACEMENTS:
        n = after_rd.count(needle)
        rd_counts.append(n)
        if n == 1:
            after_rd = after_rd.replace(needle, mutant, 1)
    rd_ok = all(c == 1 for c in rd_counts)
    if rd_ok:
        rd_path.write_bytes(after_rd)
    rows["scripts/rig_driver.gd"] = {
        "needle_counts": rd_counts,
        "bytewise_single_replace_each": rd_ok,
        "before_sha256": sha(ORIG / "rig_driver.gd"),
        "after_sha256": sha(rd_path) if rd_ok else "",
        "line_diff": list(difflib.unified_diff(
            before_rd.decode("utf-8").splitlines(),
            after_rd.decode("utf-8").splitlines(),
            lineterm="", n=0))[:40],
    }
    all_ok = all_ok and rd_ok

    for rel in ("data/motion_input.json", "data/motion_input_foe.json"):
        p = GAME / rel
        before = p.read_bytes()
        n = before.count(JSON_NEEDLE)
        after = before.replace(JSON_NEEDLE, JSON_MUTANT, 1) if n == 1 \
            else before
        if n == 1:
            p.write_bytes(after)
        bj = json.loads((ORIG / backup_name(rel)).read_text(
            encoding="utf-8"))
        aj = json.loads(p.read_text(encoding="utf-8"))
        paths = diff_paths(bj, aj)
        rows[rel] = {
            "needle_count": n,
            "bytewise_single_replace": n == 1,
            "before_sha256": sha(ORIG / backup_name(rel)),
            "after_sha256": sha(p),
            "diff_paths": paths,
            "leg_cap_deg": aj["mapping"]["leg_cap_deg"],
            "leg_mode": aj["mapping"].get("leg_mode"),
            "cards": len(aj["cards"]),
            "frames": sum(int(c["frames"]) for c in aj["cards"].values()),
        }
        all_ok = all_ok and (n == 1 and paths
                             == ["mapping.leg_cap_deg", "mapping.leg_mode"]
                             and aj["mapping"]["leg_cap_deg"] == 12.0
                             and aj["mapping"]["leg_mode"] == "atan")

    # 3) 其余 11 个受监控文件必须逐字节未动
    untouched = {rel: sha(GAME / rel)
                 == baseline_files[rel]["sha256"]
                 for rel in WATCHED if rel not in TO_CHANGE}
    checks = {
        "baseline_ok": baseline["ok"],
        "rig_driver_three_replacements_each_once": rd_ok,
        "two_json_single_replace": all(
            rows[r]["bytewise_single_replace"]
            for r in ("data/motion_input.json",
                      "data/motion_input_foe.json")),
        "two_json_only_two_diff_paths": all(
            rows[r]["diff_paths"]
            == ["mapping.leg_cap_deg", "mapping.leg_mode"]
            for r in ("data/motion_input.json",
                      "data/motion_input_foe.json")),
        "both_mappings_identical": (
            json.loads((GAME / "data/motion_input.json").read_text(
                encoding="utf-8"))["mapping"]
            == json.loads((GAME / "data/motion_input_foe.json").read_text(
                encoding="utf-8"))["mapping"]),
        "cards_still_15_284": all(
            rows[r]["cards"] == 15 and rows[r]["frames"] == 284
            for r in ("data/motion_input.json",
                      "data/motion_input_foe.json")),
        "other_11_watched_files_unchanged": all(untouched.values()),
    }
    report = {"mode": "apply", "game": str(GAME), "rows": rows,
              "untouched": untouched, "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values()) and all_ok}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("APPLY_P3_OK" if report["ok"] else "APPLY_P3_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
