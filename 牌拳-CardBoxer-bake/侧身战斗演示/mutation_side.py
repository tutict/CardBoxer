"""侧身战斗判据的变异验证：改坏 verify_side.py 会读的文件，确认判据报红。

纪律沿用 C 路线 / 战斗演示：ASCII bytes needle、as_eol 处理 CRLF、
锚点失配 = DID NOT RUN 计入未证明、二进制逐字节还原 + sha256、
守卫子进程禁写字节码。M8 是整文件替换型，验证 S09 真能抓到
「hit-stop 帧被换成别的画面」。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe"
VERIFY = HERE / "verify_side.py"
RESULT = HERE / "mutation_side_result.json"

CASES = [
    ("M1", "side_stance.json", b'"selected": "S2",', b'"selected": "S1",',
     "S02_stance_frame_equals_selected_probe"),
    ("M2", "side_joints.json", b'"flip_source_horizontally": true,',
     b'"flip_source_horizontally": false,', "S03_side_view_semantics"),
    ("M3", "side_action.json", b'"gain": 0.55,', b'"gain": 1.0,',
     "S04_local_relative_angle_and_caps"),
    ("M4", "make_side_frames.py", b"raw = wrap_deg(world[n] - pw)",
     b"raw = wrap_deg(world[n])", "S04_local_relative_angle_and_caps"),
    ("M5", "make_side_battle.py", b'flip = side == "foe"',
     b"flip = False", "S05_facing_rule"),
    ("M6", "side_battle_stats.json", b'"total_frames": 140,',
     b'"total_frames": 139,', "S07_duration_conservation"),
    ("M7", "make_side_battle.py",
     b"duration=frame_ms, loop=0, optimize=False, disposal=1)",
     b"duration=frame_ms, loop=0, optimize=True, disposal=1)",
     "S12_source_wiring"),
    ("M8", "frames/battle/side-battle-f029.png", None,
     b"frames/battle/side-battle-f012.png", "S09_hitstop_is_three_frames"),
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
    rp = HERE / "verify_side_result.json"
    return p.returncode, json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}


def main() -> int:
    selftest = os.environ.get("SIDE_MUTATION_SELFTEST") == "1"
    cases = list(CASES)
    if selftest:
        cases[2] = ("M3", "side_action.json", b'"gain": 999,',
                    b'"gain": 1.0,', "S04_local_relative_angle_and_caps")

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
        "verdict": ("MUTATION_SIDE_OK" if caught == len(cases) and clean_ok
                    and restore_ok and did_not_run == 0
                    else "MUTATION_SIDE_FAILED"),
    }
    RESULT.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"MUTATION_SIDE {caught}/{len(cases)} CAUGHT "
          f"did_not_run={did_not_run} escaped={escaped} "
          f"restore={restored}/{len(cases)} clean={summary['clean_rerun']} "
          f"{summary['verdict']}", flush=True)
    return 0 if summary["verdict"] == "MUTATION_SIDE_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
