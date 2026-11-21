"""P0 接线判据的变异验证：改坏 verify_p0.py 会读的文件，确认判据报红。

纪律沿用 C 路线 / 侧身战斗：ASCII bytes needle、as_eol 处理 CRLF、
锚点失配 = DID NOT RUN 计入未证明、二进制逐字节还原 + sha256、
守卫子进程禁写字节码、clean re-run 必须回到 18/18。

特别验证两类容易漏的坑：
  * M6/M7：把调用形态改成旧写法 / 把 HUD 条件改成 false，
    证明 V11/V12/V14 钉的是「真实调用形态」不是注释里也有的词。
  * M11：整张 PNG 替换，证明 V18 真的从盘上重算像素，不是只信 JSON。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
PY = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe"
VERIFY = HERE / "verify_p0.py"
RESULT = HERE / "mutation_p0_result.json"

# (case, rel[, needle, mutant], 期望报红的判据名)
# rel 前缀 game/ = 真实游戏源码；其余 = 本目录归档文件。
CASES = [
    ("M1", "game/scripts/battle_motion_p0.gd",
     b'"winner_card": "wave",', b'"winner_card": "jab",', "V05"),
    ("M2", "game/scripts/battle_motion_p0.gd",
     b'"extra": "super",', b'"extra": "",', "V06"),
    ("M3", "game/scripts/battle_motion_p0.gd",
     b'const REVEAL_CARD := "focus"', b'const REVEAL_CARD := "wave"', "V08"),
    ("M4", "game/scripts/arena.gd",
     b"player.perform_visual(tk_motion_id)",
     b'player.perform_visual("jab")', "V12"),
    ("M5", "game/scripts/arena.gd",
     b'enemy.apply_hit(tk_damage, "taikou", tk_motion_extra, false)',
     b'enemy.apply_hit(tk_damage, "taikou", "", false)', "V11"),
    ("M6", "game/scripts/arena.gd",
     b"player.perform_visual(MotionP0.REVEAL_CARD)",
     b"player.perform_visual(String(tk_player_ids[0]))", "V11"),
    ("M7", "game/scripts/hud.gd",
     b'if String(arena.tk_motion_id) != "":', b"if false:", "V14"),
    ("M8", "game/scripts/arena.gd",
     b" % tk_motion_label", b' % ""', "V15"),
    ("M9", "all_checks.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"', "V16"),
    ("M10", "capture_result.json",
     b"motion=wave label=", b"motion=jab label=", "V17"),
    # 中文路径不能写成 bytes 字面量（SyntaxError），整文件替换型用 str。
    ("M11", "引擎帧-三同气功波.png", None,
     "引擎帧-散牌刺拳.png", "V18"),
    ("M12", "game/scripts/arena.gd",
     b"tk_damage = Rules.damage_of(tk_player_result)", b"tk_damage = 5", "V13"),
    ("M13", "game/tests/battle_motion_p0_check.gd", None,
     b"logs/empty_marker.bin", "V04"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def as_eol(needle: bytes, data: bytes) -> bytes:
    return needle.replace(b"\n", b"\r\n" if b"\r\n" in data else b"\n")


def path_for(rel: str) -> Path:
    if rel.startswith("game/"):
        return GAME / rel[5:]
    return HERE / rel


def guard_env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_verify() -> tuple[int, list[str]]:
    p = subprocess.run([PY, "-u", str(VERIFY)], cwd=str(HERE),
                       env=guard_env(), capture_output=True, text=True,
                       timeout=180)
    rp = HERE / "verify_p0_result.json"
    data = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    failed = [c["name"] for c in data.get("checks", []) if not c.get("ok")]
    return p.returncode, failed


def main() -> int:
    selftest = os.environ.get("P0_MUTATION_SELFTEST") == "1"
    cases = list(CASES)
    if selftest:
        # 故意把 M3 锚点改成不存在的串，证明 DID NOT RUN 分支有牙
        cases[2] = ("M3", "game/scripts/battle_motion_p0.gd",
                    b'const REVEAL_CARD := "NOT_THERE"',
                    b'const REVEAL_CARD := "wave"', "V08")
    (HERE / "logs").mkdir(parents=True, exist_ok=True)
    (HERE / "logs" / "empty_marker.bin").write_bytes(b"")

    out, restored = [], 0
    for cid, rel, needle, mutant, target in cases:
        path = path_for(rel)
        if not path.is_file():
            out.append({"case": cid, "status": "DID NOT RUN",
                        "reason": "missing file " + rel, "target": target})
            print(f"[{cid}] DID NOT RUN missing {rel}", flush=True)
            continue
        orig = path.read_bytes()
        orig_sha = sha(orig)
        if needle is None:  # 整文件替换型
            src = HERE / (mutant.decode("utf-8") if isinstance(mutant, bytes) else mutant)
            if not src.is_file():
                out.append({"case": cid, "status": "DID NOT RUN",
                            "reason": "swap source missing", "target": target})
                continue
            path.write_bytes(src.read_bytes())
        else:
            n, m = as_eol(needle, orig), as_eol(mutant, orig)
            count = orig.count(n)
            if count != 1:
                out.append({"case": cid, "status": "DID NOT RUN",
                            "reason": f"anchor_count={count} in {rel}", "target": target})
                print(f"[{cid}] DID NOT RUN anchor_count={count} in {rel}", flush=True)
                continue
            path.write_bytes(orig.replace(n, m, 1))

        try:
            rc, failed = run_verify()
            caught = rc != 0 and any(f.startswith(target) for f in failed)
            status = "CAUGHT" if caught else "ESCAPED"
            out.append({"case": cid, "status": status, "rc": rc,
                        "failed_checks": failed, "target": target})
            print(f"[{cid}] {status} rc={rc} failed={failed[:4]}", flush=True)
        finally:
            path.write_bytes(orig)
            if sha(path.read_bytes()) == orig_sha:
                restored += 1
            else:
                print(f"[{cid}] RESTORE FAILED {rel}", flush=True)

    rc_clean, failed_clean = run_verify()
    clean_ok = rc_clean == 0 and not failed_clean
    caught = sum(1 for o in out if o["status"] == "CAUGHT")
    did_not_run = sum(1 for o in out if o["status"] == "DID NOT RUN")
    escaped = sum(1 for o in out if o["status"] == "ESCAPED")
    ok = (caught == len(cases) and did_not_run == 0 and escaped == 0
          and restored == len(cases) and clean_ok)
    RESULT.write_text(json.dumps({
        "cases": out, "caught": caught, "escaped": escaped,
        "did_not_run": did_not_run, "restored": restored,
        "total": len(cases), "clean_rerun_rc": rc_clean,
        "clean_failed": failed_clean, "clean_ok": clean_ok,
        "result": "MUTATION_P0_OK" if ok else "MUTATION_P0_FAILED",
        "selftest": selftest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %d/%d CAUGHT / did_not_run=%d / escaped=%d / restore=%d/%d / clean=%s / %s"
          % (caught, len(cases), did_not_run, escaped, restored, len(cases),
             "GREEN" if clean_ok else "RED",
             "MUTATION_P0_OK" if ok else "MUTATION_P0_FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
