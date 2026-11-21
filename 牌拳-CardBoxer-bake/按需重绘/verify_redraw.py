"""按需重绘承重判据（24 条）。

只读盘上的源码、归档 JSON、PNG 和日志；不启动 Godot，不改任何文件。
环境 REDRAW_VERIFY_SKIP_SHA=1 时跳过 V23（变异验证期间用来避免「任意
字节变动都被通用哈希判据抓住」，让每条变异必须打中自己的具体判据）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
BASELINE = HERE / "baseline"
SHOTS = HERE / "对比帧"
PERF = HERE / "性能A-B"
RHYTHM = HERE / "节奏回归帧1280"
SKIP_SHA = os.environ.get("REDRAW_VERIFY_SKIP_SHA") == "1"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def png_info(p: Path) -> tuple[int, int, int]:
    im = Image.open(p)
    return p.stat().st_size, im.width, im.height


def real_lines(src: str, form: str) -> int:
    n = 0
    for ln in src.split("\n"):
        s = ln.strip()
        if s.startswith("#"):
            continue
        i = ln.find(form)
        if i < 0:
            continue
        if "#" in ln[:i]:
            continue
        n += 1
    return n


def slice_of(src: str, begin: str, end: str) -> str:
    i, j = src.find(begin), src.find(end)
    return src[i:j] if i >= 0 and j > i else ""


CHECKS: list[tuple[str, bool, str]] = []


def expect(cid: str, cond: bool, detail: str) -> None:
    CHECKS.append((cid, bool(cond), detail))


def main() -> int:
    arena = (GAME / "scripts/arena.gd").read_text(encoding="utf-8")
    hud = (GAME / "scripts/hud.gd").read_text(encoding="utf-8")
    fx = (GAME / "scripts/fx_layer.gd").read_text(encoding="utf-8")
    fighter = (GAME / "scripts/fighter.gd").read_text(encoding="utf-8")
    base = jload(HERE / "源码基线.json")
    cur = jload(HERE / "当前源码指纹.json")

    # V01 备份完整
    ok = True
    for rel, rec in base.items():
        p = BASELINE / rel
        if not p.is_file() or sha(p.read_bytes()) != rec["sha256"]:
            ok = False
    expect("V01", ok, "baseline 5 files byte-identical")

    expect("V02", all(sha((GAME / rel).read_bytes()) == rec["sha256"]
                      for rel in ("scripts/fighter.gd", "project.godot")
                      for rec in [base[rel]]),
           "fighter.gd / project.godot untouched")
    expect("V03", all(sha((GAME / rel).read_bytes()) != base[rel]["sha256"]
                      for rel in ("scripts/arena.gd", "scripts/hud.gd", "scripts/fx_layer.gd")),
           "arena/hud/fx_layer actually changed")

    expect("V04", real_lines(arena, "var redraw_gate_enabled := true") == 1,
           "gate defaults ON")
    expect("V05", real_lines(arena, "var _force_redraw := true") == 1
           and real_lines(arena, "func force_redraw() -> void:") == 1,
           "first-frame force + public force_redraw()")
    proc = slice_of(arena, "func _process(delta: float) -> void:",
                    "func _capture_hit_shot()")
    expect("V06", real_lines(proc, "_request_redraw()") == 3
           and real_lines(proc, "queue_redraw()") == 0,
           "3 branches gated, 0 bare queue_redraw in _process")
    expect("V07", real_lines(proc, "_maybe_capture()") == 2,
           "capture chain kept in hitstop + main")

    req = slice_of(arena, "func _request_redraw() -> void:",
                   "# ── 每帧 ──")
    first_stmt = req.split("\n")[1].strip() if "\n" in req else ""
    expect("V08", first_stmt == "var key := _arena_visual_key()"
           and "fx_layer.queue_redraw()" in req
           and "\t\tqueue_redraw()" in req
           and 'redraw_stats["arena_queued"]' in req
           and 'redraw_stats["arena_skipped"]' in req,
           "_request_redraw body really queues/skips")
    akey = slice_of(arena, "func _arena_visual_key() -> String:",
                    "func _request_redraw()")
    tokens = ["_shake > 0.05", "_flash", "player.position.x", "enemy.position.x",
              "world.position", "fx_layer.position", "effects", "projectiles",
              "tk_rhythm_t", "tk_rhythm_winner", "tk_rhythm_hit", "visual_shift"]
    expect("V09", all(t in akey for t in tokens),
           "arena key covers all draw inputs (%d tokens)" % len(tokens))

    hkey = slice_of(hud, "func _visual_key() -> String:",
                    "func _process(delta: float) -> void:")
    fields = sorted(set(re.findall(r"arena\.([A-Za-z_][A-Za-z0-9_]*)", hud)))
    plumbing = {"redraw_gate_enabled", "redraw_stats"}
    missing = [f for f in fields if f not in plumbing and ("a.%s" % f) not in hkey]
    expect("V10", not missing,
           "hud key covers arena.* fields (%d, missing=%s)" % (len(fields), missing))
    hproc = slice_of(hud, "func _process(delta: float) -> void:",
                     "func _draw() -> void:")
    expect("V11", "_time if pulsing else -1.0" in hkey
           and real_lines(hud, "var dirty: bool =") == 1
           and "or key != _last_visual_key" in hproc
           and "if dirty:" in hproc,
           "pulse clock conditional + hud queue_redraw gated by key")
    expect("V12", "redraw_stats" not in fighter and "_visual_key" not in fighter,
           "fighter.gd deliberately NOT gated")
    expect("V13", "fx_draws" in fx and "fx_draw_us" in fx,
           "fx_layer draw/时间 counters wired")

    checks = jload(HERE / "all_checks.json")
    gate_log = (HERE / "logs" / "tests_redraw_gate_check.log").read_text(encoding="utf-8")
    expect("V14", checks["total"] == 14 and checks["failed"] == []
           and checks["result"] == "ALL GREEN"
           and "REDRAW GATE CHECK: 72/72 passed" in gate_log,
           "14/14 engine self-checks ALL GREEN")

    names = ["A_静止-关闭.png", "B_静止-开启.png", "C_变更-开启.png",
             "D_变更-关闭.png", "E_回退-开启.png"]
    infos = [png_info(SHOTS / n) for n in names]
    expect("V15", all(b > 100000 and w == 1280 and h == 720 for b, w, h in infos),
           "5 injected-state PNGs valid 1280x720")
    cmp_ = jload(SHOTS / "compare_result.json")
    expect("V16", cmp_["静止像素等价"]["changed_px"] == 0
           and cmp_[names[0]] == cmp_[names[1]],
           "static frame: gate ON/OFF pixel-identical + byte-identical")
    expect("V17", cmp_["变更后像素等价"]["changed_px"] == 0
           and cmp_["回退像素等价"]["changed_px"] == 0,
           "after change / after revert still pixel-identical")
    expect("V18", cmp_["状态变化必须可见(非0)"]["changed_px"] >= 1000,
           "state change is observable (no stale HUD)")

    summ = jload(SHOTS / "probe_summary.json")
    rows = {r["name"]: r for r in summ["rows"]}
    expect("V19", rows["off"]["draws"] == 270 and rows["off"]["draw_us"] > 10000
           and rows["on"]["draws"] == 0 and rows["on"]["draw_us"] == 0
           and rows["changed_on"]["draws"] == 1
           and rows["back_on"]["draws"] == 1,
           "5-phase draw accounting: 270 -> 0, changes draw exactly once")

    ab = jload(PERF / "ab_result.json")
    procs = ab["TIME_PROCESS_off"] + ab["TIME_PROCESS_on"]
    expect("V20", ab["repeat"] == 3
           and all(p["changed_px"] == 0 for p in ab["pairs"])
           and ab["draw_us_mean_off"] > 1000
           and ab["draw_us_mean_on"] == 0
           and all(p["gate1"]["skips"] > 0 and p["gate0"]["skips"] == 0
                   for p in ab["pairs"])
           and all(p["gate0"]["prims"] == p["gate1"]["prims"]
                   and p["gate0"]["calls"] == p["gate1"]["calls"]
                   for p in ab["pairs"])
           and "retired" in ab["TIME_PROCESS_note"]
           and len(set(procs)) >= 2,
           "3-pair perf A/B: pixels equal, draw_us -> 0, TIME_PROCESS retired")

    kb = jload(HERE / "key_bench.json")
    expect("V21", kb["n"] >= 10000 and kb["str_us"] > 1.0
           and kb["hash_us"] < 0.5 and kb["ratio"] > 10,
           "key cost measured: str %.4fus / hash %.4fus" % (kb["str_us"], kb["hash_us"]))

    rhythm_pngs = sorted(RHYTHM.glob("节奏帧-*.png"))
    rinfos = [png_info(p) for p in rhythm_pngs]
    cap_log = (HERE / "logs" / "capture_rhythm_1280.out").read_text(encoding="utf-8")
    diag = jload(HERE / "节奏回归诊断.json")
    expect("V22", len(rhythm_pngs) == 8
           and all(b > 100000 and w == 1280 and h == 720 for b, w, h in rinfos)
           and "RESULT: OK" in cap_log
           and cap_log.count("| OK ") >= 8
           and ("RESTORE OK sha256=%s" % cur["scripts/arena.gd"]["sha256"]) in cap_log
           and diag["verdict"] == "CRITERION_RETIRED",
           "8/8 injected rhythm shots + arena.gd byte-restored")

    if not SKIP_SHA:
        clean = all(sha((GAME / rel).read_bytes()) == rec["sha256"]
                    for rel, rec in cur.items())
        expect("V23", clean, "current source sha matches frozen snapshot")
    else:
        print("V23 SKIPPED (mutation mode)")

    doc = (HERE / "静止帧诊断.txt").read_text(encoding="utf-8")
    new_tests = ["tests/redraw_gate_check.gd", "tests/redraw_probe.gd",
                 "tests/redraw_perf_probe.gd", "tests/key_bench.gd"]
    expect("V24", len(doc) > 2000
           and "安全边界" in doc and "成本账" in doc
           and all((GAME / t).is_file() for t in new_tests),
           "diagnosis doc + 4 new probe scripts present")

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    lines = ["%s %-5s %s" % ("PASS" if ok else "FAIL", cid, detail)
             for cid, ok, detail in CHECKS]
    failed = [cid for cid, ok, _ in CHECKS if not ok]
    text = "\n".join(lines) + "\n\n%d/%d PASS\nRESULT: %s\n" % (
        passed, len(CHECKS), "REDRAW_VERIFIED" if not failed else "FAILED " + ",".join(failed))
    (HERE / "verify_redraw.log").write_text(text, encoding="utf-8")
    (HERE / "verify_redraw_result.json").write_text(
        json.dumps({"total": len(CHECKS), "passed": passed, "failed": failed,
                    "skip_sha": SKIP_SHA,
                    "checks": [{"id": c, "ok": o, "detail": d} for c, o, d in CHECKS]},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(text)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
