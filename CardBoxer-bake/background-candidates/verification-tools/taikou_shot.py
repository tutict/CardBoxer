"""Capture the two HUMAN-input HUD states of the Taikou IV P0 loop.

The bot-driven screenshots archived earlier never show tk_marks (the bot
confirms immediately, so the selection highlight is never drawn). This
script temporarily injects a tiny verification block into arena.gd, runs
the NORMAL main scene headless, and restores arena.gd byte-for-byte.

Discipline (same as mode_switch.py / hud_mutate.py):
  * binary read/write only -- no text-mode newline normalisation
  * the anchor must match exactly once, otherwise abort
  * restore runs in a finally block and is proven by sha256
  * no game source is left modified, no new file inside the game project
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
ARENA = GAME / "scripts" / "arena.gd"
BAKE_SHOTS = Path(r"D:\Projects\CardBoxer\CardBoxer-bake\background-candidates\classic-battle-p0")
TMP = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-tk-shots")
LOGDIR = TMP / "logs"
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")

ANCHOR_LINE = b'\ttk_bot = OS.get_environment("CARD_BOXER_TAIKOU_BOT") != ""'
CALL_LINE = b"\t_start_match()"
MARKER = b"CARD_BOXER_TK_SHOT"

BLOCK_LINES = [
    b'\tif OS.get_environment("CARD_BOXER_TK_SHOT") != "":',
    b'\t\tround_phase = "fight"',
    b"\t\tphase_time = 0.0",
    b'\t\tif OS.get_environment("CARD_BOXER_TK_SHOT") == "select":',
    b"\t\t\t_do_taikou_discard()",
    b"\t\t\t_taikou_toggle(1)",
    b"\t\t\t_taikou_toggle(3)",
    b"\t\t\t_taikou_toggle(4)",
    b"\t\telse:",
    b"\t\t\t_taikou_toggle(0)",
    b"\t\t\t_taikou_toggle(2)",
    b'\t\tprint("[TK_SHOT] tk_phase=%s marks=%s" % [tk_phase, str(tk_marks)])',
]

OUT_NAMES = {"discard": "discard-selection.png", "select": "card-selection.png"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dominant_eol(data: bytes) -> bytes:
    crlf = data.count(b"\r\n")
    lone_lf = data.count(b"\n") - crlf
    return b"\r\n" if crlf > lone_lf else b"\n"


def main() -> int:
    for path in (GODOT, ARENA, GAME / "project.godot"):
        if not path.exists():
            print("MISSING: %s" % path)
            return 2

    orig = ARENA.read_bytes()
    orig_sha = sha(orig)
    eol = dominant_eol(orig)
    anchor = ANCHOR_LINE + eol + CALL_LINE + eol
    if orig.count(anchor) != 1:
        print("ANCHOR_MISMATCH count=%d eol=%r" % (orig.count(anchor), eol))
        return 2
    if MARKER in orig:
        print("LEFTOVER_MARKER: a previous run was not restored")
        return 2

    block = eol.join(BLOCK_LINES) + eol
    mutated = orig.replace(anchor, anchor + block, 1)
    if mutated.count(MARKER) != 2 or mutated == orig:
        print("INJECT_FAILED")
        return 2

    TMP.mkdir(parents=True, exist_ok=True)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    modes = tuple(sys.argv[1:]) or ("discard", "select")

    try:
        for mode in modes:
            if mode not in OUT_NAMES:
                print("UNKNOWN_MODE %s" % mode)
                return 2
            shot_dir = TMP / mode
            if shot_dir.exists():
                shutil.rmtree(shot_dir)
            shot_dir.mkdir(parents=True)

            ARENA.write_bytes(mutated)
            if sha(ARENA.read_bytes()) != sha(mutated):
                print("WRITE_VERIFY_FAILED")
                return 2

            env = os.environ.copy()
            for key in ("CARD_BOXER_BOT", "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_CAPTURE_HIT"):
                env.pop(key, None)
            env["CARD_BOXER_CAPTURE"] = str(shot_dir)
            env["CARD_BOXER_CAPTURE_AT"] = "1.0"
            env["CARD_BOXER_TK_SHOT"] = mode

            try:
                # NOTE: --headless uses the dummy driver, where
                # RenderingServer.frame_post_draw never fires; _maybe_capture()
                # awaits it forever -> no PNG and no quit(). The archived
                # working captures all had a real GL context (see
                # godot-capture.log: "OpenGL API 3.3.0 NVIDIA").
                # --quit-after is only a hang guard, not the exit mechanism.
                proc = subprocess.run(
                    [str(GODOT), "--path", str(GAME), "--quit-after", "900"],
                    env=env, capture_output=True, timeout=120,
                )
                rc = proc.returncode
                log = proc.stdout + b"\n--- STDERR ---\n" + proc.stderr
            except subprocess.TimeoutExpired as exc:
                rc = -1
                log = (exc.stdout or b"") + b"\n--- TIMEOUT ---\n" + (exc.stderr or b"")
            (LOGDIR / ("%s.log" % mode)).write_bytes(log)

            shots = sorted(shot_dir.glob("shot_*.png"))
            text = log.decode("utf-8", errors="replace")
            script_errors = text.count("SCRIPT ERROR")
            marker_lines = [ln.strip() for ln in text.splitlines() if "[TK_SHOT]" in ln]
            big_enough = bool(shots) and shots[0].stat().st_size > 100_000

            print("%s: rc=%d shots=%d script_errors=%d marker=%s" % (
                mode, rc, len(shots), script_errors, marker_lines[:1],
            ))
            if rc != 0 or script_errors or not marker_lines or not big_enough:
                print("CAPTURE_FAILED mode=%s" % mode)
                results.append("FAIL %s" % mode)
                continue

            dest = BAKE_SHOTS / OUT_NAMES[mode]
            shutil.copy2(shots[0], dest)
            print("  saved %s (%d B)" % (dest.name, dest.stat().st_size))
            results.append("OK %s" % mode)
    finally:
        ARENA.write_bytes(orig)
        after = ARENA.read_bytes()
        ok = sha(after) == orig_sha and MARKER not in after
        print("RESTORE %s sha256=%s" % ("OK" if ok else "FAILED", sha(after)))
        results.append("OK RESTORE" if ok else "FAIL RESTORE")

    print("RESULT: %s" % " | ".join(results))
    expected = len(modes) + 1  # one capture result per mode + RESTORE
    return 0 if all(r.startswith("OK") for r in results) and len(results) == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
