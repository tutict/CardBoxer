"""按需重绘变异验证：8 组源码变异，逐字节还原 + sha256 证明。

纪律（沿用本仓口径）：
  * needle 必须唯一，匹配 0 次 = DID NOT RUN，计入「未证明」而不是通过；
  * 每条变异必须打中自己点名的那条判据（不是被通用哈希判据兜住），
    所以跑 verify 时带 REDRAW_VERIFY_SKIP_SHA=1 跳过 V23；
  * 还原用二进制读写 + sha256，逐条证明；汇总 SKIPPED/DID NOT RUN 计入失败；
  * 全部跑完做一次不带 skip 的 clean re-run，必须 24/24 PASS。
  * bytes 字面量只写 ASCII；中文行不进 needle。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
PY = sys.executable
VERIFY = HERE / "verify_redraw.py"
SELFTEST = os.environ.get("REDRAW_MUTATION_SELFTEST") == "1"

CASES = [
    {"id": "M1", "file": "scripts/arena.gd",
     "needle": b"var _force_redraw := true", "mutant": b"var _force_redraw := false",
     "expect": ["V05"], "why": "第一帧不强制重画"},
    {"id": "M2", "file": "scripts/arena.gd",
     "needle": b"var redraw_gate_enabled := true",
     "mutant": b"var redraw_gate_enabled := false",
     "expect": ["V04"], "why": "门控默认关闭"},
    {"id": "M3", "file": "scripts/arena.gd",
     "needle": b"\t\teffects, projectiles,", "mutant": b"\t\tprojectiles,",
     "expect": ["V09"], "why": "arena 键漏列 effects"},
    {"id": "M4", "file": "scripts/arena.gd",
     "needle": b"func _request_redraw() -> void:\n\tvar key := _arena_visual_key()",
     "mutant": b"func _request_redraw() -> void:\n\treturn\n\tvar key := _arena_visual_key()",
     "expect": ["V08"], "why": "_request_redraw 直接 return，永远不刷"},
    {"id": "M5", "file": "scripts/arena.gd",
     "needle": b"\t\t_maybe_capture()\n\t\treturn\n",
     "mutant": b"\t\treturn\n",
     "expect": ["V07"], "why": "hitstop 分支丢掉截帧钩子"},
    {"id": "M6", "file": "scripts/hud.gd",
     "needle": b"\t\ta.tk_motion_id, a.tk_motion_label, a.tk_react_id,",
     "mutant": b"\t\ta.tk_motion_id, a.tk_react_id,",
     "expect": ["V10"], "why": "HUD 键漏列 tk_motion_label"},
    {"id": "M7", "file": "scripts/hud.gd",
     "needle": b"\t\t_time if pulsing else -1.0,", "mutant": b"\t\t_time,",
     "expect": ["V11"], "why": "静止帧被递增时钟误判成脏"},
    {"id": "M8", "file": "scripts/hud.gd",
     "needle": b"\tvar dirty: bool = (arena == null or not arena.redraw_gate_enabled\n\t\tor key != _last_visual_key)",
     "mutant": b"\tvar dirty: bool = true",
     "expect": ["V11"], "why": "HUD 回到无条件逐帧重画"},
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify(skip_sha: bool):
    env = dict(os.environ)
    if skip_sha:
        env["REDRAW_VERIFY_SKIP_SHA"] = "1"
    else:
        env.pop("REDRAW_VERIFY_SKIP_SHA", None)
    p = subprocess.run([PY, str(VERIFY)], env=env, capture_output=True,
                       timeout=120, cwd=str(HERE))
    text = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
    result_file = HERE / "verify_redraw_result.json"
    data = json.loads(result_file.read_text(encoding="utf-8")) if result_file.is_file() else {}
    return p.returncode, text, data


def main() -> int:
    cases = CASES
    if SELFTEST:
        cases = [{"id": "SELFTEST-DID-NOT-RUN", "file": "scripts/arena.gd",
                  "needle": b"THIS_ANCHOR_DOES_NOT_EXIST_999999",
                  "mutant": b"REPLACED", "expect": [], "why": "锚点失配自检"}]

    rows = []
    restored = 0
    caught = 0
    did_not_run = 0
    for case in cases:
        path = GAME / case["file"]
        orig = path.read_bytes()
        orig_sha = sha(orig)
        n = orig.count(case["needle"])
        if n != 1:
            rows.append({"id": case["id"], "status": "DID NOT RUN",
                         "anchor_count": n, "why": case["why"]})
            did_not_run += 1
            print("%-20s DID NOT RUN (anchor=%d)" % (case["id"], n))
            continue
        mutated = orig.replace(case["needle"], case["mutant"], 1)
        path.write_bytes(mutated)
        write_ok = sha(path.read_bytes()) == sha(mutated)
        rc, text, data = run_verify(True)
        failed = data.get("failed", [])
        hit = [x for x in case["expect"] if x in failed]
        status = "CAUGHT" if (write_ok and rc != 0 and len(hit) == len(case["expect"])) else "ESCAPED"
        # 逐字节还原，不用文本模式
        path.write_bytes(orig)
        restore_ok = sha(path.read_bytes()) == orig_sha
        if restore_ok:
            restored += 1
        if status == "CAUGHT":
            caught += 1
        rows.append({"id": case["id"], "status": status, "anchor_count": n,
                     "write_ok": write_ok, "verify_rc": rc, "failed": failed,
                     "expected": case["expect"], "hit": hit, "restore_ok": restore_ok,
                     "why": case["why"]})
        print("%-20s %-8s verify_rc=%d failed=%s restore=%s"
              % (case["id"], status, rc, failed, restore_ok))

    rc_clean, text_clean, data_clean = run_verify(False)
    clean_ok = (rc_clean == 0 and data_clean.get("total") == 24
                and data_clean.get("failed") == [])
    total = len(cases)
    proven = caught + did_not_run * 0
    all_ok = (not SELFTEST and caught == total and did_not_run == 0
              and restored == total and clean_ok)
    selftest_ok = (SELFTEST and did_not_run == 1 and caught == 0 and clean_ok)
    verdict = ("MUTATION_REDRAW_FAILED" if not (all_ok or selftest_ok)
               else ("MUTATION_REDRAW_SELFTEST_OK" if SELFTEST else "MUTATION_REDRAW_OK"))
    payload = {
        "selftest": SELFTEST, "total": total, "caught": caught,
        "did_not_run": did_not_run, "restored": restored,
        "clean_rerun": {"rc": rc_clean, "total": data_clean.get("total"),
                        "failed": data_clean.get("failed"), "ok": clean_ok},
        "cases": rows, "verdict": verdict,
    }
    suffix = "_selftest" if SELFTEST else ""
    (HERE / ("mutation_redraw_result%s.json" % suffix)).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log = ["%s %s" % (r["id"], r["status"]) +
           ("" if r["status"] == "CAUGHT" else " anchor=%s" % r.get("anchor_count", ""))
           for r in rows]
    log += ["", "%d/%d CAUGHT | did_not_run=%d | restore=%d/%d | clean=%s"
            % (caught, total, did_not_run, restored, total, "GREEN" if clean_ok else "RED"),
            "RESULT: " + verdict]
    (HERE / ("mutation_redraw%s.log" % suffix)).write_text(
        "\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log[-3:]))
    return 0 if (all_ok or selftest_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
