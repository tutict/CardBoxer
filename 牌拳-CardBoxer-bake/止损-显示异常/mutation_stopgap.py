"""变异验证：证明 verify_stopgap.py 的判据真的会红。

每个 case：改坏一处 → 跑判据 → 逐字节还原（sha256 证明）→ 记录。
锚点失配记为 DID NOT RUN，计入「未证明」，不冒充 CAUGHT。
用法：python mutation_stopgap.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
J = GAME.parent / "牌拳-CardBoxer-bake" / "J路线-造型重做"
VERIFY = HERE / "verify_stopgap.py"
NEW_BAT = GAME / "运行游戏-3D.bat"
DEF_JSON = HERE / "shots" / "after-default" / "result.json"
TD_JSON = HERE / "shots" / "after-3d" / "result.json"
GLB = GAME / "assets" / "3d" / "foe-rigged.glb"
B_ROUND2 = J / "foe-rigged-b.glb"

CASES = [
    ("M1", NEW_BAT, b'set "CARD_BOXER_3D=1"', b"rem 3d disabled",
     "new_bat_has_3d_switch"),
    ("M2", NEW_BAT, b"chcp 65001", b"chcp 936",
     "new_bat_has_utf8_codepage"),
    ("M3", DEF_JSON, b'"use_3d": false', b'"use_3d": true',
     "default_probe_off"),
    ("M4", TD_JSON, b'"layer_3d": true', b'"layer_3d": false',
     "3d_probe_on"),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_verify() -> str:
    p = subprocess.run([sys.executable, "-u", str(VERIFY)],
                       capture_output=True, timeout=120, cwd=str(HERE))
    return (p.stdout + p.stderr).decode("utf-8", "replace")


def main() -> int:
    assert VERIFY.is_file() and B_ROUND2.is_file()
    rows = []
    # 文本/JSON 变异
    for name, path, needle, mutant, expect in CASES:
        original = path.read_bytes()
        if needle not in original:
            rows.append({"case": name, "status": "DID NOT RUN",
                         "reason": "anchor not found", "expect": expect})
            print(f"CASE {name} DID NOT RUN (anchor not found)")
            continue
        path.write_bytes(original.replace(needle, mutant, 1))
        out = run_verify()
        failed_line = next((l for l in out.splitlines()
                            if l.startswith("FAILED ")), "FAILED ")
        caught = "STOPGAP_FAILED" in out and expect in failed_line
        path.write_bytes(original)
        restored = sha256_bytes(path.read_bytes()) == sha256_bytes(original)
        status = "CAUGHT" if caught else "MISSED"
        rows.append({"case": name, "status": status, "expect": expect,
                     "restore_sha_ok": restored,
                     "failed_line": failed_line})
        print(f"CASE {name} {status} expect={expect} restore={restored}")
        if not restored:
            print("RESTORE FAILED - abort")
            return 1

    # M5：把工程 GLB 换回 B round2，证明「已回滚」这条核心判据有牙
    original_glb = GLB.read_bytes()
    original_hash = sha256_bytes(original_glb)
    shutil.copyfile(B_ROUND2, GLB)
    out = run_verify()
    failed_line = next((l for l in out.splitlines()
                        if l.startswith("FAILED ")), "FAILED ")
    caught = ("STOPGAP_FAILED" in out
              and "glb_sha_is_i_baseline" in failed_line
              and "b_round2_glb_removed" in failed_line)
    GLB.write_bytes(original_glb)
    restored = sha256_bytes(GLB.read_bytes()) == original_hash
    status = "CAUGHT" if caught else "MISSED"
    rows.append({"case": "M5", "status": status,
                 "expect": "glb_sha_is_i_baseline,b_round2_glb_removed",
                 "restore_sha_ok": restored, "failed_line": failed_line})
    print(f"CASE M5 {status} restore={restored}")
    if not restored:
        print("RESTORE FAILED - abort")
        return 1

    clean = run_verify()
    clean_ok = "STOPGAP_VERIFIED" in clean and "PASSED 15/15" in clean
    caught_n = sum(r["status"] == "CAUGHT" for r in rows)
    not_run = sum(r["status"] == "DID NOT RUN" for r in rows)
    restore_n = sum(r.get("restore_sha_ok") is True for r in rows)
    ok = (caught_n == len(CASES) + 1 and not_run == 0
          and restore_n == len(CASES) + 1 and clean_ok)
    (HERE / "data").mkdir(parents=True, exist_ok=True)
    (HERE / "data" / "mutation_stopgap.json").write_text(
        json.dumps({"rows": rows, "caught": caught_n,
                    "did_not_run": not_run, "restored": restore_n,
                    "clean_rerun_green": clean_ok, "ok": ok},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CAUGHT {caught_n}/{len(CASES) + 1} DID_NOT_RUN {not_run} "
          f"RESTORE {restore_n}/{len(CASES) + 1} CLEAN_GREEN {clean_ok}")
    print("MUTATION_STOPGAP_OK" if ok else "MUTATION_STOPGAP_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
