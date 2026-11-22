"""引擎内实渲的逐像素 A/B：证明贴图真画出来、且没污染其它区域。

A=接线前基线 / B=接线后关板 / C=档案页1 / D=档案页2 / E=回退关板 / F=展示图。
A~E 同进程同注入态（paused=true），F 不参与判据。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
TOL = 6

# 允许 A→B 发生变化的四块区域；框比实际绘制略大，包容 draw_arc 抗锯齿。
ALLOWED = {
    "avatar_player": (0, 0, 46, 46),
    "avatar_foe": (1232, 0, 1280, 46),
    "card_1": (238, 552, 386, 702),
    "card_5": (894, 552, 1042, 702),
}
PROFILE_BOX = (56, 44, 1224, 676)
FILES = {
    "A": "A_baseline-without-portraits.png", "B": "B_integration-panel-closed.png",
    "C": "C_profile-page-1.png", "D": "D_profile-page-2.png",
    "E": "E_rollback-panel-closed.png", "F": "F_live-unpaused.png",
}


def diff_mask(a: Image.Image, b: Image.Image) -> Image.Image:
    """返回 0/255 的 L 图，255 = 任一通道差异超过 TOL。"""
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    return d.point(lambda p: 255 if p > TOL else 0)


def count(mask: Image.Image, box: tuple[int, int, int, int] | None = None) -> int:
    m = mask.crop(box) if box else mask
    return m.histogram()[255]


def area(box: tuple[int, int, int, int]) -> int:
    return (box[2] - box[0]) * (box[3] - box[1])


def outside_count(mask: Image.Image, boxes: list[tuple[int, int, int, int]]) -> int:
    """把允许区域涂黑后，数剩下的变化像素。"""
    m = mask.copy()
    for box in boxes:
        m.paste(0, box)
    return m.histogram()[255]


def main() -> None:
    imgs = {k: Image.open(SHOTS / v).convert("RGB") for k, v in FILES.items()}
    sizes = {k: list(v.size) for k, v in imgs.items()}
    if any(s != [1280, 720] for s in sizes.values()):
        raise RuntimeError(f"shot size mismatch: {sizes}")

    m_ab = diff_mask(imgs["A"], imgs["B"])
    per_region = {name: count(m_ab, box) for name, box in ALLOWED.items()}
    outside = outside_count(m_ab, list(ALLOWED.values()))

    m_be = diff_mask(imgs["B"], imgs["E"])
    m_bc = diff_mask(imgs["B"], imgs["C"])
    m_bd = diff_mask(imgs["B"], imgs["D"])
    m_cd = diff_mask(imgs["C"], imgs["D"])

    # 阈值按区域面积比例给，避免把实测数字写死成债。
    checks = {
        "sizes_1280x720": all(s == [1280, 720] for s in sizes.values()),
        "outside_allowed_zero": outside == 0,
        "card_1_visible": per_region["card_1"] > 0.05 * area(ALLOWED["card_1"]),
        "card_5_visible": per_region["card_5"] > 0.05 * area(ALLOWED["card_5"]),
        "avatar_player_visible": per_region["avatar_player"] > 0.05 * area(ALLOWED["avatar_player"]),
        "avatar_foe_visible": per_region["avatar_foe"] > 0.05 * area(ALLOWED["avatar_foe"]),
        "two_avatars_distinct": per_region["avatar_player"] > 0 and per_region["avatar_foe"] > 0,
        "back_is_identical": count(m_be) == 0,
        "profile_page1_visible": count(m_bc, PROFILE_BOX) > 0.20 * area(PROFILE_BOX),
        "profile_page2_visible": count(m_bd, PROFILE_BOX) > 0.20 * area(PROFILE_BOX),
        "profile_pages_differ": count(m_cd, PROFILE_BOX) > 0.05 * area(PROFILE_BOX),
        "clean_shot_not_blank": imgs["F"].getbbox() is not None,
    }
    metrics = {
        "tol": TOL,
        "allowed_regions": ALLOWED,
        "changed_px_per_region": per_region,
        "changed_px_outside_allowed": outside,
        "changed_px_B_vs_E": count(m_be),
        "changed_px_B_vs_C_profile": count(m_bc, PROFILE_BOX),
        "changed_px_B_vs_D_profile": count(m_bd, PROFILE_BOX),
        "changed_px_C_vs_D_profile": count(m_cd, PROFILE_BOX),
        "profile_box": PROFILE_BOX,
        "profile_area": area(PROFILE_BOX),
    }
    result = {"checks": checks, "metrics": metrics, "shots": FILES,
              "all_pass": all(checks.values())}
    (HERE / "verify_shots.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    for k, v in checks.items():
        print(f"  {'OK' if v else 'FAIL'} {k}")
    print("SHOTS_VERIFIED" if result["all_pass"] else "SHOTS_FAILED")


if __name__ == "__main__":
    main()
