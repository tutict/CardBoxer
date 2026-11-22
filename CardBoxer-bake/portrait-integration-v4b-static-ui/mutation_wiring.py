"""变异验证：证明 tests/portrait_wiring_check.gd 的四组断言真的有牙。

纪律：
  * 二进制读写 + sha256 还原证明，不用文本读写；
  * 锚点 raw.count(old)==1，失配报 DID NOT RUN 并计入未证明，不崩在半路；
  * 每组点名一条保持绿色的哨兵断言；
  * clean re-run 必须全绿；
  * MUTATION_SELFTEST=1 故意让 M1 锚点失配，证明 DID NOT RUN 分支生效。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
GODOT = Path(r"C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64_console.exe")
HUD = GAME / "scripts" / "hud.gd"
GATE = GAME / "tests" / "redraw_gate_check.gd"
IMPORT = GAME / "assets" / "portraits" / "card_p1.png.import"
SCRIPT = "res://tests/portrait_wiring_check.gd"
SELFTEST = os.environ.get("MUTATION_SELFTEST") == "1"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ctex_path() -> Path:
    txt = IMPORT.read_text(encoding="utf-8")
    m = re.search(r'path="(res://[^"]+)"', txt)
    if not m:
        raise RuntimeError("card_p1.png.import has no ctex path")
    return GAME / m.group(1).replace("res://", "")


CTEX = ctex_path()
SENTINEL = "png sha256 matches: card_p55.png"


def run_guard() -> dict:
    r = subprocess.run(
        [str(GODOT), "--headless", "--path", str(GAME), "--script", SCRIPT],
        capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace",
    )
    out = r.stdout
    m = re.search(r"PORTRAIT WIRING CHECK: (\d+)/(\d+) passed", out)
    return {
        "exit": r.returncode,
        "passed": int(m.group(1)) if m else None,
        "failures": re.findall(r"FAIL: (.+)", out),
        "green": m is not None and r.returncode == 0,
    }


def needle_replacer(path: Path, old: bytes, new: bytes, sentinel: str):
    def apply(raw: bytes) -> bytes:
        return raw.replace(old, new, 1)

    return (path, old, apply, sentinel)


def truncate_replacer(path: Path, sentinel: str):
    def apply(raw: bytes) -> bytes:
        return b""

    return (path, b"__TRUNCATE__", apply, sentinel)


def build_cases() -> list[dict]:
    return [
        {
            "id": "M1", "label": "删掉 _visual_key() 的两个新 token",
            "target": HUD,
            "needle": b"\t\t_profile_page, portrait_ui_enabled,\n",
            "replacement": b"\t\t# M1: token removed\n",
            "sentinel": SENTINEL,
            "expect_fail_contains": "visual key covers _profile_page",
        },
        {
            "id": "M2", "label": "注释掉一张头像的 draw_texture_rect",
            "target": HUD,
            "needle": b"\tdraw_texture_rect(TEX_AVATAR_P, Rect2(2, 2, 40, 40), false)\n",
            "replacement": b"\t# M2: draw removed\n",
            "sentinel": SENTINEL,
            "expect_fail_contains": "texture draw calls present",
        },
        {
            "id": "M3", "label": "把 card_p1 的 .ctex 清空（贴图真空）",
            "target": CTEX,
            "needle": None,          # 整文件截断，不用锚点
            "replacement": None,
            "sentinel": "png sha256 matches: card_p1.png",
            "expect_fail_contains": "ctex exists and nonempty: card_p1.png",
        },
        {
            "id": "M4", "label": "把插画卡位从第 1/5 张改到第 2/4 张",
            "target": HUD,
            "needle": b"i == 0 or i == 4",
            "replacement": b"i == 1 or i == 3",
            "sentinel": SENTINEL,
            "expect_fail_contains": "only card 1/5 get portrait background",
        },
        {
            "id": "M5", "label": "把已修好的抖动手牌断言退回硬写 wave",
            "target": GATE,
            "needle": b'\ta.hand[0] = "wave" if String(a.hand[0]) != "wave" else "jab"\n',
            "replacement": b'\ta.hand[0] = "wave"\n',
            "sentinel": SENTINEL,
            "expect_fail_contains": "flaky hand-change assertion stays deterministic",
        },
        {
            "id": "M6", "label": "让 TAB 边沿不翻页",
            "target": HUD,
            "needle": b"\t\t_profile_page = (_profile_page + 1) % 3\n",
            "replacement": b"\t\t_profile_page = _profile_page\n",
            "sentinel": SENTINEL,
            "expect_fail_contains": "TAB down advances profile page once",
        },
    ]


def main() -> None:
    cases = build_cases()
    if SELFTEST:
        cases[0]["needle"] = b"\t\t__NEVER_MATCHES_999__,\n"

    originals = {p: p.read_bytes() for p in {c["target"] for c in cases}}
    rows = []
    try:
        for case in cases:
            path: Path = case["target"]
            raw = originals[path]
            if case["needle"] is None:
                mutated = b""
            else:
                needle: bytes = case["needle"]
                count = raw.count(needle)
                if count != 1:
                    rows.append({
                        "id": case["id"], "status": "DID NOT RUN",
                        "reason": f"anchor count={count} (need 1)",
                        "label": case["label"],
                    })
                    print(f"{case['id']} DID NOT RUN anchor count={count}")
                    continue
                mutated = raw.replace(needle, case["replacement"], 1)

            path.write_bytes(mutated)
            result = run_guard()
            caught = (not result["green"]
                      and any(case["expect_fail_contains"] in f for f in result["failures"]))
            sentinel_green = case["sentinel"] not in result["failures"]
            rows.append({
                "id": case["id"], "label": case["label"],
                "status": "CAUGHT" if caught and sentinel_green else "MISSED",
                "guard_exit": result["exit"],
                "guard_failures": result["failures"][:8],
                "expected_failure_present": any(case["expect_fail_contains"] in f
                                                for f in result["failures"]),
                "sentinel_green": sentinel_green,
                "sentinel": case["sentinel"],
            })
            print(f"{case['id']} {rows[-1]['status']} "
                  f"exit={result['exit']} failures={len(result['failures'])} "
                  f"sentinel_green={sentinel_green}")
            # 每组立刻还原，避免污染下一组
            path.write_bytes(raw)
    finally:
        restore = {}
        for path, raw in originals.items():
            path.write_bytes(raw)
            after = path.read_bytes()
            restore[str(path.relative_to(GAME))] = after == raw and sha(after) == sha(raw)
        clean = run_guard()

    caught_n = sum(r["status"] == "CAUGHT" for r in rows)
    did_not_run = sum(r["status"] == "DID NOT RUN" for r in rows)
    all_proven = caught_n == len(cases) and did_not_run == 0 and all(restore.values()) and clean["green"]
    result = {
        "selftest": SELFTEST,
        "total": len(cases), "caught": caught_n, "did_not_run": did_not_run,
        "restore": restore, "restore_all_ok": all(restore.values()),
        "clean_rerun": clean, "all_proven": all_proven,
        "rows": rows,
    }
    (HERE / ("mutation_selftest_result.json" if SELFTEST else "mutation_wiring_result.json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"TOTAL={len(cases)} CAUGHT={caught_n} DID_NOT_RUN={did_not_run} "
          f"RESTORE={sum(restore.values())}/{len(restore)} CLEAN={clean['green']}")
    print("MUTATION_WIRING_VERIFIED" if all_proven else "MUTATION_WIRING_FAILED")


if __name__ == "__main__":
    main()
