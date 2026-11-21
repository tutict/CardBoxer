"""B 路线 P1 返工：生成第二轮补删壳 ID（青结晶冠 + 青云纹）。

引擎内 j-sv-foe.png 里仍可见青结晶头冠、红花与腿前白布青云纹。
数据反查（diag_motif_shells_b.py）：P0 的 HEAD_TOP 阈值 cz>1.48
把 z≈1.44 的 44 个高青小壳判进了 BODY，所以 G2 没删到它们。

补删规则（按 UV 贴图颜色特征，不按区域名）：
  HEAD_CYAN  centroid_z > 1.40 且 cyan_ratio >= 0.10
  LOWER_CYAN centroid_z <= 1.40 且 cyan_ratio >= 0.10
  两者都要求 verts <= 300（只删装饰小壳，不碰躯干大壳）
  并排除 shell_targets_b.json 已删的 195 个壳。

输出 data/extra_targets_b.json，供 build_shape_b.py 合并目标集。
用法：python make_extra_targets_b.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ISOLATE = HERE / "data" / "shell_isolate_b.json"
TARGETS = HERE / "data" / "shell_targets_b.json"
OUT = HERE / "data" / "extra_targets_b.json"

CYAN_MIN = 0.10
HEAD_Z = 1.40
VERTS_MAX = 300


def main() -> int:
    iso = json.loads(ISOLATE.read_text(encoding="utf-8"))
    tg = json.loads(TARGETS.read_text(encoding="utf-8"))
    deleted = set(tg["target_shell_ids"])
    by_id = {r["shell_id"]: r for r in iso["shells_table"]}
    head, lower = [], []
    for r in iso["shells_table"]:
        sid = r["shell_id"]
        if sid in deleted or r["verts"] > VERTS_MAX:
            continue
        if r["tex"]["cyan_ratio"] < CYAN_MIN:
            continue
        (head if r["centroid"][2] > HEAD_Z else lower).append(sid)
    head.sort()
    lower.sort()
    ids = sorted(set(head) | set(lower))
    checks = {
        "isolate_probe_ok": iso["ok"] and not iso["failed"],
        "targets_probe_ok": tg["ok"] and not tg["failed"],
        "no_overlap_with_round1": not (set(ids) & deleted),
        "all_ids_in_table": all(i in by_id for i in ids),
        "head_cyan_found": len(head) > 0,
        "lower_cyan_found": len(lower) > 0,
        "all_are_small_shells": all(
            by_id[i]["verts"] <= VERTS_MAX for i in ids),
        "all_have_cyan_uv": all(
            by_id[i]["tex"]["cyan_ratio"] >= CYAN_MIN for i in ids),
    }
    report = {
        "source": str(ISOLATE), "round1": str(TARGETS),
        "rule": {"cyan_min": CYAN_MIN, "head_z": HEAD_Z,
                 "verts_max": VERTS_MAX},
        "head_cyan_ids": head, "lower_cyan_ids": lower,
        "extra_ids": ids,
        "counts": {"head_cyan": len(head), "lower_cyan": len(lower),
                   "total": len(ids),
                   "verts": sum(by_id[i]["verts"] for i in ids)},
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
    }
    report["ok"] = not report["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("COUNTS", report["counts"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("EXTRA_TARGETS_B_OK" if report["ok"]
          else "EXTRA_TARGETS_B_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
