"""跑 tests/key_bench.gd 并把 str()/hash() 微基准落成 JSON。"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")


def main() -> int:
    p = subprocess.run(
        [str(GODOT), "--headless", "--path", str(GAME),
         "--script", "res://tests/key_bench.gd"],
        capture_output=True, timeout=120, cwd=str(GAME))
    text = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
    (HERE / "logs" / "key_bench.log").write_text(text, encoding="utf-8")
    m = re.search(r"KEY_BENCH N=(\d+) str_us=([\d.]+) hash_us=([\d.]+) ratio=([\d.]+)", text)
    if not m or p.returncode != 0:
        print("KEY_BENCH FAILED rc=%s" % p.returncode)
        print(text[-1500:])
        return 1
    payload = {"n": int(m.group(1)), "str_us": float(m.group(2)),
               "hash_us": float(m.group(3)), "ratio": float(m.group(4))}
    (HERE / "key_bench.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("KEY_BENCH OK %s" % payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
