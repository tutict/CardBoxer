"""I 路线 P3：把四帧同进程 A/B 量化成可复算的区分度指标。

base   = 无 3D 层（纯背景）
on     = foe 视觉启用
plain  = set_foe_visual(false)（H 原样）
again  = 再次启用（验证可反复切换）

角色掩膜用 sum(|frame - base|) > 18 造：这样亮度只统计角色像素，
不被擂台背景稀释（H 路线 ROI 均值的教训）。
输出 data/visual_diag_i.json；只读 PNG，不改源码或资产。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
H = HERE.parent / "route-h-two-sided-3d-combat"
SHOTS = HERE / "shots" / "visual_ab"
OUT = HERE / "data" / "visual_diag_i.json"
THR = 18

ROI = json.loads((H / "data" / "roi_h.json").read_text(
    encoding="utf-8"))["boxes"]
LEFT, RIGHT = ROI[0], ROI[1]
# H 的 ROI 只有 126/128 px 宽，角色加宽后会被裁断，宽度比恒为 1.0。
# 用更宽的窗口专门量轮廓宽度（仍以 base 帧作背景参考）。
WIDE_FOE = (730, 280, 985, 545)


def load(tag: str) -> Image.Image:
    return Image.open(SHOTS / f"vis-{tag}.png").convert("RGB")


def diff(a: Image.Image, b: Image.Image, box) -> dict:
    ia, ib = a.crop(box), b.crop(box)
    d = ImageChops.difference(ia, ib)
    changed = sum(1 for px in d.get_flattened_data() if sum(px) > THR)
    total = ia.width * ia.height
    return {"changed_px": changed, "total_px": total,
            "ratio": round(changed / total, 4),
            "mae": round(sum(ImageStat.Stat(d).mean) / 3.0, 4)}


def mask_stats(frame: Image.Image, base: Image.Image, box) -> dict:
    fa, ba = frame.crop(box), base.crop(box)
    d = ImageChops.difference(fa, ba)
    fp = list(fa.get_flattened_data())
    dp = list(d.get_flattened_data())
    w, h = fa.size
    hits = [i for i, px in enumerate(dp) if sum(px) > THR]
    if not hits:
        return {"mask_px": 0, "luma": 0.0, "rgb": [0, 0, 0],
                "width_px": 0, "red_minus_blue": 0.0}
    rgb = [round(sum(fp[i][c] for i in hits) / len(hits), 2)
           for c in range(3)]
    cols = [i % w for i in hits]
    return {
        "mask_px": len(hits),
        "rgb": rgb,
        "luma": round(sum(rgb) / 3.0, 2),
        "red_minus_blue": round(rgb[0] - rgb[2], 2),
        "width_px": max(cols) - min(cols) + 1,
        "mask_ratio": round(len(hits) / (w * h), 4),
    }


def main() -> int:
    imgs = {t: load(t) for t in
            ("base", "on", "on-repeat", "plain", "again")}
    out = {"threshold_sum_rgb": THR, "left_roi": LEFT, "right_roi": RIGHT}
    out["diffs"] = {
        # 零操作对照：同状态两帧。若这里的 changed_px > 0，
        # 后面 on_vs_plain 的玩家侧差异就不能全算到视觉开关头上。
        "player_roi_noop": diff(imgs["on"], imgs["on-repeat"], LEFT),
        "foe_roi_noop": diff(imgs["on"], imgs["on-repeat"], RIGHT),
        "player_roi_on_vs_plain": diff(imgs["on"], imgs["plain"], LEFT),
        "foe_roi_on_vs_plain": diff(imgs["on"], imgs["plain"], RIGHT),
        "player_roi_on_vs_base": diff(imgs["on"], imgs["base"], LEFT),
        "foe_roi_on_vs_again": diff(imgs["on"], imgs["again"], RIGHT),
        "full_frame_on_vs_plain": diff(
            imgs["on"], imgs["plain"], (0, 0, 1280, 720)),
    }
    out["masks"] = {
        "player_on": mask_stats(imgs["on"], imgs["base"], LEFT),
        "player_plain": mask_stats(imgs["plain"], imgs["base"], LEFT),
        "foe_on": mask_stats(imgs["on"], imgs["base"], RIGHT),
        "foe_plain": mask_stats(imgs["plain"], imgs["base"], RIGHT),
        "foe_on_wide": mask_stats(imgs["on"], imgs["base"], WIDE_FOE),
        "foe_plain_wide": mask_stats(imgs["plain"], imgs["base"],
                                     WIDE_FOE),
    }
    m = out["masks"]
    out["metrics"] = {
        "luma_gap_player_minus_foe_on": round(
            m["player_on"]["luma"] - m["foe_on"]["luma"], 2),
        "luma_gap_player_minus_foe_plain": round(
            m["player_plain"]["luma"] - m["foe_plain"]["luma"], 2),
        "foe_luma_drop_on_vs_plain": round(
            m["foe_plain"]["luma"] - m["foe_on"]["luma"], 2),
        "red_blue_shift_delta": round(
            (m["player_on"]["red_minus_blue"]
             - m["foe_on"]["red_minus_blue"])
            - (m["player_plain"]["red_minus_blue"]
               - m["foe_plain"]["red_minus_blue"]), 2),
        "foe_width_ratio_on_over_plain": round(
            m["foe_on"]["width_px"] / max(1, m["foe_plain"]["width_px"]), 4),
        "player_luma_change_on_vs_plain": round(
            m["player_on"]["luma"] - m["player_plain"]["luma"], 2),
        "foe_width_ratio_wide": round(
            m["foe_on_wide"]["width_px"]
            / max(1, m["foe_plain_wide"]["width_px"]), 4),
    }
    d = out["diffs"]
    q = out["metrics"]
    spec = json.loads((HERE / "data" / "visual_diff_spec.json").read_text(
        encoding="utf-8"))["targets"]
    checks = {
        "noop_frames_identical": (
            d["player_roi_noop"]["changed_px"] == 0
            and d["foe_roi_noop"]["changed_px"] == 0),
        "player_roi_pixel_identical": (
            d["player_roi_on_vs_plain"]["changed_px"]
            == spec["player_roi_changed_px"]),
        "player_luma_unchanged": abs(
            q["player_luma_change_on_vs_plain"]) < 0.01,
        "foe_roi_changed": d["foe_roi_on_vs_plain"]["ratio"] > 0.30,
        "luma_gap_above_target": (
            q["luma_gap_player_minus_foe_on"]
            >= spec["min_luma_gap_player_minus_foe"]),
        "foe_substantially_darker": q["foe_luma_drop_on_vs_plain"] > 50.0,
        "color_shift_visible": (
            abs(q["red_blue_shift_delta"])
            >= spec["min_abs_red_blue_shift"]),
        "repeat_switch_deterministic": (
            d["foe_roi_on_vs_again"]["changed_px"] == 0),
        "wide_roi_wider_than_plain": (
            q["foe_width_ratio_wide"]
            >= spec["min_subject_width_ratio"]),
    }
    out["checks"] = checks
    out["failed"] = [k for k, v in checks.items() if not v]
    out["ok"] = all(checks.values())
    out["wide_foe_roi"] = list(WIDE_FOE)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in out["diffs"].items():
        print("DIFF", k, v)
    for k, v in m.items():
        print("MASK", k, "luma", v["luma"], "w", v["width_px"],
              "px", v["mask_px"], "rb", v["red_minus_blue"])
    print("METRICS", out["metrics"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("VISUAL_DIAG_I_OK" if out["ok"] else "VISUAL_DIAG_I_FAILED")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
