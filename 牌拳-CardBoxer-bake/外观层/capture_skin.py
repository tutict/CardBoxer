"""Capture one in-engine frame with the skin layer ON and one with it OFF.

The OFF frame is produced by a temporary, byte-proven mutation of
`const SKIN_V2 := true` -> false. Both frames use the SAME capture time and
SAME scene, so every differing pixel is caused by the skin layer alone.

Must run WITHOUT --headless: the dummy driver never emits
RenderingServer.frame_post_draw, so _maybe_capture() hangs forever.
`--quit-after` is only a hang guard; the capture itself calls quit().
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
FIGHTER = GAME / "scripts" / "fighter.gd"
OUT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\外观层")
TMP = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-skin-shots")
LOGDIR = TMP / "logs"

NEEDLE = b"const SKIN_V2 := true"
MUTANT = b"const SKIN_V2 := false"
OUT_NAMES = {"on": "外观层-开启.png", "off": "外观层-回退.png"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(mode: str, env_extra: dict[str, str]) -> bool:
    shot_dir = TMP / mode
    if shot_dir.exists():
        shutil.rmtree(shot_dir)
    shot_dir.mkdir(parents=True)

    env = os.environ.copy()
    for key in ("CARD_BOXER_CAPTURE_HIT", "CARD_BOXER_TK_SHOT"):
        env.pop(key, None)
    env["CARD_BOXER_CAPTURE"] = str(shot_dir)
    env["CARD_BOXER_CAPTURE_AT"] = "2.0"
    env["CARD_BOXER_TAIKOU_BOT"] = "1"
    env.update(env_extra)

    try:
        proc = subprocess.run(
            [str(GODOT), "--path", str(GAME), "--quit-after", "6000"],
            env=env, capture_output=True, timeout=180,
        )
        rc = proc.returncode
        log = proc.stdout + b"\n--- STDERR ---\n" + proc.stderr
    except subprocess.TimeoutExpired as exc:
        rc = -1
        log = (exc.stdout or b"") + b"\n--- TIMEOUT ---\n" + (exc.stderr or b"")
    (LOGDIR / ("%s.log" % mode)).write_bytes(log)

    text = log.decode("utf-8", "replace")
    shots = sorted(shot_dir.glob("shot_*.png"))
    has_gl = "OpenGL API" in text
    script_errors = text.count("SCRIPT ERROR")
    big_enough = bool(shots) and shots[0].stat().st_size > 100_000
    ok = rc == 0 and has_gl and script_errors == 0 and big_enough
    print(
        "%s: rc=%d shots=%d gl=%s script_errors=%d bytes=%s -> %s"
        % (mode, rc, len(shots), has_gl, script_errors,
           shots[0].stat().st_size if shots else "-", "OK" if ok else "FAIL")
    )
    if ok:
        dest = OUT / OUT_NAMES[mode]
        shutil.copy2(shots[0], dest)
        print("  saved %s (%d B)" % (dest.name, dest.stat().st_size))
    return ok


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    orig = FIGHTER.read_bytes()
    orig_sha = sha(orig)
    if orig.count(NEEDLE) != 1:
        print("ANCHOR_MISMATCH count=%d" % orig.count(NEEDLE))
        return 2

    results: list[bool] = []
    try:
        results.append(capture("on", {}))

        changed = orig.replace(NEEDLE, MUTANT, 1)
        FIGHTER.write_bytes(changed)
        if sha(FIGHTER.read_bytes()) != sha(changed):
            print("WRITE_VERIFY_FAILED")
            FIGHTER.write_bytes(orig)
            return 2
        results.append(capture("off", {}))
    finally:
        FIGHTER.write_bytes(orig)
        ok = sha(FIGHTER.read_bytes()) == orig_sha
        print("RESTORE %s sha256=%s" % ("OK" if ok else "FAILED", sha(FIGHTER.read_bytes())))
        if not ok:
            return 2

    print("RESULT: %d/%d captures OK" % (sum(results), len(results)))
    return 0 if all(results) and len(results) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
