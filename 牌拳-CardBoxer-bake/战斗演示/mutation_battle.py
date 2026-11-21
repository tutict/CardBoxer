"""战斗演示判据的变异验证：改坏 verify_battle.py 会读的文件，确认判据报红。

纪律与 C 路线一致：ASCII bytes needle、as_eol 处理 CRLF、锚点失配
= DID NOT RUN 计入未证明、二进制逐字节还原 + sha256、守卫禁写字节码。
M7 是「整文件替换」型变异：把真3D版关键帧换成立绘版副本，验证 B09
真的能抓到「两版其实是同一张图」。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe"
VERIFY = HERE / "verify_battle.py"
RESULT = HERE / "mutation_battle_result.json"

CASES = [
    ("M1", "battle_script.json", b'"foe": 81,', b'"foe": 85,',
     "B02_hp_rage_track_recomputed"),
    ("M2", "battle_script.json", b'"damage": 5,', b'"damage": 6,',
     "B01_card_type_binding"),
    ("M3", "battle_demo_stats.json", b'"total_frames": 140,',
     b'"total_frames": 139,', "B05_duration_conservation"),
    ("M4", "battle_script.json", b'"frame_ms": 80,', b'"frame_ms": 83,',
     "B06_frame_ms_10ms_multiple"),
    ("M5", "make_battle.py",
     b'duration=FRAME_MS, loop=0, optimize=False, disposal=1)',
     b'duration=FRAME_MS, loop=0, optimize=True, disposal=1)',
     "B12_source_wiring"),
    ("M6", "battle_script.json", b"demo simplification",
     b"full Taikou rules", "B14_not_claimed_is_explicit"),
    ("M7", "frames/c3d/battle-f069.png", None,
     b"frames/puppet/battle-f069.png", "B09_foe_differs_between_versions"),
    ("M8", "battle_demo_stats.json", b'"spec_sha256": "',
     b'"spec_sha256": "BROKEN', "B13_source_fingerprints"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def as_eol(needle: bytes, data: bytes) -> bytes:
    return needle.replace(b"\n", b"\r\n" if b"\r\n" in data else b"\n")


def guard_env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_verify() -> tuple[int, dict]:
    p = subprocess.run([PY, "-u", str(VERIFY)], cwd=str(HERE),
                       env=guard_env(), capture_output=True, text=True,
                       timeout=180)
    rp = HERE / "verify_battle_result.json"
    return p.returncode, json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}


def main() -> int:
    selftest = os.environ.get("BATTLE_MUTATION_SELFTEST") == "1"
    cases = list(CASES)
    if selftest:
        cases[1] = ("M2", "battle_script.json", b'"damage": 999,',
                    b'"damage": 6,', "B01_card_type_binding")

    out, restored = [], 0
    for cid, rel, needle, mutant, target in cases:
        path = HERE / rel
        orig = path.read_bytes()
        orig_sha = sha(orig)
        if needle is None:  # 整文件替换型
            src = HERE / mutant.decode("ascii")
            assert src.is_file(), f"swap source missing: {src}"
            path.write_bytes(src.read_bytes())
        else:
            n, m = as_eol(needle, orig), as_eol(mutant, orig)
            count = orig.count(n)
            if count != 1:
                out.append({"case": cid, "status": "DID NOT RUN",
                            "reason": f"anchor_count={count} in {rel}",
                            "target": target})
                print(f"[{cid}] DID NOT RUN anchor_count={count} in {rel}", flush=True)
                continue
            path.write_bytes(orig.replace(n, m, 1))
        try:
            rc, res = run_verify()
            failed = [c["name"] for c in res.get("checks", []) if not c["ok"]]
            caught = rc != 0 and target in failed
            out.append({"case": cid, "status": "CAUGHT" if caught else "ESCAPED",
                        "returncode": rc, "target": target,
                        "failed_checks": failed[:6]})
            print(f"[{cid}] {'CAUGHT' if caught else 'ESCAPED'} "
                  f"rc={rc} failed={failed[:4]}", flush=True)
        finally:
            path.write_bytes(orig)
            ok = sha(path.read_bytes()) == orig_sha
            restored += 1
            out[-1]["restored_sha256_ok"] = ok
            if not ok:
                print(f"[{cid}] RESTORE FAILED {rel}", flush=True)

    rc, clean = run_verify()
    clean_ok = rc == 0 and clean.get("verified") is True
    caught = sum(1 for o in out if o["status"] == "CAUGHT")
    did_not_run = sum(1 for o in out if o["status"] == "DID NOT RUN")
    escaped = sum(1 for o in out if o["status"] == "ESCAPED")
    restore_ok = all(o.get("restored_sha256_ok", True) for o in out)
    summary = {
        "cases": out, "caught": caught, "total": len(cases),
        "did_not_run": did_not_run, "escaped": escaped,
        "restored": restored, "restore_all_ok": restore_ok,
        "clean_rerun": "GREEN" if clean_ok else "RED",
        "clean_passed": clean.get("passed"), "clean_total": clean.get("total"),
        "selftest": selftest,
        "verdict": ("MUTATION_BATTLE_OK" if caught == len(cases) and clean_ok
                    and restore_ok and did_not_run == 0
                    else "MUTATION_BATTLE_FAILED"),
    }
    RESULT.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"MUTATION_BATTLE {caught}/{len(cases)} CAUGHT "
          f"did_not_run={did_not_run} escaped={escaped} "
          f"restore={restored}/{len(cases)} clean={summary['clean_rerun']} "
          f"{summary['verdict']}", flush=True)
    return 0 if summary["verdict"] == "MUTATION_BATTLE_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
