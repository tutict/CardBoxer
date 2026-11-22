"""side-view-rhythm · 20 条承重判据的变异验证。

纪律沿用 P0 / 侧身战斗：ASCII bytes needle、as_eol 处理 CRLF、
锚点失配 = DID NOT RUN 并计入未证明、二进制逐字节还原 + sha256、
守卫子进程禁写字节码（PYTHONDONTWRITEBYTECODE=1）、clean re-run 必须回到 20/20。

覆盖意图：
  * M1-M3  参数真相来源 / 生成物可复现
  * M4-M6  节奏接线形态（含本轮修过的后仰方向符号）
  * M7-M9  P0 不回归 / 判定零改动 / 平局不启节奏
  * M10-M12 纯绘制层边界、变更范围恰好两个文件
  * M13-M17 备份指纹、引擎自检、截帧日志、像素证据（含整张 PNG 替换）
  * M18-M20 离线脚本未改、新自检存在、hitstop 分支可截帧

R20 是「写出指纹后立即比对」的自检型判据，不存在可改坏的上游输入，
故不参与变异，在验证记录里如实标注。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
PY = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe"
VERIFY = HERE / "verify_rhythm.py"
RESULT = HERE / "mutation_rhythm_result.json"

# (case, rel, needle, mutant, 期望报红的判据前缀)
# rel 前缀 game/ = 真实游戏源码；其余按 HERE 解析（可用 ../ 出本目录）。
CASES = [
    ("M1", "battle_rhythm_spec.json",
     b'"press_px": 110,', b'"press_px": 111,', "R07"),
    ("M2", "battle_rhythm_spec.json",
     b'"total_s": 1.9,', b'"total_s": 2.0,', "R06"),
    ("M3", "game/scripts/battle_rhythm.gd",
     b"const PRESS_PX := 110.0", b"const PRESS_PX := 99.0", "R05"),
    ("M4", "game/scripts/arena.gd",
     b"\t_tick_rhythm(dt)", b"\tpass", "R13"),
    ("M5", "game/scripts/arena.gd",
     b"Rhythm.press_px(t) * dir * fade", b"0.0 * dir * fade", "R13"),
    ("M6", "game/scripts/arena.gd",
     b"Rhythm.tilt_rad(t) * dir * fade",
     b"Rhythm.tilt_rad(t) * (-dir) * fade", "R13"),
    ("M7", "game/scripts/arena.gd",
     b"MotionP0.binding_for(winner_type)",
     b'MotionP0.binding_for("scatter")', "R19"),
    ("M8", "game/scripts/arena.gd",
     b"tk_damage = Rules.damage_of(tk_player_result)",
     b"tk_damage = 5", "R11"),
    ("M9", "game/scripts/arena.gd",
     b'if tk_winner == "draw":', b'if tk_winner == "player":', "R15"),
    # 把视觉字段泄漏进判定逻辑：语法成立，但破坏 R12 的纯绘制层边界。
    ("M10", "game/scripts/fighter.gd",
     b'\tvar blocked := is_guarding() and card_id != "throw"',
     b'\tposition += visual_shift\n'
     b'\tvar blocked := is_guarding() and card_id != "throw"', "R12"),
    ("M11", "game/scripts/hud.gd",
     b"class_name FightHUD", b"class_name FightHUD # mutated", "R02"),
    # 整文件换成 pre-side-rhythm 基线 = 把 B 路线接线全撤掉。
    ("M12", "game/scripts/arena.gd", None,
     "../orig/pre-side-rhythm/arena.gd", "R03"),
    ("M13", "backup-fingerprints.json",
     b'"sha256": "5c4c393b7b26c6de6aab40be3a57ebfec39845d6b73f651b17d30bb7e53ac8e3"',
     b'"sha256": "6c4c393b7b26c6de6aab40be3a57ebfec39845d6b73f651b17d30bb7e53ac8e3"',
     "R01"),
    ("M14", "all_checks.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"', "R16"),
    ("M15", "capture_result.json",
     b'"restore_ok": true', b'"restore_ok": false', "R17"),
    ("M16", "evidence_rhythm.json",
     b'"diff_px": 2350', b'"diff_px": 9999', "R18"),
    # 中文路径不能写成 bytes 字面量；整文件替换型一律用 str。
    ("M17", "rhythm-frame-t048-impact-HIT.png", None,
     "rhythm-frame-t180-reset.png", "R18"),
    ("M18", "../side-view-battle-demo/make_side_battle.py",
     b"int(110 * pulse)", b"int(99 * pulse)", "R09"),
    ("M19", "game/tests/battle_rhythm_check.gd", None,
     "logs/empty_marker.bin", "R04"),
    ("M20", "game/scripts/arena.gd",
     b"\t\t_maybe_capture()\n\t\treturn",
     b"\t\tpass  # capture removed\n\t\treturn", "R14"),
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
    rp = HERE / "verify_rhythm_result.json"
    data = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    failed = [c["name"] for c in data.get("checks", []) if not c.get("ok")]
    return p.returncode, failed


def main() -> int:
    selftest = os.environ.get("RHYTHM_MUTATION_SELFTEST") == "1"
    cases = list(CASES)
    if selftest:
        # 故意把 M4 锚点改成不存在的串，证明 DID NOT RUN 分支有牙。
        idx = next(i for i, c in enumerate(cases) if c[0] == "M4")
        c = cases[idx]
        cases[idx] = (c[0], c[1], b"\t_tick_rhythm_NO_SUCH_ANCHOR(dt)",
                      c[3], c[4])
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
            src = HERE / (mutant.decode("utf-8") if isinstance(mutant, bytes)
                          else mutant)
            if not src.is_file():
                out.append({"case": cid, "status": "DID NOT RUN",
                            "reason": "swap source missing", "target": target})
                print(f"[{cid}] DID NOT RUN swap source missing {src}", flush=True)
                continue
            path.write_bytes(src.read_bytes())
        else:
            n, m = as_eol(needle, orig), as_eol(mutant, orig)
            count = orig.count(n)
            if count != 1:
                out.append({"case": cid, "status": "DID NOT RUN",
                            "reason": f"anchor_count={count} in {rel}",
                            "target": target})
                print(f"[{cid}] DID NOT RUN anchor_count={count} in {rel}",
                      flush=True)
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
    if selftest:
        # 自测期望：恰好 1 条 DID NOT RUN、其余全 CAUGHT、还原数少 1、clean 全绿。
        ok = (did_not_run == 1 and caught == len(cases) - 1 and escaped == 0
              and restored == len(cases) - 1 and clean_ok)
        result = ("MUTATION_RHYTHM_SELFTEST_OK" if ok
                  else "MUTATION_RHYTHM_SELFTEST_FAILED")
    else:
        ok = (caught == len(cases) and did_not_run == 0 and escaped == 0
              and restored == len(cases) and clean_ok)
        result = "MUTATION_RHYTHM_OK" if ok else "MUTATION_RHYTHM_FAILED"
    RESULT.write_text(json.dumps({
        "cases": out, "caught": caught, "escaped": escaped,
        "did_not_run": did_not_run, "restored": restored,
        "total": len(cases), "clean_rerun_rc": rc_clean,
        "clean_failed": failed_clean, "clean_ok": clean_ok,
        "result": result, "selftest": selftest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %d/%d CAUGHT / did_not_run=%d / escaped=%d / restore=%d/%d / clean=%s / %s"
          % (caught, len(cases), did_not_run, escaped, restored, len(cases),
             "GREEN" if clean_ok else "RED", result))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
