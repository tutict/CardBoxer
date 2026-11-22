"""对手怪 prompt 提交前的硬校验：长度 + 禁词 + 必备造型约束。

沿用 V1~V4b 的教训：
  * V1 踩过 1058 > 1024 被服务拒，长度必须校验。
  * V5 踩过反复前置 glove/boxing 把语义簇推到男性中式道服 ——
    本轮连否定式也不写这两个词，用 hand wraps / bracers 代替。
  * 不复刻具体 IP 条目：敌人专名 / 阵营名 / 角色名一律禁。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
text = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
low = text.lower()

FORBIDDEN = [
    # 语义簇地雷
    "glove", "boxing", "gloves",
    # IP / 具体条目，不复刻
    "zenless", "zzz", "hollow thug", "rampant brute", "poacher",
    "ye shunguang", "yixuan", "叶瞬光", "仪玄", "云岿山", "云岫阁",
    "山狮", "瑞扎", "怒汉", "盗洞暴徒", "logo", "emblem",
    # 武器（《牌拳》的武器是卡牌）
    "sword", "katana", "blade", "crossbow", "arrow", "spear", "hammer", "club",
    # 露肤 / 性化 / 血腥恐怖
    "fox ear", "animal ear", "sheer", "off-shoulder", "cleavage",
    "stockings", "high heels", "gore", "blood", "zombie", "horror", "skull",
]
REQUIRED = [
    # 输出与姿态（沿用 V4b）
    "neutral a-pose", "fully covered", "no base", "no weapon",
    "no background", "no text", "single character",
    # 对手怪造型四要素：剪影 / 覆面 / 拼装警示 / 侵蚀「怪」感
    "wide hunched shoulders", "respirator mask",
    "hazard orange-yellow warning stripes", "ether crystal",
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
(HERE / "check_prompt.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["verdict"] == "PROMPT_OK" else 1)
