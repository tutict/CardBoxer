"""复跑 30 次，证明修好后的 redraw_gate_check 不再随机假红。

不换文件、不写工程，只跑同一条自检并统计退出码/失败断言。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SCRIPT = "res://tests/redraw_gate_check.gd"
N = 30


def main() -> None:
    rows = []
    for i in range(N):
        r = subprocess.run(
            [str(GODOT), "--headless", "--path", str(GAME), "--script", SCRIPT],
            capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
        )
        m = re.search(r"REDRAW GATE CHECK: (\d+)/(\d+) passed", r.stdout)
        rows.append({
            "run": i + 1, "exit": r.returncode,
            "passed": int(m.group(1)) if m else None,
            "total": int(m.group(2)) if m else None,
            "failures": re.findall(r"FAIL: (.+)", r.stdout),
        })
    fails = [r for r in rows if r["exit"] != 0 or r["passed"] != r["total"] or r["failures"]]
    result = {"runs": N, "failures": len(fails), "rows": rows}
    (HERE / "verify_flaky_fix.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"RUNS={N} FAILURES={len(fails)}")
    print(f"VERDICTS={sorted({r['passed'] for r in rows})}")
    print("FLAKY_FIX_VERIFIED" if not fails else "FLAKY_FIX_FAILED")


if __name__ == "__main__":
    main()
