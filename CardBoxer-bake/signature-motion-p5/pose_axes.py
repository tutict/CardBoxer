# -*- coding: utf-8 -*-
"""P5 口径订正后的手臂轴指标（#215 起为落地判据的真相来源）。

为什么需要它（逐帧读盘实测，见 logs/diag_arm_axes.out）：
  · #213 的 reach = |f_hand - shoulder| 是欧氏距离，不区分前后，
    也不隔离肩部轨迹。cross 的 f_hand 全程恒为 (44,-156)，只有 shoulder
    在动，reach 的「峰值」其实是躯干后仰；wave 的手与肩同步平移，
    reach 几乎不变。两者都会被误判。
  · mf = |f_hand - stance.f_hand| 是 rig_driver.gd::retarget_delta
    **原样使用**的量（tf = min(1, mf / reach_norm_px)），
    既直接决定 3D 手臂驱动，也不会被 shoulder 污染。

本模块与 pose_metrics.py 的 13 指标并存：#213 的历史判据不改动，
新口径只用于 #215 之后的候选评估、落地与验收。
"""
from __future__ import annotations

import math


def forward_ext(frame: dict) -> float:
    """手相对肩的水平前伸（px）；仅作辅助报告，肩部轨迹会干扰它。"""
    return float(frame["f_hand"][0]) - float(frame["shoulder"][0])


def mf(frame: dict, stance: dict) -> float:
    """手相对站架手的位移（px）—— 与 rig_driver.gd 的 tf/tb 同口径。"""
    a = frame["f_hand"]
    b = stance["f_hand"]
    return math.hypot(float(a[0]) - float(b[0]),
                      float(a[1]) - float(b[1]))


def axis_metrics(track: list, stance: dict) -> dict:
    mfs = [mf(f, stance) for f in track]
    fws = [forward_ext(f) for f in track]
    ph = [str(f.get("phase", "react")) for f in track]
    peak = max(range(len(track)), key=lambda i: mfs[i])
    fw_peak = max(range(len(track)), key=lambda i: fws[i])
    st_fw = forward_ext(stance)
    return {
        "mf_peak_px": round(mfs[peak], 4),
        "mf_peak_frame": peak,
        "mf_peak_phase": ph[peak],
        "mf_at_active_max_px": round(
            max((mfs[i] for i, p in enumerate(ph) if p == "active"),
                default=0.0), 4),
        "forward_ext_peak_px": round(fws[fw_peak], 4),
        "forward_ext_gain_px": round(fws[fw_peak] - st_fw, 4),
        "forward_ext_peak_frame": fw_peak,
        "forward_ext_peak_phase": ph[fw_peak],
    }
