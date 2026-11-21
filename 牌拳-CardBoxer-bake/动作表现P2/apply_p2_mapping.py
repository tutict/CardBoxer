"""P2 最小表现层落地：两份 motion_input*.json 的 leg_cap_deg 3.0 -> 9.0。

纪律：
  * 只做一次精确 bytes 替换，锚点在每份文件里必须恰好命中 1 次；
    命中 0 次直接判失败（DID NOT RUN 不静默通过）。
  * 改后 JSON 与 pre-p2 备份做递归逐值 diff，差异路径必须只有
    ["mapping.leg_cap_deg"] 一条 —— 防止顺手改坏别的字段或格式。
  * 14 个受监控文件里除这两份数据外，sha256 必须与 baseline 完全一致。
  * 不改 rig_driver.gd / arena.gd / GLB / card_motion.json。
  * --restore 从 pre-p2 备份逐字节还原，供变异验证与回退使用。

用法：python apply_p2_mapping.py [--restore]
产出：data/apply_p2.json（restore 时写 data/restore_p2.json）
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
ORIG = HERE / "orig" / "pre-p2"
BASELINE = HERE / "data" / "baseline_p2.json"

OLD = b'"leg_cap_deg":3.0'
NEW = b'"leg_cap_deg":9.0'
TO_CHANGE = ("data/motion_input.json", "data/motion_input_foe.json")
NEW_CAP = 9.0


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def diff_paths(a, b, prefix: str = "") -> list[str]:
    """递归逐值比较，返回所有取值不同的路径（只比结构，不比字节）。"""
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


def main() -> int:
    restore = "--restore" in sys.argv
    out = HERE / "data" / ("restore_p2.json" if restore
                           else "apply_p2.json")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    watched = base["files"]
    rows: dict[str, dict] = {}
    checks: dict[str, bool] = {}

    checks["baseline_report_ok"] = (base.get("ok") is True
                                    and all(base.get("checks", {}).values())
                                    and len(watched) == 14)
    checks["baseline_two_to_change"] = (
        base.get("to_change") == list(TO_CHANGE))

    # 备份必须仍是 baseline 当时的字节，否则后续 diff 没有可信真值
    backup_ok = {}
    for rel in TO_CHANGE:
        bp = ORIG / Path(rel).name
        backup_ok[rel] = (bp.is_file()
                          and sha(bp.read_bytes())
                          == watched[rel]["sha256"])
    checks["pre_p2_backups_match_baseline_sha"] = all(backup_ok.values())

    for rel in TO_CHANGE:
        p = GAME / rel
        bp = ORIG / Path(rel).name
        before = p.read_bytes()
        old_json = json.loads(bp.read_bytes().decode("utf-8"))
        rec: dict = {
            "path": str(p),
            "before_sha256": sha(before),
            "baseline_sha256": watched[rel]["sha256"],
            "backup_sha256": sha(bp.read_bytes()),
        }
        if restore:
            # 还原：无条件把备份字节写回，再用哈希证明
            p.write_bytes(bp.read_bytes())
            after = p.read_bytes()
            rec["mode"] = "restore"
            rec["needle_count_new"] = before.count(NEW)
            rec["after_sha256"] = sha(after)
            rec["restored_bytewise"] = (sha(after)
                                        == watched[rel]["sha256"])
            checks[f"{rel}::restored"] = rec["restored_bytewise"]
            checks[f"{rel}::was_shipped_state"] = (
                rec["needle_count_new"] == 1)
        else:
            # 落地：锚点恰好 1 次 + 改前 sha 必须等于 baseline
            n = before.count(OLD)
            rec["mode"] = "apply"
            rec["needle_count_old"] = n
            rec["before_matches_baseline"] = (
                sha(before) == watched[rel]["sha256"])
            if n != 1:
                # 锚点失配绝不静默跳过：直接落一条失败判据
                rec["applied"] = False
                checks[f"{rel}::needle_exactly_once"] = False
                rows[rel] = rec
                continue
            after = before.replace(OLD, NEW, 1)
            p.write_bytes(after)
            got = p.read_bytes()
            new_json = json.loads(got.decode("utf-8"))
            paths = diff_paths(old_json, new_json)
            rec.update({
                "applied": True,
                "after_sha256": sha(got),
                "expected_bytes": sha(after),
                "bytewise_single_replace": got == after,
                "json_parses": True,
                "diff_paths": paths,
                "new_leg_cap_deg": new_json["mapping"]["leg_cap_deg"],
                "old_leg_cap_deg": old_json["mapping"]["leg_cap_deg"],
                "cards_before": len(old_json["cards"]),
                "cards_after": len(new_json["cards"]),
            })
            checks[f"{rel}::needle_exactly_once"] = True
            checks[f"{rel}::before_matches_baseline"] = rec[
                "before_matches_baseline"]
            checks[f"{rel}::bytewise_single_replace"] = (
                rec["bytewise_single_replace"])
            checks[f"{rel}::only_mapping_leg_cap_changed"] = (
                paths == ["mapping.leg_cap_deg"])
            checks[f"{rel}::cap_is_9"] = (
                rec["new_leg_cap_deg"] == NEW_CAP
                and rec["old_leg_cap_deg"] == 3.0)
            checks[f"{rel}::cards_untouched"] = (
                rec["cards_before"] == rec["cards_after"] == 15)
        rows[rel] = rec

    # 两份 mapping 除 apose_points 之外的业务参数仍完全一致
    if not restore and all(r.get("applied") for r in rows.values()):
        js = [json.loads((GAME / rel).read_bytes().decode("utf-8"))
              for rel in TO_CHANGE]
        checks["two_mappings_still_identical"] = (
            js[0]["mapping"] == js[1]["mapping"])
        checks["two_card_tables_still_identical"] = (
            js[0]["cards"] == js[1]["cards"])
        checks["arm_gains_untouched"] = all(
            j["mapping"]["arm_gain_deg"]
            == {"f_upper": 32.0, "f_fore": 26.0,
                "b_upper": 28.0, "b_fore": 22.0} for j in js)
        checks["torso_cap_untouched"] = all(
            j["mapping"]["torso_cap_deg"] == 8.0 for j in js)

    # 其余 12 个受监控文件 sha 必须没变
    others = {}
    for rel, meta in watched.items():
        if rel in TO_CHANGE:
            continue
        p = GAME / rel
        others[rel] = p.is_file() and sha(p.read_bytes()) == meta["sha256"]
    checks["other_12_files_unchanged"] = (len(others) == 12
                                          and all(others.values()))

    report = {
        "game": str(GAME), "mode": "restore" if restore else "apply",
        "old_needle": OLD.decode("ascii"),
        "new_needle": NEW.decode("ascii"),
        "chosen_cap_deg": NEW_CAP,
        "rows": rows, "other_files_unchanged": others,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for rel, r in rows.items():
        print("FILE", rel, r.get("mode"),
              "needle", r.get("needle_count_old",
                              r.get("needle_count_new")),
              "diff", r.get("diff_paths"),
              "sha", r.get("after_sha256", "")[:12])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("APPLY_P2_OK" if report["ok"] else "APPLY_P2_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
