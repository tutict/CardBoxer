# -*- coding: utf-8 -*-
"""#213 变异验证：证明 verify_pose_spec.py 的 14 条判据有牙。

纪律（沿用 P4 / 实机验收）：
  · 二进制读写 + sha256 还原证明，不用文本模式（会做换行转换）。
  · 锚点必须恰好命中 1 次；否则是 DID NOT RUN，计入未证明。
  · 守卫崩栈 / SyntaxError / JSONDecodeError 记 BROKEN，不算 CAUGHT。
  · SKIPPED / DNR / BROKEN / MISSED 一律计入未证明。
  · 守卫子进程禁写字节码，避免快 runner 上读到陈旧 pyc。
  · --selftest-dnr 故意让锚点失配，必须出现 DNR 且汇总 FAILED。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "牌拳-CardBoxer"
VERIFY = HERE / "verify_pose_spec.py"
RESULT = HERE / "mutation_pose_spec_result.json"

BASELINE = json.loads(
    (HERE / "orig" / "基线-规格阶段.json").read_text(encoding="utf-8-sig"))
ARENA_SHA = BASELINE["files"]["scripts/arena.gd"]["sha256"]
ARENA_SHA_BAD = ("0" if ARENA_SHA[0] != "0" else "1") + ARENA_SHA[1:]

SPEC = "招牌动作规格.json"
TXT = "招牌动作设计-规格说明.txt"
BASE = "orig/基线-规格阶段.json"
METRICS = "pose_metrics.py"


def case(name, loc, needle, mutant, expect):
    return {"name": name, "loc": loc, "needle": needle,
            "mutant": mutant, "expect": expect}


CASES = [
    case("M1 删掉一个来源 id（L7 引用悬空）", SPEC,
         '"id": "S7",', '"id": "SX7",',
         "language_rules_complete_and_traceable"),
    case("M2 改 stance 快照一个关节值", SPEC,
         '"shoulder": [2.0, -148.0]', '"shoulder": [2.0, -149.0]',
         "coordinate_matches_live_table"),
    case("M3 改坐标系 units", SPEC,
         '+x forward; -y up', '+x forward; +y up',
         "coordinate_matches_live_table"),
    case("M4 把 L3 峰值段改成 windup", SPEC,
         "peak_reach_phase == 'active'", "peak_reach_phase == 'windup'",
         "hard_rules_are_explicit"),
    case("M5 允许重新引入精确平台", SPEC,
         "exact_hold_pairs 必须保持 0", "exact_hold_pairs 可以大于 0",
         "hard_rules_are_explicit"),
    case("M6 把 triple 绑到 focus", SPEC,
         '"winner_asset": "wave"', '"winner_asset": "focus"',
         "tiers_match_p0_binding"),
    case("M7 删掉 C1 冲突编号", SPEC,
         '"id": "C1",', '"id": "CX1",',
         "conflicts_named_and_p4_not_retired"),
    case("M8 抹掉不复刻 IP 的边界", SPEC,
         "不复刻 SNK/Capcom", "复刻 SNK/Capcom",
         "boundaries_declared"),
    case("M9 篡改 wave 实测数字", SPEC,
         '"wave": 1.7224, "cross": 18.9248',
         '"wave": 9.9999, "cross": 18.9248',
         "provisional_findings_independently_recomputed"),
    case("M10 改源码基线的一个 sha", BASE,
         ARENA_SHA, ARENA_SHA_BAD,
         "game_sources_untouched"),
    case("M11 让精确平台公式恒 +1", METRICS,
         "exact_hold = sum(1 for i in range(1, n) if js[i] == js[i - 1])",
         "exact_hold = sum(1 for i in range(1, n) if js[i] == js[i - 1]) + 1",
         "provisional_findings_independently_recomputed"),
    case("M12 把 reach 默认侧改成后手", METRICS,
         'def reach(j: dict, side: str = "f") -> float:',
         'def reach(j: dict, side: str = "b") -> float:',
         "provisional_findings_independently_recomputed"),
    case("M13 说明文档里删掉 L8 规则", TXT,
         "L8 招式可辨", "L9 招式可辨",
         "spec_text_covers_rules_and_sources"),
    case("M14 真改游戏源码 units", "GAME:data/card_motion.json",
         '+x forward; -y up', '+x forward; +y up',
         "game_sources_untouched"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def resolve(loc: str) -> Path:
    if loc.startswith("GAME:"):
        return GAME / loc[5:]
    return HERE / loc


def guard_env() -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_verify() -> tuple:
    p = subprocess.run(
        [sys.executable, "-B", "-u", str(VERIFY)],
        cwd=str(HERE), env=guard_env(), capture_output=True, timeout=180)
    text = (p.stdout.decode("utf-8", "replace")
            + p.stderr.decode("utf-8", "replace"))
    broken = any(w in text for w in
                 ("Traceback", "SyntaxError", "JSONDecodeError"))
    failed = re.findall(r"^FAIL\s+(\S+)", text, re.M)
    clean = p.returncode == 0 and "POSE_SPEC_VERIFIED" in text
    passed_line = re.search(r"(\d+)/(\d+) PASS", text)
    passed = passed_line.group(1) if passed_line else "?"
    total = passed_line.group(2) if passed_line else "?"
    return p.returncode, text, failed, broken, clean, passed, total


def run_one(c: dict) -> dict:
    path = resolve(c["loc"])
    row = {"name": c["name"], "file": str(path), "expect": c["expect"]}
    if not path.is_file():
        row.update({"status": "DID NOT RUN", "why": "file missing"})
        return row
    original = path.read_bytes()
    needle = c["needle"].encode("utf-8")
    mutant = c["mutant"].encode("utf-8")
    hits = original.count(needle)
    if hits != 1:
        row.update({"status": "DID NOT RUN",
                    "why": "anchor hits %d (need exactly 1)" % hits})
        return row
    changed = original.replace(needle, mutant, 1)
    if changed == original:
        row.update({"status": "DID NOT RUN", "why": "no byte change"})
        return row

    path.write_bytes(changed)
    try:
        rc, text, failed, broken, clean, passed, total = run_verify()
    finally:
        path.write_bytes(original)
    restored = sha(path.read_bytes()) == sha(original)
    row["restore_sha_ok"] = restored

    if broken:
        row.update({"status": "BROKEN", "why": "guard crashed or bad syntax",
                    "guard_output": text[:400]})
    elif rc != 0 and failed:
        row.update({"status": "CAUGHT", "caught": failed,
                    "expect_hit": c["expect"] in failed,
                    "verdict": "%s/%s" % (passed, total)})
    elif rc == 0:
        row.update({"status": "MISSED", "why": "guard stayed GREEN",
                    "verdict": "%s/%s" % (passed, total)})
    else:
        row.update({"status": "MISSED", "why": "rc=%d without FAIL lines" % rc,
                    "verdict": "%s/%s" % (passed, total)})
    return row


def main() -> None:
    global RESULT
    selftest = "--selftest-dnr" in sys.argv
    RESULT = HERE / ("mutation_pose_spec_selftest_result.json" if selftest
                     else "mutation_pose_spec_result.json")
    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)

    cases = list(CASES)
    if selftest:
        cases = [dict(CASES[0], needle="__ANCHOR_THAT_DOES_NOT_EXIST__",
                      name="SELFTEST 锚点失配")]

    rows = [run_one(c) for c in cases]
    for r in rows:
        print("%-11s %-48s %s" % (
            r["status"], r["name"][:48],
            ",".join(r.get("caught", []))[:110]
            or r.get("why", "") or r.get("verdict", "")), flush=True)

    caught = sum(1 for r in rows if r["status"] == "CAUGHT")
    dnr = sum(1 for r in rows if r["status"] == "DID NOT RUN")
    broken = sum(1 for r in rows if r["status"] == "BROKEN")
    missed = sum(1 for r in rows if r["status"] == "MISSED")
    restored = sum(1 for r in rows if r.get("restore_sha_ok"))
    attempted = sum(1 for r in rows if "restore_sha_ok" in r)
    expect_hit = sum(1 for r in rows if r.get("expect_hit"))

    _rc, _text, _failed, _broken, clean, passed, total = run_verify()
    clean_ok = clean and not _broken
    proved = (caught == len(rows) and dnr == 0 and broken == 0
              and missed == 0 and restored == attempted == len(rows)
              and expect_hit == caught and clean_ok)

    if selftest:
        effective = dnr == 1 and not proved and clean_ok
        print("\nSELFTEST_DNR_EFFECTIVE" if effective
              else "\nSELFTEST_DNR_INEFFECTIVE",
              "dnr=%d clean=%s/%s" % (dnr, passed, total), flush=True)
        verdict = "SELFTEST_DNR_EFFECTIVE" if effective else "SELFTEST_DNR_FAILED"
    else:
        print("\nMUTATION_POSE_SPEC %d/%d CAUGHT / DNR %d / BROKEN %d / "
              "MISSED %d / RESTORE %d/%d / expect_hit %d/%d / clean %s/%s %s"
              % (caught, len(rows), dnr, broken, missed, restored, attempted,
                 expect_hit, caught, passed, total,
                 "ALL GREEN" if proved else "FAILED"), flush=True)
        verdict = "MUTATION_POSE_SPEC_OK" if proved else "MUTATION_POSE_SPEC_FAILED"

    RESULT.write_text(json.dumps(
        {"verdict": verdict, "selftest": selftest, "rows": rows,
         "summary": {"cases": len(rows), "caught": caught, "dnr": dnr,
                     "broken": broken, "missed": missed,
                     "restored": restored, "expect_hit": expect_hit,
                     "clean": clean_ok, "clean_passed": passed,
                     "clean_total": total}},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if (effective if selftest else proved) else 1)


if __name__ == "__main__":
    main()
