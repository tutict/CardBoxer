# -*- coding: utf-8 -*-
"""P5 · verify_pose_p5.py 的变异验证（#218）。

纪律（与本项目历轮一致）：
  · 每条变异只改一个目标文件的一个值 / 删一个文件，且必须保持 JSON 语法成立；
    mutate() 找不到目标就返回 False → DID NOT RUN，计未证明；
  · 守卫必须**点名变红的具体判据**（输出含 `CHECK <name> False`），
    只靠泛化的 sha 判据兜住不算证明；
  · 还原用二进制写回 + sha256 逐字节证明，不用文本读写（会转换行）；
  · 子进程禁字节码（PYTHONDONTWRITEBYTECODE=1 + -B），避免陈旧 pyc
    让变异看起来没生效；
  · 汇总把 DNR / BROKEN / MISSED / SKIPPED 全计未证明；
  · 全部还原后再 clean re-run 一次，必须 30/30 全绿；
  · --selftest-dnr 用一条锚点必然失配的假变异，证明 DNR 检测有效。

用法：python mutation_pose_p5.py [--selftest-dnr]
产出：mutation_pose_p5_result.json、logs/mutation_pose_p5.out（由调用方重定向）
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
DATA = HERE / "data"
BOARDS = HERE / "boards"
VERIFY = HERE / "verify_pose_p5.py"
OUT = HERE / "mutation_pose_p5_result.json"
SELFTEST_OUT = HERE / "mutation_pose_p5_selftest_result.json"
PY = Path(sys.executable)

TABLE_NAMES = {"card_motion.json", "motion_input.json",
               "motion_input_foe.json"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def dumps(path: Path, obj: dict) -> bytes:
    """游戏表沿用 P4 的 round-trip 恒等格式；产物用通用 indent=2。"""
    if path.name == "card_motion.json" and (
            path.parent == GAME / "data" or path.parent.name == "pre-p5"):
        return json.dumps(obj, indent=1, ensure_ascii=False).replace(
            "\n", "\r\n").encode("utf-8")
    if path.name in ("motion_input.json", "motion_input_foe.json"):
        return (json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
                + "\n").encode("utf-8")
    return (json.dumps(obj, ensure_ascii=False, indent=2)
            + "\n").encode("utf-8")


def set_at(obj, path, value) -> bool:
    cur = obj
    for key in path[:-1]:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif isinstance(cur, list) and isinstance(key, int) \
                and 0 <= key < len(cur):
            cur = cur[key]
        else:
            return False
    last = path[-1]
    if isinstance(cur, dict) and last in cur:
        cur[last] = value
        return True
    if isinstance(cur, list) and isinstance(last, int) \
            and 0 <= last < len(cur):
        cur[last] = value
        return True
    return False


def get_at(obj, path):
    cur = obj
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif isinstance(cur, list) and isinstance(key, int) \
                and 0 <= key < len(cur):
            cur = cur[key]
        else:
            return None
    return cur


def j(rel: str) -> Path:
    return DATA / rel


def g(rel: str) -> Path:
    return GAME / rel


# ---- 变异体：每条 mutate(obj) 恰好改一处，返回 False = DID NOT RUN ----

def m01(o):
    return set_at(o, ("cards", "jab", "track", 6, "f_hand", 0), 12.0)


def m02(o):
    v = get_at(o, ("cards", "wave", "track", 0, "f_hand", 0))
    return (v is not None and set_at(
        o, ("cards", "wave", "track", 0, "f_hand", 0), float(v) + 7.0))


def m03(o):
    return set_at(o, ("stance", "f_hand", 0), 74.0)


def m04(o):
    return set_at(o, ("mapping", "leg_cap_deg"), 9.0)


def m05(o):
    return set_at(o, ("stance", "f_hand", 0), 74.0)


def m06(o):
    return set_at(o, ("checks", "three_tables_6248_joint_values_in_sync"),
                  False)


def m07(o):
    return set_at(o, ("checks", "main_marker_parsed"), False)


def m08(o):
    return set_at(o, ("checks", "poses_568"), False)


def m09(o):
    return set_at(o, ("checks", "three_files_changed"), False)


def m10(o):
    return set_at(o, ("checks", 0, "rc"), 1)


def m11(o):
    cases = o.get("cases", [])
    idx = next((i for i, c in enumerate(cases)
                if c.get("name") == o.get("recommended")), None)
    return idx is not None and set_at(o, ("cases", idx, "passed"), False)


def m12(o):
    return set_at(o, ("pose_p5", "worst_p999_m"), 0.01)


def m13(o):
    for i, r in enumerate(o.get("rows", [])):
        if r.get("case") == "pose_p5":
            return set_at(o, ("rows", i, "p999_edge_tear_m"), 0.2)
    return False


def m14(o):
    key = next((k for k in o.get("diff_px", {})
                if "shipped_vs_rolled_back:wave" in k), None)
    return key is not None and set_at(o, ("diff_px", key), 0)


def m15(o):
    v = get_at(o, ("rows", 0, "player_delta", "upperarm_f"))
    return v is not None and set_at(
        o, ("rows", 0, "player_delta", "upperarm_f"), float(v) + 10.0)


def m16(o):
    return set_at(o, ("rows", 0, "mf_live"), 5.0)


def m17(o):
    return set_at(o, ("rows", 0, "table_marker_player"), "bogus")


def m18(o):
    return set_at(o, ("metric_revision",), "R1")


def m19(o):
    return set_at(o, ("files", "data/card_motion.json", "sha_after"),
                  "0" * 64)


CASES = [
    ("M01", g("data/card_motion.json"), m01,
     "jab_identical_to_baseline_independent", "改坏 jab 一个关节值"),
    ("M02", g("data/card_motion.json"), m02,
     "endpoints_zero_drift_independent", "改坏 wave 首帧"),
    ("M03", g("data/card_motion.json"), m03,
     "mf_thresholds_met_independent", "改 stance 前手基准，压低所有 mf"),
    ("M04", g("data/motion_input.json"), m04,
     "probe_rows_delta_matches_formula_independent", "改 leg_cap_deg 破坏公式对账"),
    ("M05", HERE / "orig" / "pre-p5" / "card_motion.json", m05,
     "backup_sha_match_apply_report", "改备份原表"),
    ("M06", j("p5_readback.json"), m06,
     "readback_report_self_consistent", "报告自称 ok 但一条 check 为假"),
    ("M07", j("p5_probe.json"), m07,
     "probe_report_self_consistent", "A/B 报告一条 check 为假"),
    ("M08", j("pose_tear.json"), m08,
     "tear_report_self_consistent", "撕裂报告一条 check 为假"),
    ("M09", j("apply_pose_p5.json"), m09,
     "apply_report_self_consistent", "落地报告一条 check 为假"),
    ("M10", j("all_checks_p5.json"), m10,
     "all_checks_15_of_15_independently", "自检一条 rc=1 但 ok 仍为真"),
    ("M11", j("candidate_scan.json"), m11,
     "recommended_case_all_hard_constraints", "推荐档 passed 改假"),
    ("M12", j("pose_tear.json"), m12,
     "tear_568_rows_recomputed_match_report", "报告 p999 与原始行不符"),
    ("M13", j("pose_tear_blender.json"), m13,
     "tear_within_anchor_and_headroom_2x_cost", "原始行越外部锚"),
    ("M14", j("p5_probe.json"), m14,
     "probe_pixel_diffs_recomputed_match_report", "报告像素差与读盘重算不符"),
    ("M15", j("p5_probe.json"), m15,
     "probe_rows_delta_matches_formula_independent", "改一行 13 骨 delta"),
    ("M16", j("p5_probe.json"), m16,
     "probe_rows_mf_matches_formula_independent", "改一行 mf_live"),
    ("M17", j("p5_probe.json"), m17,
     "probe_marker_matches_mode_independent", "改一行表标记"),
    ("M18", j("recommended_tracks.json"), m18,
     "spec_json_has_r1_and_r2_revisions", "把 R1+R2 退回 R1"),
    ("M19", j("apply_pose_p5.json"), m19,
     "three_table_sha_match_apply_report", "改落地报告 sha_after"),
    ("M20", BOARDS / "P5-引擎AB对照板.png", None,
     "four_boards_present_and_dimensions_ok", "删掉终版 A/B 看板"),
]

FAKE = ("DNR", j("p5_probe.json"),
        lambda o: set_at(o, ("checks", "no_such_check_xyz"), False),
        "none", "锚点必然失配，用来证明 DNR 检测有效")


def guard_env() -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_guard() -> tuple[int, str]:
    p = subprocess.run([str(PY), "-B", "-u", str(VERIFY)],
                       cwd=str(HERE), capture_output=True,
                       timeout=300, env=guard_env())
    return p.returncode, (p.stdout + b"\n" + p.stderr).decode(
        "utf-8", "replace")


def one(case, selftest: bool = False) -> dict:
    cid, target, mutate, expect, why = case
    row = {"id": cid, "target": str(target), "expect": expect, "why": why}
    if not target.is_file():
        row.update({"status": "SKIPPED", "why": "target missing"})
        return row
    original = target.read_bytes()
    before = sha(original)
    obj = None
    if mutate is not None:
        try:
            obj = load(target)
        except Exception as exc:
            row.update({"status": "BROKEN",
                        "why": "json parse: " + repr(exc)})
            return row
        if not mutate(obj):
            row.update({"status": "DID NOT RUN",
                        "why": "anchor not found (needs exactly 1)",
                        "restored": sha(target.read_bytes()) == before})
            return row
        target.write_bytes(dumps(target, obj))
    else:
        target.unlink()
    row["wrote"] = True
    rc, text = run_guard()
    crashed = ("Traceback (most recent call last):" in text
               or "SyntaxError" in text or "JSONDecodeError" in text)
    expect_line = "CHECK " + expect + " False"
    row["rc"] = rc
    row["expect_line_hit"] = expect_line in text
    row["guard_failed"] = "VERIFY_POSE_P5_FAILED" in text
    if crashed:
        row["status"] = "BROKEN"
        row["guard_output"] = text[-600:]
    elif rc == 0:
        row["status"] = "MISSED"
    elif row["expect_line_hit"] and row["guard_failed"]:
        row["status"] = "CAUGHT"
    else:
        row["status"] = "BROKEN"
        row["guard_output"] = text[-600:]
    target.write_bytes(original)
    row["restored"] = sha(target.read_bytes()) == before
    if selftest:
        row["sha_after_selftest"] = before
    return row


def main() -> int:
    selftest = "--selftest-dnr" in sys.argv
    if selftest:
        rows = [one(FAKE, selftest=True)]
        report = {"mode": "selftest-dnr", "rows": rows,
                  "ok": rows[0]["status"] == "DID NOT RUN"
                  and rows[0].get("restored") is True
                  and rows[0].get("wrote") is not True}
        SELFTEST_OUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        for r in rows:
            print("SELFTEST", r["id"], r["status"],
                  "restored", r.get("restored"),
                  "wrote", r.get("wrote", False))
        print("SELFTEST_DNR_EFFECTIVE" if report["ok"]
              else "SELFTEST_DNR_INEFFECTIVE")
        return 0 if report["ok"] else 1

    rows = [one(c) for c in CASES]
    caught = sum(r["status"] == "CAUGHT" for r in rows)
    dnr = sum(r["status"] == "DID NOT RUN" for r in rows)
    broken = sum(r["status"] == "BROKEN" for r in rows)
    missed = sum(r["status"] == "MISSED" for r in rows)
    skipped = sum(r["status"] == "SKIPPED" for r in rows)
    restored = sum(r.get("restored") is True for r in rows)
    attempted = sum(r.get("wrote") is True for r in rows)
    expect_hit = sum(r.get("expect_line_hit") is True for r in rows)
    rc_clean, text_clean = run_guard()
    clean_ok = (rc_clean == 0 and "VERIFY_POSE_P5_OK 30/30" in text_clean)
    proved = (caught == len(rows) and dnr == 0 and broken == 0
              and missed == 0 and skipped == 0
              and restored == attempted == len(rows)
              and expect_hit == caught and clean_ok)
    report = {
        "rows": rows,
        "caught": caught, "dnr": dnr, "broken": broken,
        "missed": missed, "skipped": skipped,
        "restored": restored, "attempted": attempted,
        "expect_hit": expect_hit, "clean_ok": clean_ok,
        "clean_verdict": next(
            (l for l in text_clean.splitlines()
             if "VERIFY_POSE_P5" in l), ""),
        "ok": proved,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print("%s %-6s expect=%-52s rc=%s hit=%s restored=%s" % (
            r["id"], r["status"], r["expect"], r.get("rc"),
            r.get("expect_line_hit"), r.get("restored")))
        if r["status"] in ("BROKEN", "DID NOT RUN", "MISSED"):
            print("   WHY", r.get("why"), r.get("guard_output", "")[:180])
    print("MUTATION_POSE_P5 %d/%d CAUGHT / DNR %d / BROKEN %d / MISSED %d "
          "/ SKIPPED %d / RESTORE %d/%d / expect_hit %d/%d / clean %s" % (
              caught, len(rows), dnr, broken, missed, skipped,
              restored, attempted, expect_hit, caught,
              "OK" if clean_ok else "FAILED"))
    print("ALL GREEN" if proved else "NOT PROVED")
    return 0 if proved else 1


if __name__ == "__main__":
    raise SystemExit(main())
