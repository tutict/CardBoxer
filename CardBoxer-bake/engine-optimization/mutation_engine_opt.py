"""engine-optimization 20 条判据的变异验证。

纪律：ASCII bytes needle、as_eol 处理 CRLF、锚点失配 = DID NOT RUN 计入
未证明、二进制逐字节还原 + sha256、守卫子进程禁写字节码、clean re-run 全绿。
变异体一律保持语法成立（注释掉一行 / 改数值 / 整文件换成合法基线），
不拿「文件坏了」当证明。

R20 是写后自检（写指纹再比对），无上游可变异，不参与。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
PY = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe"
VERIFY = HERE / "verify_engine_opt.py"
RESULT = HERE / "mutation_engine_opt_result.json"

# (case, rel, needle, mutant, 期望报红的判据前缀)
# rel 前缀 game/ = 真实游戏源码；prev/ = 上轮归档；其余按 HERE 解析。
CASES = [
    ("M1", "game/scripts/arena.gd",
     b"Rect2(-40, -40, 1360, 800), false)",
     b"Rect2(-40, -40, 100, 100), false)", "V05"),
    ("M2", "game/scripts/arena.gd",
     b"func _draw_backdrop() -> void:",
     b"func _draw_backdrop() -> void:\n\tvar bands := [Color(0.1, 0.1, 0.1)]", "V06"),
    ("M3", "game/scripts/arena.gd",
     b"\t_draw_light_cone(Vector2(250, -40)",
     b"\t# _draw_light_cone(Vector2(250, -40)", "V08"),
    ("M4", "game/scripts/arena.gd",
     b"tk_damage = Rules.damage_of(tk_player_result)",
     b"tk_damage = 5", "V09"),
    ("M5", "game/scripts/arena.gd",
     b"MotionP0.binding_for(winner_type)",
     b'MotionP0.binding_for("scatter")', "V10"),
    ("M6", "game/scripts/arena.gd", None,
     "../orig/pre-engine-opt/scripts__arena.gd", "V02"),
    ("M7", "game/project.godot",
     b"window/size/window_width_override=1600",
     b"window/size/window_width_override=1280", "V19"),
    ("M8", "background-fingerprints.json",
     b'"sha256": "', b'"sha256": "0', "V04"),
    ("M9", "backup-fingerprints.json",
     b'"sha256": "72cdfe54dfad3c62160e684b237e40fa87eca22f2f5cdd7292cf309f6f806dc6"',
     b'"sha256": "02cdfe54dfad3c62160e684b237e40fa87eca22f2f5cdd7292cf309f6f806dc6"', "V01"),
    ("M10", "game/tests/engine_opt_check.gd", None,
     "logs/empty_marker.bin", "V03"),
    ("M11", "after/background-baseline.png", None,
     "logs/pixel_mutant.png", "V11"),
    ("M12", "ab_result.json",
     b'"delta": -294.0', b'"delta": 294.0', "V12"),
    ("M13", "all_checks.json",
     b'"result": "ALL GREEN"', b'"result": "FAILED"', "V13"),
    ("M14", "window_probe_result.json",
     b'"result": "WINDOW_ENLARGED_OK"',
     b'"result": "WINDOW_ENLARGED_FAILED"', "V14"),
    ("M15", "logs/rng_probe.log", None,
     "logs/rng_all_same.log", "V16"),
    ("M16", "regression_result.json",
     b'"result": "REGRESSION_EVIDENCE_OK"',
     b'"result": "REGRESSION_EVIDENCE_FAILED"', "V17"),
    ("M17", "prev/side-view-rhythm-file-list.txt",
     b"8174c35fdf83b903139df0bc28f8ed2347b39de26d122da3b7061ff47f859859",
     b"0174c35fdf83b903139df0bc28f8ed2347b39de26d122da3b7061ff47f859859", "V18"),
    ("M18", "game/scripts/arena.gd",
     b"Color(0.055, 0.045, 0.085, 0.20)",
     b"Color(0.055, 0.045, 0.085, 0.21)", "V07"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def as_eol(needle: bytes, data: bytes) -> bytes:
    return needle.replace(b"\n", b"\r\n" if b"\r\n" in data else b"\n")


def path_for(rel: str) -> Path:
    if rel.startswith("game/"):
        return GAME / rel[5:]
    if rel.startswith("prev/"):
        return HERE.parent / "side-view-rhythm" / rel[5:]
    return HERE / rel


def guard_env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_verify() -> tuple[int, list[str]]:
    p = subprocess.run([PY, "-u", str(VERIFY)], cwd=str(HERE),
                       env=guard_env(), capture_output=True, text=True,
                       timeout=180)
    rp = HERE / "verify_engine_opt_result.json"
    data = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {}
    failed = [c["name"] for c in data.get("checks", []) if not c.get("ok")]
    return p.returncode, failed


def prepare_fixtures() -> None:
    logs = HERE / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "empty_marker.bin").write_bytes(b"")
    src = Image.open(HERE / "baseline" / "background-baseline.png").convert("RGB")
    src.putpixel((10, 10), (255, 0, 0))
    src.save(logs / "pixel_mutant.png")
    same = "\n".join(
        ["RNG_PROBE unseeded=0.123456789 a=0.349460930 b=0.349460930 "
         "c=0.349460930 new_consumes_global=false reset_restores=true"] * 3
    ) + "\n"
    (logs / "rng_all_same.log").write_text(same, encoding="utf-8")


def main() -> int:
    selftest = os.environ.get("ENGINE_OPT_MUTATION_SELFTEST") == "1"
    cases = list(CASES)
    if selftest:
        idx = next(i for i, c in enumerate(cases) if c[0] == "M2")
        c = cases[idx]
        cases[idx] = (c[0], c[1], b"func _draw_backdrop_NO_SUCH_ANCHOR()",
                      c[3], c[4])
    prepare_fixtures()

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
        if needle is None:
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
        ok = (did_not_run == 1 and caught == len(cases) - 1 and escaped == 0
              and restored == len(cases) - 1 and clean_ok)
        result = ("MUTATION_ENGINE_OPT_SELFTEST_OK" if ok
                  else "MUTATION_ENGINE_OPT_SELFTEST_FAILED")
    else:
        ok = (caught == len(cases) and did_not_run == 0 and escaped == 0
              and restored == len(cases) and clean_ok)
        result = "MUTATION_ENGINE_OPT_OK" if ok else "MUTATION_ENGINE_OPT_FAILED"
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
