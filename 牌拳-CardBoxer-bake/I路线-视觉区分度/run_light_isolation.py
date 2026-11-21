"""I 路线诊断驱动：读回 on/plain/again 三态两层灯能量与材质 override。

落盘 data/light_isolation_i.json，并判定玩家层是否真的没被改。
用法：python run_light_isolation.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
SRC = HERE / "tests" / "light_isolation_probe.gd"
DST = GAME / "tests" / "light_isolation_probe.gd"
OUT = HERE / "data" / "light_isolation_i.json"


def main() -> int:
    shutil.copyfile(SRC, DST)
    env = os.environ.copy()
    env.pop("CARD_BOXER_3D", None)
    env.pop("CARD_BOXER_FOE_VISUAL", None)
    p = subprocess.run(
        [str(GODOT), "--path", str(GAME), "--resolution", "1280x720",
         "--quit-after", "900", "--script",
         "res://tests/light_isolation_probe.gd"],
        env=env, capture_output=True, timeout=300, cwd=str(GAME))
    text = (p.stdout + b"\n--- STDERR ---\n"
            + p.stderr).decode("utf-8", "replace")
    (HERE / "logs" / "godot_light_isolation.log").write_text(
        text, encoding="utf-8")
    marker = "ILIGHT_JSON "
    line = next((l for l in text.splitlines()
                 if l.startswith(marker)), None)
    payload = json.loads(line[len(marker):]) if line else {"error": "no marker"}
    rows = {r["tag"]: r for r in payload.get("rows", [])}
    on, plain, again = (rows.get(t, {}) for t in ("on", "plain", "again"))
    pl_on = on.get("player_lights", [])
    pl_plain = plain.get("player_lights", [])
    foe_on = on.get("foe_lights", [])
    foe_plain = plain.get("foe_lights", [])
    checks = {
        "rc0": p.returncode == 0,
        "marker": line is not None,
        "no_errors": ("SCRIPT ERROR" not in text
                      and "Parse Error" not in text),
        "three_states": len(rows) == 3,
        "four_lights_each": all(len(v) == 4 for v in
                                (pl_on, pl_plain, foe_on, foe_plain)),
        "player_lights_unchanged": pl_on == pl_plain,
        # v2 明确「两层灯一个都不改」；v1 里 foe 灯会变，已归档为负结果。
        "foe_lights_unchanged": foe_on == foe_plain,
        "all_lights_identical_across_states": (
            on.get("player_lights") == plain.get("player_lights")
            == again.get("player_lights")
            and on.get("foe_lights") == plain.get("foe_lights")
            == again.get("foe_lights")),
        "player_no_override": all(r.get("player_overrides") == 0
                                  for r in rows.values()),
        # v3：3D 材质 override 整套退役，任何状态都不得出现。
        "no_3d_override_any_state": all(r.get("foe_overrides") == 0
                                        for r in rows.values()),
    }
    ok = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "payload": payload, "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "player_lights_equal_but_pixels_changed": (
            checks["player_lights_unchanged"]),
        "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for t in ("on", "plain", "again"):
        r = rows.get(t, {})
        print(t, "player_energy",
              [x["energy"] for x in r.get("player_lights", [])],
              "foe_energy",
              [x["energy"] for x in r.get("foe_lights", [])],
              "overrides", r.get("player_overrides"),
              r.get("foe_overrides"))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("LIGHT_ISOLATION_I_OK" if ok else "LIGHT_ISOLATION_I_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
