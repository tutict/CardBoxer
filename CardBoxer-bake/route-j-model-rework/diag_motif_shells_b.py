"""B 路线 P1 返工：用 UV 贴图特征反查「青冠/红花/白布青云纹」所在的壳。

P0 按空间区域分组，删掉了背面大披风 / 中间倒三角布 / 头顶圆顶，
但引擎内 j-sv-foe.png 里青结晶冠 + 红花 + 长白布青云纹仍在，
说明这些显眼的 V4b 装饰是**另外的壳**，散在 G4_BODY 里。

本脚本用 probe_shell_isolate_b.py 已经逐壳算好的 UV 采样分数
（cyan_ratio / warm_ratio / lin_luma）找候选，按位置分成三组：
  HEAD_ORNAMENT  z>1.40 且 cyan/warm 高
  LOWER_WHITE    z<1.00 且 lin_luma 高
  TRAILING_STRIP 侧视那条碎片（用 z 跨度 + 窄 x/y 辅助）

只读，输出 data/motif_shells_b.json 与候选壳 ID 清单。
用法：python diag_motif_shells_b.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ISOLATE = HERE / "data" / "shell_isolate_b.json"
TARGETS = HERE / "data" / "shell_targets_b.json"
OUT = HERE / "data" / "motif_shells_b.json"

CYAN_MIN = 0.10
WARM_MIN = 0.08
LUMA_MIN = 0.16


def top(rows, key, n=25):
    return sorted(rows, key=lambda r: -r["tex"][key])[:n]


def brief(r):
    return {
        "shell_id": r["shell_id"], "verts": r["verts"],
        "group": r["group"], "region": r["region"],
        "centroid": r["centroid"], "lo": r["lo"], "hi": r["hi"],
        "uv_bbox": r["uv_bbox"], "tex": r["tex"],
    }


def main() -> int:
    iso = json.loads(ISOLATE.read_text(encoding="utf-8"))
    tg = json.loads(TARGETS.read_text(encoding="utf-8"))
    deleted = set(tg["target_shell_ids"])
    all_rows = iso["shells_table"]
    live = [r for r in all_rows if r["shell_id"] not in deleted]

    cyan = [r for r in top(live, "cyan_ratio", 400)
            if r["tex"]["cyan_ratio"] >= CYAN_MIN]
    warm = [r for r in top(live, "warm_ratio", 400)
            if r["tex"]["warm_ratio"] >= WARM_MIN]
    bright = [r for r in top(live, "lin_luma", 400)
              if r["tex"]["lin_luma"] >= LUMA_MIN]

    head_cyan = [r for r in cyan if r["centroid"][2] > 1.40]
    head_warm = [r for r in warm if r["centroid"][2] > 1.40]
    lower_bright = [r for r in bright if r["centroid"][2] < 1.00]

    stats = {
        "live_shells": len(live),
        "cyan_over_threshold": len(cyan),
        "warm_over_threshold": len(warm),
        "bright_over_threshold": len(bright),
        "head_cyan": len(head_cyan), "head_warm": len(head_warm),
        "lower_bright": len(lower_bright),
        "thresholds": {"cyan_min": CYAN_MIN, "warm_min": WARM_MIN,
                       "luma_min": LUMA_MIN},
    }
    report = {
        "source": str(ISOLATE), "already_deleted": len(deleted),
        "stats": stats,
        "head_cyan_top": [brief(r) for r in top(head_cyan,
                                                "cyan_ratio", 20)],
        "head_warm_top": [brief(r) for r in top(head_warm,
                                                "warm_ratio", 20)],
        "lower_bright_top": [brief(r) for r in top(lower_bright,
                                                   "lin_luma", 20)],
        "candidate_ids": sorted(set(
            [r["shell_id"] for r in head_cyan]
            + [r["shell_id"] for r in head_warm]
            + [r["shell_id"] for r in lower_bright])),
    }
    report["candidate_count"] = len(report["candidate_ids"])
    report["ok"] = (len(head_cyan) + len(head_warm)
                    + len(lower_bright)) > 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("STATS", stats)
    for label, rows in (("HEAD_CYAN", head_cyan), ("HEAD_WARM", head_warm),
                        ("LOWER_BRIGHT", lower_bright)):
        print("---", label, len(rows), "---")
        for r in top(rows, "lin_luma", 8):
            print(" ", r["shell_id"], "v", r["verts"],
                  "z", round(r["centroid"][2], 3),
                  "cyan", r["tex"]["cyan_ratio"],
                  "warm", r["tex"]["warm_ratio"],
                  "luma", r["tex"]["lin_luma"])
    print("CANDIDATES", report["candidate_count"])
    print("MOTIF_SHELLS_B_OK" if report["ok"]
          else "MOTIF_SHELLS_B_EMPTY")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
