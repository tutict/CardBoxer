"""I 路线 P0 汇总：把三条独立证据合成一条可复算的根因结论。

1. 贴图：UV 岛（非黑区）亮度差 70.99，玩家亮、对手暗（texture_i.json）。
2. 材质：两份 GLB 在 Godot 里都是 StandardMaterial3D，metallic=1.0 /
   roughness=1.0 乘数 + 独立 metallicRoughnessTexture，只有贴图内容不同
   （material_i.json）。
3. 渲染：H 路线同进程 vp_diag 两帧里，角色主体亮度 95.02 vs 106.2，
   对手反而更亮 11.18 —— 贴图差异被渲染链吃掉甚至反转。

结论：造型撞车之外，「贴图暗却看不出暗」是渲染链问题（四盏固定方向
高强度灯 + 金属度乘数 1.0 让 albedo 不参与漫反射）。因此**不需要重做
3D 模型**，表现层（tint / metallic / 灯光 / 轮廓）就能把两人分开。

输出 data/rootcause_i.json。只读，不改任何资产或源码。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageStat

HERE = Path(__file__).resolve().parent
H = HERE.parent / "H路线-双方3D侧面战斗"
OUT = HERE / "data" / "rootcause_i.json"
# H 路线自动定位的两个角色 ROI（取中间主体区域，避开大部分背景）
SUBJECT = {"player": (380, 300, 468, 525),
           "foe": (812, 300, 902, 525)}
SHOTS = {"player": H / "shots" / "vp_diag" / "vp-foe-hidden.png",
         "foe": H / "shots" / "vp_diag" / "vp-player-hidden.png"}


def luma(path: Path, box) -> tuple[list[float], float]:
    im = Image.open(path).convert("RGB").crop(box)
    m = [round(v, 2) for v in ImageStat.Stat(im).mean]
    return m, round(sum(m) / 3.0, 2)


def main() -> int:
    tex = json.loads((HERE / "data" / "texture_i.json").read_text(
        encoding="utf-8"))
    mat = json.loads((HERE / "data" / "material_i.json").read_text(
        encoding="utf-8"))
    surfaces = mat["standard_surfaces"]
    lit_gap = tex["deltas"]["mean_lit_luma_player_minus_foe"]
    lit_ratio_gap = tex["deltas"]["lit_ratio_player_minus_foe"]

    subject = {}
    for k, p in SHOTS.items():
        rgb, lum = luma(p, SUBJECT[k])
        subject[k] = {"rgb": rgb, "luma": lum, "box": list(SUBJECT[k]),
                      "source": str(p)}
    render_gap = round(subject["player"]["luma"]
                       - subject["foe"]["luma"], 2)

    metal = {k: [s.get("metallic") for s in v]
             for k, v in surfaces.items()}
    rough = {k: [s.get("roughness") for s in v]
             for k, v in surfaces.items()}
    tex_paths = {k: [s.get("metallic_texture", "") for s in v]
                 for k, v in surfaces.items()}

    out = {
        "texture_lit_luma_gap": lit_gap,
        "texture_black_fill_ratio_gap": lit_ratio_gap,
        "hypothesis_falsified": tex["hypothesis_falsified"],
        "material_multipliers": {"metallic": metal, "roughness": rough},
        "metallic_textures": tex_paths,
        "render_subject": subject,
        "render_luma_gap_player_minus_foe": render_gap,
    }
    out["checks"] = {
        "texture_gap_is_real": lit_gap > 50.0,
        "black_fill_ruled_out": abs(lit_ratio_gap) < 0.10
                                and tex["hypothesis_falsified"] is True,
        "both_materials_standard_and_metallic": all(
            v == [1.0] for v in metal.values())
            and all(len(v) > 0 for v in surfaces.values()),
        "both_have_metallic_texture": all(
            all(bool(t) for t in v) for v in tex_paths.values()),
        "render_gap_flat_or_inverted": render_gap < 20.0,
    }
    out["root_cause"] = (
        "四盏固定方向高强度灯 + metallic 乘数 1.0 抑制 albedo 漫反射，"
        "把贴图 70.99 的亮度差吃成渲染 -11.18；属渲染链，不是贴图也不是拓扑"
        if all(out["checks"].values()) else
        "三条证据未同时成立，根因待查，不得据此动表现层")
    out["decision"] = (
        "表现层可修：tint + 降 metallic + 降灯能量 + 加宽轮廓；"
        "不重做 3D 模型（重做要重跑 Voxel/绑骨/GLB/rest 全链）"
        if all(out["checks"].values()) else "先补诊断，不动手")
    out["ok"] = all(out["checks"].values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("TEXTURE_LIT_GAP", lit_gap, "BLACK_FILL_GAP", lit_ratio_gap)
    print("METALLIC", metal, "ROUGHNESS", rough)
    print("RENDER_SUBJECT", {k: v["luma"] for k, v in subject.items()},
          "GAP", render_gap)
    print("ROOT_CAUSE", out["root_cause"])
    print("DECISION", out["decision"])
    for k, v in out["checks"].items():
        print("CHECK", k, v)
    print("ROOTCAUSE_I_OK" if out["ok"] else "ROOTCAUSE_I_INCONCLUSIVE")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
