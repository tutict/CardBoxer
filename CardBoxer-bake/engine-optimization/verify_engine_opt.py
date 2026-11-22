"""引擎优化（裁死绘制 + 放大窗口）承重判据，20 条。

四层证据：
  1) 变更范围：备份 30 文件、只有 2 个既有文件变更、上轮归档未污染
  2) 零视觉变化：贴图无 alpha、覆盖矩形含视口、同状态 PNG 独立重算 changed=0
  3) 判定/接线零改动：伤害与阶段行、P0 与节奏层形态、引擎 13 套自检
  4) 真实收益与窗口：引擎帧统计 A/B、1600x900 大窗口帧、RNG 根因日志

只钉可复算事实，不评好看；看图结论单写在验证记录里。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
BACKUP = BAKE / "orig" / "pre-engine-opt"
PREV = BAKE / "side-view-rhythm"
PREV_LIST = PREV / "side-view-rhythm-file-list.txt"
RESULT = HERE / "verify_engine_opt_result.json"
FINGERPRINT = HERE / "source-fingerprints.json"

checks: list[dict] = []


def check(name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print("[%s] %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def real_lines(src: str, form: str) -> list[str]:
    """只认真实代码行：注释行、以及 form 前已被 # 注释掉的一律不算。"""
    return [ln for ln in src.splitlines()
            if form in ln and not ln.lstrip().startswith("#")
            and "#" not in ln[:ln.index(form)]]


def verdict_lines(src: str) -> list[str]:
    keys = ("apply_hit(", "Rules.damage_of(", "tk_phase_time >=",
            "TK_MAX_TURNS :=", "tk_damage = 3")
    return [ln.strip() for ln in src.splitlines() if any(k in ln for k in keys)]


