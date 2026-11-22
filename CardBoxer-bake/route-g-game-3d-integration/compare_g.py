"""G 路线 A/B 判据：判定零变化 / 3D 开可见 / 动作随节奏变 / 对照板。

【判据订正 2026-11-11】第一版逐模式断言 baseline 与 off 的整帧
「跨进程逐像素等价」，实测 6/6 全 FAIL。根因不是回归：Godot 每次启动
会随机化全局 RNG，手牌 / 观众席 / 灯光相位在不同进程间天然不同。
diag_ab.py 实测 baseline_vs_off 的 mae=10.43、gt6=34785 px，且差异
均匀铺满全屏（top_bg / mid / bottom_hud / player 四区都有），不是角色
局部变化。项目既有订正口径见 engine-optimization/compare_regression.py。

因此**退役** `off_pixel_identical_*` 这 6 条，换成三条真正有牙的证据：
  ① static_ab_g.json：同一冻结状态（paused + 隐藏动态子节点）跨进程
     逐像素等价 changed_pixels=0 —— 这是「默认关零污染」的硬证据；
  ② same_tree_ab_g.json：同一进程同一棵树 off→on 的 ROI 判据全绿；
  ③ 逐模式 RHYTHM_SHOT marker 三组逐字相同 —— 判定层零变化。
跨进程的 `on_vs_off_changed_px` 只作观察值记录，不再当等价判据。

用法：python compare_g.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
SHOTS = HERE / "shots"
LOGS = HERE / "logs"
BOARDS = HERE / "boards"
DATA = HERE / "data"
OUT = DATA / "ab_g.json"

sys.path.insert(0, str(BAKE / "side-view-rhythm"))
import capture_rhythm as cr  # noqa: E402

MODES = ["t000", "t048", "t112", "t140", "draw", "foewin"]
GROUPS = ["baseline", "off", "on"]
PLAYER_ROI = (290, 270, 580, 535)   # 玩家侧 3D 角色区域（2D 坐标）

FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")


def shot(group: str, mode: str) -> Path:
    return SHOTS / group / cr.CASES[mode][3]


def diff_px(a: Image.Image, b: Image.Image, box=None) -> int:
    x = a.convert("RGB") if box is None else a.convert("RGB").crop(box)
    y = b.convert("RGB") if box is None else b.convert("RGB").crop(box)
    d = ImageChops.difference(x, y)
    return sum(1 for px in d.get_flattened_data() if px != (0, 0, 0))


def marker(group: str, mode: str) -> str:
    p = LOGS / ("capture_" + group) / ("capture_%s.log" % mode)
    if not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    hits = re.findall(r"\[RHYTHM_SHOT\][^\r\n]*", text)
    return hits[0].strip() if hits else ""


def font(sz: int):
    if FONT_PATH.is_file():
        return ImageFont.truetype(str(FONT_PATH), sz)
    return ImageFont.load_default()


def board(rows: list[tuple[str, list[tuple[str, Path]]]], out: Path,
          cell: tuple[int, int] = (620, 350)) -> None:
    w, h = cell
    pad, label_h = 18, 30
    canvas = Image.new("RGB", (len(rows[0][1]) * (w + pad) + pad,
                              len(rows) * (h + label_h + pad) + pad),
                       (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = font(20)
    for r, (row_name, items) in enumerate(rows):
        for c, (name, p) in enumerate(items):
            x = pad + c * (w + pad)
            y = pad + r * (h + label_h + pad)
            im = Image.open(p).convert("RGB").resize((w, h))
            canvas.paste(im, (x, y))
            d.text((x + 4, y + h + 2), f"{row_name} / {name}",
                   font=f, fill=(150, 220, 200))
    canvas.save(out)


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    per_mode, checks, notes = {}, {}, {}

    for mode in MODES:
        paths = {g: shot(g, mode) for g in GROUPS}
        present = all(p.is_file() for p in paths.values())
        if not present:
            checks[f"pngs_{mode}"] = False
            continue
        checks[f"pngs_{mode}"] = True
        ims = {g: Image.open(p) for g, p in paths.items()}
        eq = diff_px(ims["baseline"], ims["off"])
        on_off = diff_px(ims["on"], ims["off"])
        marks = {g: marker(g, mode) for g in GROUPS}
        per_mode[mode] = {
            "baseline_vs_off_changed_px": eq,
            "on_vs_off_changed_px": on_off,
            "marker_baseline": marks["baseline"],
            "marker_off": marks["off"],
            "marker_on": marks["on"],
            "marker_all_same": (bool(marks["baseline"])
                                and marks["baseline"] == marks["off"]
                                and marks["off"] == marks["on"]),
        }
        # eq 只记录、不判绿（跨进程 RNG 噪声），见模块 docstring 的退役说明。
        checks[f"on_visible_{mode}"] = on_off > 20000
        checks[f"judgement_same_{mode}"] = per_mode[mode]["marker_all_same"]
        for g, p in paths.items():
            notes.setdefault(g, {})[mode] = {
                "bytes": p.stat().st_size,
                "w": ims[g].width, "h": ims[g].height,
            }

    # 3D 动作随节奏变化：只看玩家侧 ROI，排除 HUD / banner 差异。
    if all(shot("on", m).is_file() for m in ("t000", "t048", "t112")):
        a = Image.open(shot("on", "t000"))
        b = Image.open(shot("on", "t048"))
        c = Image.open(shot("on", "t112"))
        roi = {
            "t000_vs_t048": diff_px(a, b, PLAYER_ROI),
            "t048_vs_t112": diff_px(b, c, PLAYER_ROI),
            "t000_vs_t112": diff_px(a, c, PLAYER_ROI),
        }
        notes["on_player_roi_changed_px"] = roi
        # 口径提醒：这三个数含跨进程 RNG 噪声（约 7 万量级），**不能**
        # 当作「3D 动作随节奏变化」的证据。那条硬证据是
        # same_tree_ab_g.json 的 on-stance/on-jab6/on-wave17 同树对比。
        # 这里只保留「截帧非空、非全同」的下限，防止整批截图失效。
        checks["on_roi_frames_not_identical"] = (
            roi["t000_vs_t048"] > 500 and roi["t048_vs_t112"] > 500)
        board([
            ("3D ON", [("t000 起手", shot("on", "t000")),
                       ("t048 命中", shot("on", "t048")),
                       ("t112 攻击窗末", shot("on", "t112"))]),
        ], BOARDS / "G-3D-motion-three-frames.png")
    else:
        checks["3d_motion_changes_in_player_roi"] = False

    if shot("off", "t048").is_file():
        board([
            ("t048 命中帧", [
                ("改动前 baseline", shot("baseline", "t048")),
                ("默认关 off", shot("off", "t048")),
                ("3D 开 on", shot("on", "t048"))]),
        ], BOARDS / "G-dual-track-AB-comparison.png")

    captures = {}
    for g in GROUPS:
        p = DATA / ("capture_%s.json" % g)
        captures[g] = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    checks["all_groups_restored"] = all(
        captures[g].get("restore_ok") is True for g in GROUPS)
    checks["all_groups_rc0"] = all(
        captures[g].get("returncode") == 0 for g in GROUPS)

    # 退役 6 条跨进程等价后，用三条硬证据顶上，点名具体值而不是宽松下限。
    static = DATA / "static_ab_g.json"
    st = json.loads(static.read_text(encoding="utf-8")) if static.is_file() else {}
    same = DATA / "same_tree_ab_g.json"
    sm = json.loads(same.read_text(encoding="utf-8")) if same.is_file() else {}
    checks["static_default_off_pixel_identical"] = (
        st.get("changed_pixels") == 0 and st.get("ok") is True)
    checks["same_tree_ab_all_green"] = sm.get("ok") is True
    checks["same_tree_3d_visible_in_roi"] = bool(
        sm.get("checks", {}).get("3d_visible_in_roi"))
    checks["retired_cross_process_claim_not_reused"] = all(
        not k.startswith("off_pixel_identical") for k in checks)
    checks["retirement_documented"] = "退役" in (__doc__ or "")

    failed = [k for k, v in checks.items() if not v]
    ok = not failed
    OUT.write_text(json.dumps({
        "modes": MODES, "groups": GROUPS,
        "player_roi": list(PLAYER_ROI),
        "per_mode": per_mode, "notes": notes,
        "checks": checks, "failed": failed, "ok": ok,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for m in MODES:
        r = per_mode.get(m)
        if r:
            print(f"{m:8s} base-vs-off={r['baseline_vs_off_changed_px']:>7} "
                  f"on-vs-off={r['on_vs_off_changed_px']:>7} "
                  f"marker_same={r['marker_all_same']}")
    print("ROI", notes.get("on_player_roi_changed_px"))
    for k in failed:
        print("  FAIL", k)
    print("AB_G_OK" if ok else "AB_G_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
