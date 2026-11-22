"""G 路线承重判据：游戏内 3D 接线 + 侧面战斗表现层。

七层，任一 FAIL 即整体验证失败：
  A 源码形状   —— 双轨开关默认关、侧身定稿常量、站架偏置、表现层不改驱动链
  B 源码漂移   —— 基线 105 文件中只允 2 个（arena.gd / fighter.gd）被改，
                  其余逐 sha256 与改动前一致；新增文件按形状白名单
  C 资产       —— GLB / 3 张 PBR / motion_input.json / rig_driver.gd 与
                  F 路线原件逐字节同 sha
  D 判定零变化 —— 六模式 RHYTHM_SHOT marker 三组逐字相同
  E 表现       —— 默认关静态像素等价 / 同树 A/B / 节奏帧 / 侧身探针全绿
  F 全量自检   —— 15 套引擎内自检 before/after 全绿
  G 交付清单   —— 文件清单逐项 sha 自洽、覆盖全部交付文件、diff 非空

【判据口径】跨 Godot 进程的整帧逐像素等价不成立（全局 RNG 每次启动
随机化），已由 diag_ab.py 量化并退役；默认关零污染改由
run_static_ab_g.py 的「同冻结状态」口径证明。详见 compare_g.py docstring。

用法：python verify_g.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
F_ROUTE = BAKE / "route-f-godot-driver"
DATA = HERE / "data"
LOGS = HERE / "logs"
BOARDS = HERE / "boards"
OUT = LOGS / "verify_g.json"

# 改动前 105 个文件中，允许被 G 路线改的只有这两个（且必须有备份）。
ALLOWED_CHANGED = {"scripts/arena.gd", "scripts/fighter.gd"}
# 新增文件按形状分族，逐族给规则，不按名字死列。
ADDED_RULES = {
    "glb": lambda r: r == "assets/3d/player-rigged.glb",
    "glb_import": lambda r: r == "assets/3d/player-rigged.glb.import",
    "pbr": lambda r: (r.startswith("assets/3d/player-rigged_texture_pbr_")
                      and r.endswith(".png")),
    "pbr_import": lambda r: (r.startswith("assets/3d/player-rigged_texture_pbr_")
                             and r.endswith(".png.import")),
    "motion": lambda r: r == "data/motion_input.json",
    "layer": lambda r: r == "scripts/fighter_3d_layer.gd",
    "driver": lambda r: r in ("scripts/rig_driver.gd",
                              "scripts/rig_driver.gd.uid"),
    "probe": lambda r: (r.startswith("tests/")
                        and r.endswith(".gd")
                        and r in {
                            "tests/three_d_probe.gd",
                            "tests/side_view_probe.gd",
                            "tests/side_stance_probe.gd"}),
    # Godot 编辑器自动生成的 .uid，属导入副产物，规则限定在 tests/scripts 下。
    "uid": lambda r: (r.endswith(".gd.uid")
                      and (r.startswith("tests/") or r.startswith("scripts/"))),
}

EXPECTED_BIAS = {
    "upperarm_f": 26.0, "forearm_f": -50.0,
    "upperarm_b": -26.0, "forearm_b": 50.0,
    "spine": 4.0, "head": -2.4,
    "thigh_f": 10.0, "shin_f": -6.0,
    "thigh_b": -12.0, "shin_b": 7.0,
}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def js(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def game_files() -> dict:
    out = {}
    for p in GAME.rglob("*"):
        if not p.is_file() or ".godot" in p.parts:
            continue
        out[str(p.relative_to(GAME)).replace("\\", "/")] = sha256(p)
    return out


def main() -> int:
    checks, notes = {}, {}
    layer_path = GAME / "scripts" / "fighter_3d_layer.gd"
    arena_src = read(GAME / "scripts" / "arena.gd")
    fighter_src = read(GAME / "scripts" / "fighter.gd")
    layer_src = read(layer_path)

    # ── A 源码形状 ────────────────────────────────────────────
    checks["A01_switch_default_off"] = (
        'use_3d = OS.get_environment("CARD_BOXER_3D") != ""' in arena_src)
    checks["A02_override_default_false"] = (
        "var draw_3d_override := false" in fighter_src)
    checks["A03_layer_preload_present"] = (
        'preload("res://scripts/fighter_3d_layer.gd")' in arena_src)
    checks["A04_sync_hook_present"] = arena_src.count("_sync_3d_layer()") >= 2
    # 判据写赋值形态，不写裸常量：注释里也会提到 55.0。
    # [ \t\r]* 而非 \s*$：本仓工作树 CRLF/LF 混合，\s 会跨行吞掉下一行。
    yaw = re.search(r"^const DEFAULT_SIDE_YAW := ([0-9.]+)[ \t\r]*$",
                    layer_src, re.M)
    checks["A05_side_yaw_is_55"] = yaw is not None and float(yaw.group(1)) == 55.0
    notes["side_yaw"] = float(yaw.group(1)) if yaw else None
    flip = re.search(r"^const DEFAULT_SIDE_FLIP := (true|false)[ \t\r]*$",
                     layer_src, re.M)
    checks["A06_side_flip_false"] = flip is not None and flip.group(1) == "false"
    checks["A07_no_90deg_view"] = (
        "const DEFAULT_SIDE_YAW := 90.0" not in layer_src)
    # 站架偏置逐项解析，钉具体值 + 名单长度（防「删几项还算通过」）。
    block = re.search(r"const DEFAULT_STANCE_BIAS := \{(.*?)\n\}",
                      layer_src, re.S)
    bias = {}
    if block:
        for k, v in re.findall(r'"([a-z_]+)":\s*(-?[0-9.]+)', block.group(1)):
            bias[k] = float(v)
    checks["A08_stance_bias_exact"] = (bias == EXPECTED_BIAS
                                       and len(bias) == 10)
    notes["stance_bias"] = bias
    checks["A09_stance_bias_default_applied"] = (
        "var stance_bias_deg: Dictionary = DEFAULT_STANCE_BIAS.duplicate()"
        in layer_src)
    # 只在 apply() 函数体内判顺序：源码里还有 func _apply_stance_bias()
    # 的定义，全文件 index() 会命中定义行（更早），造成假红。
    apply_body = re.search(
        r"func apply\(card: String, frame: int\) -> void:(.*?)"
        r"(?=\nfunc |\Z)", layer_src, re.S)
    body = apply_body.group(1) if apply_body else ""
    checks["A10_bias_is_postprocess_only"] = (
        bool(apply_body)
        and "drv.apply_frame(c, f)" in body
        and "_apply_stance_bias()" in body
        and body.index("drv.apply_frame(c, f)")
        < body.index("_apply_stance_bias()"))
    checks["A11_bias_uses_bone_pose_rotation"] = (
        "drv.skel.set_bone_pose_rotation(i, cur * q)" in layer_src)
    checks["A12_camera_uses_yaw"] = (
        "CAM_RADIUS * sin(a)" in layer_src
        and "CAM_RADIUS * cos(a)" in layer_src
        and "cam.look_at(Vector3(0.0, CAM_TARGET_Y, 0.0), Vector3.UP)"
        in layer_src)
    # 表现层不得碰判定字段：源码里不出现 HP / 伤害 / 牌型写入。
    checks["A13_layer_no_gameplay_writes"] = not any(
        s in layer_src for s in ("hp -=", "hp =", "damage =",
                                 "tk_player_rage", "tk_enemy_rage"))

    # ── B 源码漂移 ────────────────────────────────────────────
    baseline = json.loads((HERE / "baseline_g.json").read_text(
        encoding="utf-8"))
    base = {x["rel"]: x["sha256"] for x in baseline["files"]}
    cur = game_files()
    changed = {k for k in base if k in cur and base[k] != cur[k]}
    missing = {k for k in base if k not in cur}
    added = {k for k in cur if k not in base}
    checks["B01_no_baseline_file_deleted"] = not missing
    checks["B02_only_allowed_changed"] = changed == ALLOWED_CHANGED
    checks["B03_added_all_whitelisted"] = all(
        any(rule(r) for rule in ADDED_RULES.values()) for r in added)
    # 按形状分族断言每族齐全，不写死总数（.uid 是编辑器副产物，会增减）。
    for fam, rule in ADDED_RULES.items():
        if fam in ("uid",):
            continue
        checks[f"B04_family_present_{fam}"] = any(rule(r) for r in added)
    checks["B05_no_unclassified_added"] = checks["B03_added_all_whitelisted"]
    notes["changed"] = sorted(changed)
    notes["missing"] = sorted(missing)
    notes["added_count"] = len(added)
    for f in ALLOWED_CHANGED:
        b = HERE / "orig" / "pre-3d" / f
        checks[f"B06_backup_exists_{f.replace('/', '_')}"] = b.is_file()
    # 侧身版 3D 层自身也要有改动前备份，便于一键回退。
    checks["B07_pre_side_backup"] = (
        (HERE / "orig/pre-side/fighter_3d_layer.gd").is_file())

    # ── C 资产 ───────────────────────────────────────────────
    inst = js("install_assets_g.json")
    copies = {x["rel"]: x["sha256"] for x in inst.get("copies", [])}
    for rel, expected in copies.items():
        p = GAME / rel
        checks[f"C01_copy_{rel.replace('/', '_')}"] = (
            p.is_file() and sha256(p) == expected)
    checks["C02_three_copies"] = len(copies) == 3
    checks["C03_glb_matches_F_route"] = (
        (GAME / "assets/3d/player-rigged.glb").is_file()
        and (F_ROUTE / "player-rigged.glb").is_file()
        and sha256(GAME / "assets/3d/player-rigged.glb")
        == sha256(F_ROUTE / "player-rigged.glb"))
    checks["C04_driver_matches_F_route"] = (
        sha256(GAME / "scripts/rig_driver.gd")
        == sha256(F_ROUTE / "probe_project_f/scenes/rig_driver.gd"))
    checks["C05_motion_matches_F_route"] = (
        sha256(GAME / "data/motion_input.json")
        == sha256(F_ROUTE / "data/motion_input.json"))
    checks["C06_glb_bytes"] = (
        (GAME / "assets/3d/player-rigged.glb").stat().st_size > 30_000_000)
    pbr = [r for r in added if ADDED_RULES["pbr"](r)]
    for r in pbr:
        im_path = GAME / r
        with Image.open(im_path) as im:
            checks[f"C07_pbr_4096_{r.split('/')[-1][:14]}"] = (
                im.size == (4096, 4096))
    checks["C08_three_pbr"] = len(pbr) == 3

    # ── D 判定零变化 ──────────────────────────────────────────
    ab = js("ab_g.json")
    per_mode = ab.get("per_mode", {})
    checks["D01_six_modes_present"] = len(per_mode) == 6
    checks["D02_all_markers_identical"] = all(
        v.get("marker_all_same") is True for v in per_mode.values())
    checks["D03_ab_ok"] = ab.get("ok") is True
    checks["D04_retired_claim_absent"] = all(
        not k.startswith("off_pixel_identical") for k in ab.get("checks", {}))
    checks["D05_all_groups_restored"] = all(
        js(f"capture_{g}.json").get("restore_ok") is True
        for g in ("baseline", "off", "on"))

    # ── E 表现证据 ────────────────────────────────────────────
    static = js("static_ab_g.json")
    checks["E01_static_pixel_identical"] = (
        static.get("changed_pixels") == 0 and static.get("ok") is True)
    same = js("same_tree_ab_g.json")
    checks["E02_same_tree_ok"] = same.get("ok") is True
    checks["E03_3d_visible_in_roi"] = bool(
        same.get("checks", {}).get("3d_visible_in_roi"))
    checks["E04_three_motions_distinct"] = all(
        same.get("checks", {}).get(k) for k in (
            "stance_vs_jab6_distinct", "jab6_vs_wave17_distinct",
            "stance_vs_wave17_distinct"))
    three = js("three_d_ab.json")
    checks["E05_three_d_ab_ok"] = three.get("ok") is True
    checks["E06_bones13_frames_positive"] = (
        three.get("payload", {}).get("bones") == 13
        and int(three.get("payload", {}).get("frames_applied", 0)) > 0)
    side = js("side_view_probe.json")
    checks["E07_side_view_probe_ok"] = (
        side.get("ok") is True and side.get("views") == 8)
    stance_p = js("side_stance_probe.json")
    checks["E08_stance_probe_ok"] = stance_p.get("ok") is True
    scan = js("side_stance_scan.json")
    checks["E09_stance_scan_ok"] = scan.get("ok") is True
    checks["E10_scan_six_cases"] = len(scan.get("cases", [])) == 6
    sub = js("subviewport_probe.json")
    checks["E11_subviewport_probe_ok"] = sub.get("ok") is True
    for name in ("G-same-scene-3d-dual-track-AB.png", "G-side-view-angle-eight-panel.png",
                 "G-side-view-four-level-stance-comparison.png", "G-side-view-reverse-stance-scan.png",
                 "G-dual-track-AB-comparison.png", "G-3D-motion-three-frames.png"):
        p = BOARDS / name
        checks[f"E12_board_{name}"] = p.is_file() and p.stat().st_size > 10000
    for group in ("off", "on"):
        pngs = sorted((HERE / "shots" / group).glob("*.png"))
        checks[f"E13_six_shots_{group}"] = len(pngs) == 6
        checks[f"E14_shots_nontrivial_{group}"] = all(
            x.stat().st_size > 200000 for x in pngs)

    # ── F 全量自检 ────────────────────────────────────────────
    for tag in ("before", "after"):
        d = js(f"all_checks_{tag}.json")
        checks[f"F01_all_green_{tag}"] = (
            d.get("total") == 15 and d.get("failed") == []
            and d.get("result") == "ALL GREEN"
            and len(d.get("checks", [])) == 15
            and all(x.get("ok") is True for x in d.get("checks", [])))
    txt = (LOGS / "run_checks_after.out").read_text(encoding="utf-8") \
        if (LOGS / "run_checks_after.out").is_file() else ""
    checks["F02_after_output_all_green"] = (
        "TOTAL 15 checks, 0 failed" in txt and "ALL_GREEN" in txt)

    # ── G 交付清单 ────────────────────────────────────────────
    fl = HERE / "file-list.txt"
    if fl.is_file():
        rows = [l for l in fl.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")]
        data_rows = [l for l in rows if "\t" in l]
        bad = 0
        listed = set()
        for l in data_rows:
            parts = l.split("\t")
            rel, size, sha = parts[0], parts[1], parts[2]
            listed.add(rel)
            p = HERE / rel
            if not p.is_file() or p.stat().st_size != int(size) \
                    or sha256(p) != sha:
                bad += 1
        checks["G01_filelist_nonempty"] = len(data_rows) > 20
        checks["G02_filelist_sha_selfconsistent"] = bad == 0
        notes["filelist_rows"] = len(data_rows)
        notes["filelist_bad"] = bad
        # 复用清单生成器的 entries()，不在这里另写一套排除规则：
        # 两套口径不一致会造出「两套互相打架的数字」，比一套坏数字更坏。
        from make_filelist_g import entries as _entries
        actual = {str(p.relative_to(HERE)).replace("\\", "/")
                  for p in _entries()}
        notes["filelist_missing"] = sorted(actual - listed)[:10]
        notes["filelist_extra"] = sorted(listed - actual)[:10]
        checks["G03_filelist_covers_all"] = not (actual - listed) \
            and not (listed - actual)
    else:
        for k in ("G01_filelist_nonempty", "G02_filelist_sha_selfconsistent",
                  "G03_filelist_covers_all"):
            checks[k] = False
    diff = HERE / "new-files.diff"
    checks["G04_diff_nonempty"] = diff.is_file() and diff.stat().st_size > 10000
    notes["diff_bytes"] = diff.stat().st_size if diff.is_file() else 0

    failed = [k for k, v in checks.items() if not v]
    ok = not failed
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "checks": checks, "failed": failed, "total": len(checks),
        "passed": len(checks) - len(failed), "notes": notes, "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k in failed:
        print("  FAIL", k)
    print(f"VERIFY_G {len(checks) - len(failed)}/{len(checks)} "
          f"failed={len(failed)}")
    print("G_VERIFIED" if ok else "G_VERIFY_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