def main() -> int:
    baseline = jload(HERE / "backup-fingerprints.json")
    png_fp = jload(HERE / "background-fingerprints.json")
    ab = jload(HERE / "ab_result.json")
    reg = jload(HERE / "regression_result.json")
    all_checks = jload(HERE / "all_checks.json")
    win = jload(HERE / "window_probe_result.json")
    win_probe = jload(HERE / "window_probe.json")
    before = jload(HERE / "baseline" / "perf.json")
    after = jload(HERE / "after" / "perf.json")

    arena_src = (GAME / "scripts" / "arena.gd").read_text(encoding="utf-8")
    backup_arena = (BACKUP / "scripts__arena.gd").read_text(encoding="utf-8")
    proj = (GAME / "project.godot").read_text(encoding="utf-8")
    backup_proj = (BACKUP / "project.godot").read_text(encoding="utf-8")

    # ── 1. 变更范围 ──────────────────────────────────────────
    hashes_ok = all(
        (BACKUP / baseline[rel]["backup_file"]).is_file()
        and sha((BACKUP / baseline[rel]["backup_file"]).read_bytes())
        == baseline[rel]["sha256"] for rel in baseline)
    check("V01_backup_manifest_intact",
          len(baseline) == 30 and hashes_ok,
          "files=%d hashes_match=%s" % (len(baseline), hashes_ok))

    changed = set()
    for rel, meta in baseline.items():
        p = GAME / rel
        if not p.is_file() or sha(p.read_bytes()) != meta["sha256"]:
            changed.add(rel)
    check("V02_only_two_existing_files_changed",
          changed == {"scripts/arena.gd", "project.godot"},
          "changed=%s" % sorted(changed))

    probes = ["tests/perf_probe.gd", "tests/window_probe.gd",
              "tests/engine_opt_check.gd", "tests/rng_probe.gd"]
    check("V03_four_probe_scripts_present",
          all((GAME / r).is_file() and (GAME / r).stat().st_size > 500
              for r in probes),
          "sizes=%s" % [(GAME / r).stat().st_size for r in probes])

    png = GAME / "background" / "arena.png"
    im = Image.open(png)
    check("V04_backdrop_is_opaque_and_unmodified",
          "A" not in im.getbands() and im.mode == "RGB"
          and sha(png.read_bytes()) == png_fp["sha256"],
          "mode=%s bands=%s sha_match=%s" % (
              im.mode, im.getbands(), sha(png.read_bytes()) == png_fp["sha256"]))

    m = re.search(r"draw_texture_rect\(BackdropTexture, Rect2\("
                  r"([-\d.]+), ([-\d.]+), ([-\d.]+), ([-\d.]+)\)", arena_src)
    cover = False
    if m:
        x, y, w, h = (float(v) for v in m.groups())
        cover = x <= 0 and y <= 0 and x + w >= 1280 and y + h >= 720
    check("V05_texture_rect_covers_whole_viewport",
          bool(m) and cover,
          "rect=%s covers=%s" % (m.groups() if m else None, cover))

    # ── 2. 死绘制退役 / 动态层保留 ───────────────────────────
    dead = ["func _build_backdrop()", "_build_backdrop()", "_background_cache",
            "var bands := [", "lamp_color", "rng.randf_range",
            "sin(_time * 1.7", "for rect: Rect2 in", '"lamps"']
    dead_left = [d for d in dead if real_lines(arena_src, d)]
    check("V06_dead_draw_forms_retired",
          not dead_left, "left=%s" % dead_left)
    check("V07_texture_and_overlay_kept_exactly_once",
          len(real_lines(arena_src, "draw_texture_rect(BackdropTexture,")) == 1
          and len(real_lines(arena_src, "Color(0.055, 0.045, 0.085, 0.20)")) == 1,
          "texture=%d overlay=%d" % (
              len(real_lines(arena_src, "draw_texture_rect(BackdropTexture,")),
              len(real_lines(arena_src, "Color(0.055, 0.045, 0.085, 0.20)"))))

    i = arena_src.find("func _draw_backdrop() -> void:")
    j = arena_src.find("func _draw_light_cone(")
    body = arena_src[i:j] if i >= 0 and j > i else ""
    check("V08_dynamic_backdrop_layers_kept",
          body != "" and body.count("for i in range(9)") == 1
          and body.count("range(13)") == 1
          and len(real_lines(arena_src, "_draw_light_cone(")) >= 3
          and len(real_lines(arena_src, "_draw_floor_glow(")) >= 3,
          "body=%dB lines9=%d lines13=%d" % (
              len(body), body.count("for i in range(9)"), body.count("range(13)")))

    # ── 3. 判定 / 接线零改动 ─────────────────────────────────
    vb, va = verdict_lines(backup_arena), verdict_lines(arena_src)
    check("V09_damage_and_phase_lines_untouched",
          vb == va and len(va) >= 8,
          "lines=%d identical=%s" % (len(va), vb == va))
    keep = ["MotionP0.binding_for(winner_type)", "MotionP0.REVEAL_CARD",
            "_draw_rhythm_fx(canvas)", "func _apply_rhythm_visuals() -> void:",
            "tk_damage = Rules.damage_of(tk_player_result)"]
    counts_ok = all(arena_src.count(s) == backup_arena.count(s) > 0
                    for s in keep)
    check("V10_p0_and_rhythm_wiring_not_regressed", counts_ok,
          json.dumps({s: arena_src.count(s) for s in keep}, ensure_ascii=False))

    # ── 4. 零视觉变化（从 PNG 独立重算）──────────────────────
    p1 = HERE / "baseline" / "background-baseline.png"
    p2 = HERE / "after" / "background-baseline.png"
    a, b = Image.open(p1).convert("RGB"), Image.open(p2).convert("RGB")
    recalc = sum(ImageChops.difference(a, b).convert("L").histogram()[1:])
    check("V11_static_backdrop_pixels_recomputed_identical",
          a.size == b.size == (1280, 720) and recalc == 0
          and recalc == ab["changed_pixels"] and ab["pixel_identical"]
          and p1.read_bytes() == p2.read_bytes(),
          "recalc=%d json=%d bytes_equal=%s" % (
              recalc, ab["changed_pixels"], p1.read_bytes() == p2.read_bytes()))

    drops = {k: ab["deltas"][k]["delta"] for k in
             ("primitives", "draw_calls", "process_ms")}
    check("V12_engine_frame_stats_all_dropped_and_comparable",
          all(v < 0 for v in drops.values())
          and before["samples"] == after["samples"] == 120
          and before["viewport"] == after["viewport"] == [1280, 720]
          and len(set(before["raw_primitives"])) == 1
          and len(set(after["raw_primitives"])) == 1
          and after["primitives"]["mean"] == ab["deltas"]["primitives"]["after"],
          "deltas=%s" % drops)

    rec = next((r for r in all_checks["checks"]
                if r["check"] == "tests/engine_opt_check.gd"), {})
    check("V13_thirteen_engine_checks_green",
          all_checks["result"] == "ALL GREEN" and all_checks["total"] == 13
          and len(all_checks["checks"]) == 13 and all(r["ok"] for r in all_checks["checks"])
          and "37/37 passed" in rec.get("summary", ""),
          "result=%s opt_check=%s" % (all_checks["result"], rec.get("summary")))

    # ── 5. 窗口放大与证据链 ──────────────────────────────────
    check("V14_window_enlarged_1_25_without_layout_change",
          win["result"] == "WINDOW_ENLARGED_OK"
          and all(win["checks"].values())
          and win_probe["physical"] == [1600, 900]
          and win_probe["logical"] == [1280, 720]
          and abs(win_probe["scale_x"] - 1.25) < 1e-9
          and abs(win_probe["scale_y"] - 1.25) < 1e-9
          and win_probe["stretch_mode"] == "canvas_items",
          "physical=%s logical=%s scale=%s" % (
              win_probe["physical"], win_probe["logical"], win_probe["scale_x"]))

    big = HERE / "large-window-captures" / "rhythm-frame-t048-impact-HIT.png"
    big_im = Image.open(big) if big.is_file() else None
    check("V15_large_window_full_game_frame_rendered",
          big_im is not None and big_im.size == (1600, 900)
          and big.stat().st_size > 100_000,
          "size=%s bytes=%s" % (big_im.size if big_im else None,
                                big.stat().st_size if big.is_file() else 0))

    rng_lines = (HERE / "logs" / "rng_probe.log").read_text(
        encoding="utf-8").strip().splitlines()
    useeds = [re.search(r"unseeded=([\d.]+)", ln).group(1)
              for ln in rng_lines if re.search(r"unseeded=([\d.]+)", ln)]
    check("V16_rng_root_cause_logged",
          len(rng_lines) == 3 and len(set(useeds)) == 3
          and all("new_consumes_global=false" in ln for ln in rng_lines),
          "runs=%d distinct_unseeded=%d" % (len(rng_lines), len(set(useeds))))

    check("V17_regression_evidence_and_restore_ok",
          reg["result"] == "REGRESSION_EVIDENCE_OK" and reg["frames_ok"]
          and reg["engine_ok"] and reg["restore_ok"]
          and reg["static_ab_pixel_identical"] and len(reg["rows"]) == 8,
          "rows=%d result=%s" % (len(reg["rows"]), reg["result"]))

    prev_rows = []
    for ln in PREV_LIST.read_text(encoding="utf-8").splitlines()[5:]:
        mm = re.match(r"^(.+?)\s+(\d+)\s+([0-9a-f]{64})$", ln.strip())
        if mm:
            prev_rows.append(mm.groups())
    prev_ok = len(prev_rows) == 60 and all(
        (PREV / rel).is_file() and sha((PREV / rel).read_bytes()) == h
        and (PREV / rel).stat().st_size == int(n)
        for rel, n, h in prev_rows)
    check("V18_previous_archive_untouched",
          prev_ok, "entries=%d all_match=%s" % (len(prev_rows), prev_ok))

    added_only = all(ln in proj.splitlines() for ln in backup_proj.splitlines()
                     if ln.strip() and not ln.strip().startswith(";"))
    check("V19_project_godot_only_added_window_override",
          added_only and "window/size/window_width_override=1600" in proj
          and "window/size/window_height_override=900" in proj,
          "original_lines_kept=%s overrides_present=%s" % (
              added_only, "window_width_override=1600" in proj))

    fps = {}
    for rel in ["scripts/arena.gd", "scripts/fighter.gd", "scripts/hud.gd",
                "scripts/battle_rhythm.gd", "scripts/battle_motion_p0.gd",
                "tests/engine_opt_check.gd", "tests/perf_probe.gd",
                "tests/window_probe.gd", "tests/rng_probe.gd", "project.godot"]:
        p = GAME / rel
        if p.is_file():
            fps[rel] = {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
    FINGERPRINT.write_text(json.dumps(fps, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    check("V20_source_fingerprints_written", len(fps) == 10,
          "files=%d" % len(fps))

    passed = sum(1 for c in checks if c["ok"])
    RESULT.write_text(json.dumps({
        "checks": checks, "passed": passed, "total": len(checks),
        "result": "ENGINE_OPT_VERIFIED" if passed == len(checks)
        else "ENGINE_OPT_FAILED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT: %d/%d %s" % (passed, len(checks),
                                "ENGINE_OPT_VERIFIED" if passed == len(checks)
                                else "ENGINE_OPT_FAILED"))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
