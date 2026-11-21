"""证明 redraw_gate_check 的 hand-change 断言是既有抖动，与本轮改动无关。

做法：把原版 hud.gd（备份）与接线后 hud.gd 各跑 N 次同一条自检，
记录 PASS/FAIL 与失败断言名。全程二进制读写 + sha256 还原证明。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
TARGET = GAME / "scripts" / "hud.gd"
ORIGINAL = HERE / "orig" / "pre-portrait-ui" / "scripts" / "hud.gd"
TMP = HERE / "logs" / "hud_current_bytes.tmp"
SCRIPT = "res://tests/redraw_gate_check.gd"
N = 30


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_once() -> dict:
    r = subprocess.run(
        [str(GODOT), "--headless", "--path", str(GAME), "--script", SCRIPT],
        capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
    )
    out = r.stdout
    m = re.search(r"REDRAW GATE CHECK: (\d+)/(\d+) passed", out)
    fails = re.findall(r"FAIL: (.+)", out)
    return {
        "exit": r.returncode,
        "passed": int(m.group(1)) if m else None,
        "total": int(m.group(2)) if m else None,
        "failures": fails,
    }


def batch(label: str) -> list[dict]:
    return [dict(run=i + 1, **run_once()) for i in range(N)]


def main() -> None:
    if not ORIGINAL.is_file():
        raise RuntimeError(f"missing backup: {ORIGINAL}")
    current = TARGET.read_bytes()
    original = ORIGINAL.read_bytes()
    TMP.write_bytes(current)
    result: dict = {"runs_per_variant": N, "current_sha256": sha(current),
                    "original_sha256": sha(original)}
    try:
        TARGET.write_bytes(original)
        assert TARGET.read_bytes() == original
        result["original_hud"] = batch("original")
        TARGET.write_bytes(current)
        assert TARGET.read_bytes() == current
        result["wired_hud"] = batch("wired")
    finally:
        # 无论如何都把接线后的版本还原回去，并做二进制 + sha256 证明
        restored = TMP.read_bytes()
        TARGET.write_bytes(restored)
        after = TARGET.read_bytes()
        result["restore_sha256"] = sha(after)
        result["restore_identical"] = after == current == restored

    for key in ("original_hud", "wired_hud"):
        rows = result[key]
        print(f"{key}: " + ", ".join(
            f"{r['run']}={'PASS' if r['exit'] == 0 else 'FAIL'}({r['passed']}/{r['total']})"
            for r in rows))
        print(f"  failure kinds: {sorted({f for r in rows for f in r['failures']})}")
    print(f"RESTORE_IDENTICAL={result['restore_identical']} sha={result['restore_sha256']}")
    (HERE / "probe_flaky.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("FLAKY_PROBE_OK" if result["restore_identical"] else "FLAKY_PROBE_RESTORE_FAILED")


if __name__ == "__main__":
    main()
