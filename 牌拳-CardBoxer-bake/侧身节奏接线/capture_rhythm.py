"""Capture in-engine frames of the resolve rhythm layer at EXACT time points.

Trick: after _resolve_taikou() we manually advance _tick_rhythm() in 80ms
steps, then set _global_hitstop to a large value. _process() takes the
hitstop branch every frame (which now also calls _maybe_capture), so the
rhythm clock freezes at the requested instant and the PNG is that exact pose.
arena.gd is injected temporarily and restored byte-for-byte (sha256 proven).

Must run WITHOUT --headless: dummy driver never emits frame_post_draw.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
ARENA = GAME / "scripts" / "arena.gd"
OUT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\侧身节奏接线")
TMP = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-rhythm-shots")
LOGDIR = OUT / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")

ANCHOR_A = b'\ttk_bot = OS.get_environment("CARD_BOXER_TAIKOU_BOT") != ""'
ANCHOR_B = b"\t_start_match()"
MARKER = b"CARD_BOXER_RHYTHM_SHOT"

# mode -> (steps of 80ms, 玩家 rank, 对手 rank, 输出文件名)
CASES = {
    "t000": (0, [9, 9, 9], [2, 5, 8], "节奏帧-t000-起手.png"),
    "t048": (6, [9, 9, 9], [2, 5, 8], "节奏帧-t048-命中HIT.png"),
    "t072": (9, [9, 9, 9], [2, 5, 8], "节奏帧-t072-停顿后.png"),
    "t112": (14, [9, 9, 9], [2, 5, 8], "节奏帧-t112-攻击窗末.png"),
    "t140": (17, [9, 9, 9], [2, 5, 8], "节奏帧-t140-淡出.png"),
    "t180": (22, [9, 9, 9], [2, 5, 8], "节奏帧-t180-归零.png"),
    "draw": (6, [1, 1, 1], [1, 1, 1], "节奏帧-平局无节奏.png"),
    "foewin": (6, [1, 1, 2], [9, 9, 9], "节奏帧-对手赢反向.png"),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dominant_eol(data: bytes) -> bytes:
    crlf = data.count(b"\r\n")
    return b"\r\n" if crlf > data.count(b"\n") - crlf else b"\n"


def gd_ints(values) -> str:
    return "[" + ", ".join(str(v) for v in values) + "]"


def mode_lines(mode: str) -> list[bytes]:
    steps, p, e, _ = CASES[mode]
    pids = ["guard"] * 3 if p == [9, 9, 9] else ["jab", "jab", "cross"]
    eids = ["jab", "wave", "cross"] if e == [2, 5, 8] else ["guard"] * 3
    lines = [
        '\tif OS.get_environment("CARD_BOXER_RHYTHM_SHOT") != "":',
        '\t\tround_phase = "fight"',
        "\t\tphase_time = 0.0",
        "\t\ttk_bot = false",
        "\t\ttk_player_reveal = %s" % gd_ints(p),
        "\t\ttk_enemy_reveal = %s" % gd_ints(e),
        "\t\ttk_player_ids = [%s]" % ", ".join('"%s"' % x for x in pids),
        "\t\ttk_enemy_ids = [%s]" % ", ".join('"%s"' % x for x in eids),
        "\t\ttk_player_result = Rules.evaluate(tk_player_reveal)",
        "\t\ttk_enemy_result = Rules.evaluate(tk_enemy_reveal)",
        "\t\t_resolve_taikou()",
        "\t\tfor i in range(%d):" % steps,
        "\t\t\t_tick_rhythm(0.08)",
        "\t\t_apply_rhythm_visuals()",
        "\t\t_global_hitstop = 10.0",
        # 占位符数量 == 参数数组长度；全部 %s + str()，不用 %d（hp 是 int 但稳妥）
        '\t\tprint("[RHYTHM_SHOT] mode=%s t=%s p_shift=%s e_shift=%s p_tilt=%s e_tilt=%s hit=%s hp=%s/%s" % ["{M}", str(tk_rhythm_t), str(player.visual_shift.x), str(enemy.visual_shift.x), str(player.visual_tilt), str(enemy.visual_tilt), str(tk_rhythm_hit), str(player.hp), str(enemy.hp)])'.replace("{M}", mode),
    ]
    return [ln.encode("utf-8") for ln in lines]


def main() -> int:
    for path in (GODOT, ARENA, GAME / "project.godot"):
        if not path.exists():
            print("MISSING: %s" % path)
            return 2
    orig = ARENA.read_bytes()
    orig_sha = sha(orig)
    eol = dominant_eol(orig)
    anchor = ANCHOR_A + eol + ANCHOR_B + eol
    if orig.count(anchor) != 1 or MARKER in orig:
        print("ANCHOR_MISMATCH count=%d leftover=%s" % (
            orig.count(anchor), MARKER in orig))
        return 2

    TMP.mkdir(parents=True, exist_ok=True)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    modes = tuple(sys.argv[1:]) or tuple(CASES)
    results, records = [], []

    try:
        for mode in modes:
            if mode not in CASES:
                print("UNKNOWN_MODE %s" % mode)
                return 2
            block = eol.join(mode_lines(mode)) + eol
            mutated = orig.replace(anchor, anchor + block, 1)
            if mutated.count(MARKER) != 1 or mutated == orig:
                print("INJECT_FAILED mode=%s" % mode)
                return 2
            ARENA.write_bytes(mutated)
            if sha(ARENA.read_bytes()) != sha(mutated):
                print("WRITE_VERIFY_FAILED %s" % mode)
                return 2

            shot_dir = TMP / mode
            if shot_dir.exists():
                shutil.rmtree(shot_dir)
            shot_dir.mkdir(parents=True)
            env = os.environ.copy()
            for key in ("CARD_BOXER_BOT", "CARD_BOXER_TAIKOU_BOT",
                        "CARD_BOXER_TK_SHOT", "CARD_BOXER_P0_SHOT",
                        "CARD_BOXER_CAPTURE_HIT", "CARD_BOXER_RAGE_START"):
                env.pop(key, None)
            env["CARD_BOXER_CAPTURE"] = str(shot_dir)
            env["CARD_BOXER_CAPTURE_AT"] = "0.35"
            env["CARD_BOXER_RHYTHM_SHOT"] = mode
            try:
                proc = subprocess.run(
                    [str(GODOT), "--path", str(GAME), "--quit-after", "900"],
                    env=env, capture_output=True, timeout=120)
                rc = proc.returncode
                log = proc.stdout + b"\n--- STDERR ---\n" + proc.stderr
            except subprocess.TimeoutExpired as exc:
                rc = -1
                log = (exc.stdout or b"") + b"\n--- TIMEOUT ---\n" + (exc.stderr or b"")
            (LOGDIR / ("capture_%s.log" % mode)).write_bytes(log)

            text = log.decode("utf-8", "replace")
            shots = sorted(shot_dir.glob("shot_*.png"))
            markers = [ln.strip() for ln in text.splitlines() if "[RHYTHM_SHOT]" in ln]
            stderr_part = text.split("--- STDERR ---", 1)[-1]
            engine_errors = (text.count("SCRIPT ERROR") + stderr_part.count("ERROR:")
                             + stderr_part.count("Parse Error"))
            has_gl = "OpenGL API" in text
            big_enough = bool(shots) and shots[0].stat().st_size > 100_000
            marker_ok = bool(markers) and ("mode=%s" % mode) in markers[0] \
                and "t=" in markers[0]
            ok = rc == 0 and has_gl and engine_errors == 0 and marker_ok and big_enough
            print("%s: rc=%d shots=%d gl=%s errors=%d marker=%s" % (
                mode, rc, len(shots), has_gl, engine_errors, markers[:1]))
            records.append({"mode": mode, "rc": rc, "ok": ok,
                            "marker": markers, "engine_errors": engine_errors,
                            "gl": has_gl, "bytes": shots[0].stat().st_size if shots else 0})
            if ok:
                dest = OUT / CASES[mode][3]
                shutil.copy2(shots[0], dest)
                print("  saved %s (%d B)" % (dest.name, dest.stat().st_size))
                results.append("OK %s" % mode)
            else:
                results.append("FAIL %s" % mode)
    finally:
        ARENA.write_bytes(orig)
        after = ARENA.read_bytes()
        restore_ok = sha(after) == orig_sha and MARKER not in after
        print("RESTORE %s sha256=%s" % ("OK" if restore_ok else "FAILED", sha(after)))
        results.append("OK RESTORE" if restore_ok else "FAIL RESTORE")

    (OUT / "capture_result.json").write_text(
        json.dumps({"records": records, "restore_ok": restore_ok},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %s" % " | ".join(results))
    return 0 if all(r.startswith("OK") for r in results) \
        and len(results) == len(modes) + 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
