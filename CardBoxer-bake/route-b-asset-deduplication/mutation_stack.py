"""B 路线 P0 变异验证：证明 verify_stack.py 的判据真的会红。

纪律（沿用本项目既有口径）：
  * 变异体必须语法成立（只改数字/布尔，不改 JSON 结构）；
  * 还原一律二进制写回 + sha256 逐字节证明，不用退出码、不用文本读写；
  * 锚点匹配不到 = DID NOT RUN 并计入未证明，不崩、不假装通过；
  * 每组必须「点名」报红的具体判据，任意异常不算 CAUGHT；
  * 子进程禁写字节码（PYTHONDONTWRITEBYTECODE=1），避免陈旧 .pyc；
  * 跑完做 clean re-run，必须 43/43 ALL GREEN。
输出 data/mutation_stack.json。
用法：python mutation_stack.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
SHOTS = HERE / "shots"
VERIFY = HERE / "verify_stack.py"
OUT = D / "mutation_stack.json"

# (id, 目标文件, needle, mutant, 期望报红的判据名)
CASES = [
    ("M1", D / "stack_pixels.json",
     b'"bright_px": 0', b'"bright_px": 1077',
     "pix_s1_all_zero"),
    ("M2", D / "stack_pixels.json",
     b'"near_white_px": 668', b'"near_white_px": 9999',
     "pix_s4_white_668_cyan_449"),
    ("M3", D / "stack_diagnosis.json",
     b'"cyan_faces_on_deleted": 258', b'"cyan_faces_on_deleted": 10',
     "diag_cyan_on_deleted_258"),
    ("M4", D / "current_pair.json",
     b'"foe_verts_64059": true', b'"foe_verts_64059": false',
     "pair_report_ok"),
    ("M5", SHOTS / "current_pair" / "pair-sv-foe.png",
     None, None,
     "historical_sv_labels_swapped"),
    ("M6", D / "single_layers.json",
     b'"player_is_the_white_one": true',
     b'"player_is_the_white_one": false',
     "single_report_ok"),
    ("M7", D / "world3d_probe.json",
     b'"after_foe_white_drops": true',
     b'"after_foe_white_drops": false',
     "w3d_report_ok"),
    ("M8", D / "world3d_probe.json",
     b'"near_white_px": 937', b'"near_white_px": 17602',
     "w3d_after_foe_white_937"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_verify() -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, "-B", str(VERIFY)],
                          cwd=str(HERE), env=env, capture_output=True,
                          timeout=120)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def main() -> int:
    results = []
    for cid, target, needle, mutant, expect in CASES:
        original = target.read_bytes()
        h0 = sha(original)
        rec = {"id": cid, "target": str(target), "expect_fail": expect,
               "status": "DID NOT RUN", "restore": False}
        try:
            if needle is None:
                # M5：把 foe 原图换成 player 原图的字节（仍是合法 PNG）
                payload = (SHOTS / "current_pair" / "pair-sv-player.png")\
                    .read_bytes()
                assert payload != original
            else:
                n = original.count(needle)
                if n != 1:
                    rec["anchor_count"] = n
                    rec["status"] = "DID NOT RUN"
                    results.append(rec)
                    continue
                payload = original.replace(needle, mutant, 1)
                json.loads(payload.decode("utf-8"))  # 变异体语法必须成立
            target.write_bytes(payload)
            rc, out = run_verify()
            fails = [l.strip() for l in out.splitlines()
                     if l.startswith("FAIL ")]
            named = any(l == "FAIL " + expect for l in fails)
            if rc != 0 and named:
                rec["status"] = "CAUGHT"
            else:
                rec["status"] = "MISSED"
            rec["rc"] = rc
            rec["fails"] = fails[:8]
        except Exception as exc:  # 任意异常都不算证明
            rec["status"] = "MISSED"
            rec["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            target.write_bytes(original)
            rec["restore"] = sha(target.read_bytes()) == h0
        results.append(rec)

    rc_clean, out_clean = run_verify()
    # 不写死判据条数：verify_stack.py 加判据时这里不该失效。
    clean_green = (rc_clean == 0
                   and "ALL GREEN" in out_clean
                   and not out_clean.startswith("FAIL"))
    caught = sum(1 for r in results if r["status"] == "CAUGHT")
    did_not_run = sum(1 for r in results
                      if r["status"] == "DID NOT RUN")
    restored = sum(1 for r in results if r["restore"])
    ok = (caught == len(CASES) and did_not_run == 0
          and restored == len(CASES) and clean_green)
    report = {
        "cases": results, "total": len(CASES), "caught": caught,
        "did_not_run": did_not_run, "restored": restored,
        "clean_rerun_rc": rc_clean,
        "clean_rerun_green": clean_green,
        "clean_rerun_tail": out_clean.strip().splitlines()[-2:],
        "ok": ok,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                   + "\n", encoding="utf-8")
    for r in results:
        print(r["id"], r["status"], "expect", r["expect_fail"],
              "restore", r["restore"], r.get("error", ""))
    print(f"CAUGHT {caught}/{len(CASES)}  DID_NOT_RUN {did_not_run}  "
          f"RESTORE {restored}/{len(CASES)}  CLEAN_GREEN {clean_green}")
    print("MUTATION_STACK_OK" if ok else "MUTATION_STACK_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
