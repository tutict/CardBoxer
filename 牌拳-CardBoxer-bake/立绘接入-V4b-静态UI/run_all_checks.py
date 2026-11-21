"""跑五道门 + 全量自检，逐条记退出码与原始输出。

不动工程，只在 -bake/logs/ 写日志与 result.json。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
LOGS = HERE / "logs" / "checks"
LOGS.mkdir(parents=True, exist_ok=True)

CHECKS = [
    ("motion_check", "res://tests/motion_check.gd"),
    ("pose_probe", "res://tests/pose_probe.gd"),
    ("duel_probe", "res://tests/duel_probe.gd"),
    ("reach_probe", "res://tests/reach_probe.gd"),
    ("feet_probe", "res://tests/feet_probe.gd"),
    ("fighter_skin_check", "res://tests/fighter_skin_check.gd"),
    ("battle_motion_p0_check", "res://tests/battle_motion_p0_check.gd"),
    ("battle_rhythm_check", "res://tests/battle_rhythm_check.gd"),
    ("engine_opt_check", "res://tests/engine_opt_check.gd"),
    ("redraw_gate_check", "res://tests/redraw_gate_check.gd"),
    ("taikou_flow_check", "res://tests/taikou_flow_check.gd"),
    ("taikou_rage_check", "res://tests/taikou_rage_check.gd"),
    ("taikou_rules_check", "res://tests/taikou_rules_check.gd"),
    ("combo_check", "res://scripts/combo_check.gd"),
    ("portrait_wiring_check", "res://tests/portrait_wiring_check.gd"),
]


def main() -> None:
    rows = []
    for name, script in CHECKS:
        p = GAME / script.replace("res://", "")
        if not p.is_file():
            rows.append({"name": name, "script": script, "status": "MISSING", "exit": -1})
            print(f"{name:26s} MISSING {script}")
            continue
        try:
            r = subprocess.run(
                [str(GODOT), "--headless", "--path", str(GAME), "--script", script],
                capture_output=True, text=True, timeout=180,
                encoding="utf-8", errors="replace",
            )
            out, err, code = r.stdout, r.stderr, r.returncode
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            err = "TIMEOUT"
            code = -9
        (LOGS / f"{name}.log").write_text(out + "\n--- STDERR ---\n" + err, encoding="utf-8")
        # Godot 脚本常用 assert / push_error；退出码为 0 且无 ERROR/FAILED 字样才算绿
        # combo_check 在 headless 退出时固定打印下面几行 RID / ObjectDB 泄漏警告。
        # 这是既有的 Godot 退出噪音，不是测试失败：-bake 下 侧身节奏接线/、
        # 动作接线P0/、引擎优化/、按需重绘/ 四份历史 scripts_combo_check.log
        # 都有同一段，且它们的汇总同样是 8/8 passed + exit 0。
        benign = (
            "WARNING: 8 RIDs", "WARNING: ObjectDB instances leaked at exit",
            "ERROR: 1 resources still in use at exit", "run with --verbose",
            "at: _free_rids", "at: cleanup", "at: clear",
        )
        clean_err = "\n".join(
            ln for ln in err.splitlines()
            if not any(b in ln for b in benign)
        )
        text = out + "\n" + clean_err
        # 只认明确的失败标记；"0 failed" 这类正常汇总不误判。
        bad_markers = ["SCRIPT ERROR", "Parse Error", "Assertion failed",
                       "FAILED", "ERROR:", "Condition \""]
        failed_marker = [k for k in bad_markers if k in text]
        ok = code == 0 and not failed_marker
        rows.append({
            "name": name, "script": script, "exit": code,
            "status": "PASS" if ok else "FAIL",
            "bad_markers": failed_marker,
            "stdout_tail": out.strip().splitlines()[-4:],
        })
        print(f"{name:26s} exit={code:3d} {'PASS' if ok else 'FAIL'}  | {out.strip().splitlines()[-1:] }")

    passed = sum(r["status"] == "PASS" for r in rows)
    result = {"total": len(rows), "passed": passed, "failed": [r["name"] for r in rows if r["status"] != "PASS"], "rows": rows}
    (HERE / "checks_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"TOTAL={len(rows)} PASSED={passed} FAILED={result['failed']}")
    print("ALL_CHECKS_GREEN" if passed == len(rows) else "ALL_CHECKS_FAILED")


if __name__ == "__main__":
    main()
