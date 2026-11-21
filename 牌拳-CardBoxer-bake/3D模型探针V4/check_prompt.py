"""prompt 提交前的硬校验：长度上限 + 禁词 + 必备约束。

V1 踩过 1058 > 1024 被服务拒；V2/V3 踩过 glove/boxing 语义簇跑偏。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
text = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
low = text.lower()

FORBIDDEN = [
    "glove", "boxing", "ye shunguang", "yixuan", "zenless", "zzz",
    "叶瞬光", "仪玄", "云岿山", "云岫阁", "fox ear", "animal ear",
    "sheer", "off-shoulder", "cleavage", "stockings", "high heels",
    "sword", "katana", "blade", "logo", "emblem",
]
REQUIRED = [
    "neutral a-pose", "fully covered", "no base", "no weapon",
    "no background", "no text", "single character",
]

hits = [w for w in FORBIDDEN if w in low]
missing = [w for w in REQUIRED if w not in low]
checks = {
    "length_le_1024": len(text) <= 1024,
    "length_gt_400": len(text) > 400,
    "no_forbidden_terms": not hits,
    "all_required_constraints": not missing,
    "ascii_only": text.isascii(),
}
result = {
    "length": len(text),
    "sha256": hashlib.sha256(text.encode()).hexdigest(),
    "forbidden_hits": hits,
    "missing_constraints": missing,
    "checks": checks,
    "verdict": "PROMPT_OK" if all(checks.values()) else "PROMPT_REJECTED",
}
(HERE / "check_prompt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["verdict"] == "PROMPT_OK" else 1)
