"""Capture in-engine frames for the P0 motion wiring.

Temporarily injects a tiny verification block into arena.gd (after
_start_match()), runs the NORMAL main scene with a real GL context, and
restores arena.gd byte-for-byte in a finally block (sha256 proven).

Modes:
  reveal   -> real _do_taikou_reveal() path; both fighters must be on focus
  triple / sequence / scatter / draw -> real _resolve_taikou() path with
               deterministic ranks, so the banner / HUD / fighter action
               can be inspected frame by frame.

Discipline (same as taikou_shot.py / capture_skin.py):
  * binary read/write only; anchor must match exactly once
  * restore proven by sha256; no game source left modified
  * no --headless: dummy driver never emits frame_post_draw
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
ARENA = GAME / "scripts" / "arena.gd"
OUT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\动作接线P0")
TMP = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-p0-shots")
LOGDIR = OUT / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")

ANCHOR_A = b'\ttk_bot = OS.get_environment("CARD_BOXER_TAIKOU_BOT") != ""'
ANCHOR_B = b"\t_start_match()"
MARKER = b"CARD_BOXER_P0_SHOT"

OUT_NAMES = {
    "reveal": "引擎帧-亮牌focus.png",
    "triple": "引擎帧-三同气功波.png",
    "sequence": "引擎帧-三连交叉反击.png",
    "scatter": "引擎帧-散牌刺拳.png",
    "draw": "引擎帧-平局对峙.png",
}

# （玩家 rank, 对手 rank, 玩家 ids, 对手 ids）
RANK_CASES = {
    "triple": ([9, 9, 9], [2, 5, 8], ["guard", "guard", "guard"], ["jab", "wave", "cross"]),
    "sequence": ([4, 5, 6], [2, 5, 8], ["sweep", "wave", "throw"], ["jab", "wave", "cross"]),
    "scatter": ([2, 5, 8], [1, 1, 2], ["cross", "wave", "backstep"], ["jab", "jab", "cross"]),
    "draw": ([1, 1, 1], [1, 1, 1], ["jab", "jab", "jab"], ["jab", "jab", "jab"]),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dominant_eol(data: bytes) -> bytes:
    crlf = data.count(b"\r\n")
    lone_lf = data.count(b"\n") - crlf
    return b"\r\n" if crlf > lone_lf else b"\n"


def gd_array_int(values) -> str:
    return "[" + ", ".join(str(v) for v in values) + "]"


def gd_array_str(values) -> str:
    return "[" + ", ".join('"%s"' % v for v in values) + "]"


def mode_lines(mode: str) -> list[bytes]:
    lines: list[str] = [
        '\tif OS.get_environment("CARD_BOXER_P0_SHOT") != "":',
        '\t\tround_phase = "fight"',
        "\t\tphase_time = 0.0",
    ]
    if mode == "reveal":
        lines += [
            "\t\ttk_bot = false",
            '\t\thand = ["guard", "guard", "guard", "cross", "uppercut"]',
            "\t\ttk_marks = [0, 1, 2]",
            "\t\t_do_taikou_reveal()",
            # 全部占位符走 %s + str()：hp 是 float，用 %d 会触发
            # Godot "String formatting error: a number is required"。
            '\t\tprint("[P0_SHOT] mode=reveal tk_phase=%s p_action=%s e_action=%s hp=%s/%s" % [str(tk_phase), String(player._action.get("id", "")), String(enemy._action.get("id", "")), str(player.hp), str(enemy.hp)])',
        ]
    else:
        p, e, pids, eids = RANK_CASES[mode]
        lines += [
            "\t\ttk_bot = true",  # 只为了打印 [TAIKOU] 行；已直接进 resolve，不会自动 confirm
            "\t\ttk_player_reveal = %s" % gd_array_int(p),
            "\t\ttk_enemy_reveal = %s" % gd_array_int(e),
            "\t\ttk_player_ids = %s" % gd_array_str(pids),
            "\t\ttk_enemy_ids = %s" % gd_array_str(eids),
            "\t\ttk_player_result = Rules.evaluate(tk_player_reveal)",
            "\t\ttk_enemy_result = Rules.evaluate(tk_enemy_reveal)",
            "\t\t_resolve_taikou()",
            # GDScript 自己的 %s 占位符不能交给 Python 的 % 格式化，
            # 用 {MODE} 占位后 replace，避免 "not enough arguments"。
            # 占位符数量必须和参数数组长度严格相等：mode 也用 %s，
            # 别硬编码后再多传一个参数（会报 not all arguments converted）。
            '\t\tprint("[P0_SHOT] mode=%s tk_phase=%s motion=%s label=%s winner=%s hp=%s/%s" % ["{MODE}", str(tk_phase), str(tk_motion_id), str(tk_motion_label), str(tk_winner), str(player.hp), str(enemy.hp)])'.replace("{MODE}", mode),
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
    if orig.count(anchor) != 1:
        print("ANCHOR_MISMATCH count=%d eol=%r" % (orig.count(anchor), eol))
        return 2
    if MARKER in orig:
        print("LEFTOVER_MARKER: a previous run was not restored")
        return 2

    TMP.mkdir(parents=True, exist_ok=True)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    modes = tuple(sys.argv[1:]) or tuple(OUT_NAMES)
    results: list[str] = []
    records: list[dict] = []

    try:
        for mode in modes:
            if mode not in OUT_NAMES:
                print("UNKNOWN_MODE %s" % mode)
                return 2
            block = eol.join(mode_lines(mode)) + eol
            mutated = orig.replace(anchor, anchor + block, 1)
            if mutated.count(MARKER) != 1 or mutated == orig:
                print("INJECT_FAILED mode=%s" % mode)
                return 2
            ARENA.write_bytes(mutated)
            if sha(ARENA.read_bytes()) != sha(mutated):
                print("WRITE_VERIFY_FAILED mode=%s" % mode)
                return 2

            shot_dir = TMP / mode
            if shot_dir.exists():
                shutil.rmtree(shot_dir)
            shot_dir.mkdir(parents=True)

            env = os.environ.copy()
            for key in ("CARD_BOXER_BOT", "CARD_BOXER_TAIKOU_BOT",
                        "CARD_BOXER_TK_SHOT", "CARD_BOXER_CAPTURE_HIT",
                        "CARD_BOXER_RAGE_START"):
                env.pop(key, None)
            env["CARD_BOXER_CAPTURE"] = str(shot_dir)
            env["CARD_BOXER_CAPTURE_AT"] = "0.35"
            env["CARD_BOXER_P0_SHOT"] = mode

            try:
                proc = subprocess.run(
                    [str(GODOT), "--path", str(GAME), "--quit-after", "900"],
                    env=env, capture_output=True, timeout=120,
                )
                rc = proc.returncode
                log = proc.stdout + b"\n--- STDERR ---\n" + proc.stderr
            except subprocess.TimeoutExpired as exc:
                rc = -1
                log = (exc.stdout or b"") + b"\n--- TIMEOUT ---\n" + (exc.stderr or b"")
            (LOGDIR / ("capture_%s.log" % mode)).write_bytes(log)

            text = log.decode("utf-8", "replace")
            shots = sorted(shot_dir.glob("shot_*.png"))
            marker_lines = [ln.strip() for ln in text.splitlines() if "[P0_SHOT]" in ln]
            taikou_lines = [ln.strip() for ln in text.splitlines() if "[TAIKOU]" in ln]
            # 只查 "SCRIPT ERROR" 会漏掉 Godot 的 "ERROR: String formatting
            # error"——首版就是这样假绿过一次（截图存下来了但 print 整行报废）。
            stderr_part = text.split("--- STDERR ---", 1)[-1]
            engine_errors = (text.count("SCRIPT ERROR")
                             + stderr_part.count("ERROR:")
                             + stderr_part.count("Parse Error"))
            has_gl = "OpenGL API" in text
            big_enough = bool(shots) and shots[0].stat().st_size > 100_000
            expected_motion = {"triple": "wave", "sequence": "cross",
                               "scatter": "jab", "draw": "", "reveal": "focus"}
            marker_ok = bool(marker_lines) and ("mode=%s" % mode) in marker_lines[0]
            if mode == "reveal":
                marker_ok = marker_ok and "p_action=focus" in marker_lines[0]
            elif expected_motion[mode]:
                marker_ok = marker_ok and ("motion=%s" % expected_motion[mode]) in marker_lines[0]
            ok = (rc == 0 and has_gl and engine_errors == 0 and marker_ok
                  and big_enough)
            print("%s: rc=%d shots=%d gl=%s engine_errors=%d marker=%s" % (
                mode, rc, len(shots), has_gl, engine_errors, marker_lines[:1]))
            records.append({
                "mode": mode, "rc": rc, "ok": ok, "shots": len(shots),
                "bytes": shots[0].stat().st_size if shots else 0,
                "marker": marker_lines, "taikou": taikou_lines,
                "gl": has_gl, "engine_errors": engine_errors,
                "marker_ok": marker_ok,
            })
            if ok:
                dest = OUT / OUT_NAMES[mode]
                shutil.copy2(shots[0], dest)
                print("  saved %s (%d B)" % (dest.name, dest.stat().st_size))
                results.append("OK %s" % mode)
            else:
                results.append("FAIL %s" % mode)
    finally:
        ARENA.write_bytes(orig)
        after = ARENA.read_bytes()
        ok = sha(after) == orig_sha and MARKER not in after
        print("RESTORE %s sha256=%s" % ("OK" if ok else "FAILED", sha(after)))
        results.append("OK RESTORE" if ok else "FAIL RESTORE")

    import json
    (OUT / "capture_result.json").write_text(
        json.dumps({"records": records, "restore_ok": ok}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print("RESULT: %s" % " | ".join(results))
    expected = len(modes) + 1
    return 0 if all(r.startswith("OK") for r in results) and len(results) == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
