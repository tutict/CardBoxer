"""I 路线 P0 根因诊断：贴图均值差 3.3 倍，为什么渲染只差 9.27 亮度？

原假设：4096² basecolor 里 UV 岛之外有大片黑填充，整图均值被黑区拉低。
实测证伪：非黑区（UV 岛）亮度差 70.99，与整图 70.66 同量级，
黑填充占比只差 3.1%。所以「贴图暗」是真的，抹平发生在渲染链，
不在贴图。这个负结果保留在 data/texture_i.json，不放宽阈值粉饰。

用 256×256 LANCZOS 抽样（4096² 全逐像素太慢，抽样足够判分布），
分别算：全图均值、非近黑像素占比、只看非近黑区域的均值、红蓝偏色。
输出 data/texture_i.json。只读，不改资产。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
OUT = HERE / "data" / "texture_i.json"
TEX = {
    "player": GAME / "assets/3d" /
              "player-rigged_texture_pbr_20250901.png",
    "foe": GAME / "assets/3d" /
           "foe-rigged_texture_pbr_20250901.png",
}
NEAR_BLACK = 30   # sum(R,G,B) < 30 视为 UV 岛外的黑填充


def analyse(path: Path) -> dict:
    im = Image.open(path).convert("RGB")
    orig_size = list(im.size)
    px = list(im.resize((256, 256), Image.LANCZOS).getdata())
    n = len(px)
    mean_all = [round(sum(p[i] for p in px) / n, 2) for i in range(3)]
    lit = [p for p in px if sum(p) >= NEAR_BLACK]
    dark = n - len(lit)
    mean_lit = ([round(sum(p[i] for p in lit) / len(lit), 2)
                 for i in range(3)] if lit else [0.0, 0.0, 0.0])
    return {
        "file": path.name, "orig_size": orig_size, "bytes": path.stat().st_size,
        "sample": [256, 256],
        "mean_all_rgb": mean_all,
        "mean_all_luma": round(sum(mean_all) / 3.0, 2),
        "near_black_px": dark, "lit_px": len(lit),
        "lit_ratio": round(len(lit) / n, 4),
        "mean_lit_rgb": mean_lit,
        "mean_lit_luma": round(sum(mean_lit) / 3.0, 2),
        "red_minus_blue": round(mean_all[0] - mean_all[2], 2),
    }


def main() -> int:
    rows = {k: analyse(v) for k, v in TEX.items()}
    out = {"near_black_threshold_sum_rgb": NEAR_BLACK, "textures": rows}
    out["deltas"] = {
        "mean_all_luma_player_minus_foe": round(
            rows["player"]["mean_all_luma"]
            - rows["foe"]["mean_all_luma"], 2),
        "mean_lit_luma_player_minus_foe": round(
            rows["player"]["mean_lit_luma"]
            - rows["foe"]["mean_lit_luma"], 2),
        "lit_ratio_player_minus_foe": round(
            rows["player"]["lit_ratio"] - rows["foe"]["lit_ratio"], 4),
    }
    # 原假设（黑填充拉低整图均值）已被实测证伪：UV 岛亮度差 70.99
    # 与整图 70.66 同量级，黑填充仅差 3.1%。这里把「证伪」本身当结果，
    # 不放宽阈值假装假设成立；根因转查材质/光照，见 rootcause_i.json。
    d = out["deltas"]
    checks = {
        "full_image_luma_gap_is_large": (
            d["mean_all_luma_player_minus_foe"] > 50.0),
        "uv_island_gap_same_order": (
            abs(d["mean_lit_luma_player_minus_foe"])
            > abs(d["mean_all_luma_player_minus_foe"]) * 0.9),
        "black_fill_not_the_cause": (
            abs(d["lit_ratio_player_minus_foe"]) < 0.10),
        "both_are_4096": all(
            r["orig_size"] == [4096, 4096] for r in rows.values()),
    }
    falsified = (checks["uv_island_gap_same_order"]
                 and checks["black_fill_not_the_cause"])
    out["hypothesis_falsified"] = falsified
    out["checks"] = checks
    out["root_cause"] = (
        "贴图确实整体暗（UV 岛亮度差 70.99），黑填充只差 3.1%；"
        "渲染亮度差被抹平的原因不在贴图，转查材质/光照"
        if falsified else
        "UV 岛外的黑填充主导整图均值差，需按非黑区重新评估")
    out["ok"] = all(checks.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, r in rows.items():
        print(k, "mean_all", r["mean_all_rgb"], "lit_ratio", r["lit_ratio"],
              "mean_lit", r["mean_lit_rgb"])
    print("DELTAS", d)
    print("ROOT_CAUSE", out["root_cause"])
    for k, v in out["checks"].items():
        print("CHECK", k, v)
    print("TEXTURE_I_OK" if out["ok"] else "TEXTURE_I_INCONCLUSIVE")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
