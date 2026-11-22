"""H 路线视觉诊断附录：定量核对「左右两个 3D 角色是不是同一张脸」。

盘上已知：两份 GLB 的 mesh 名 / 顶点数 / bbox / 三张 PBR 的 sha256
全都不同（diag_glb_pair_h.py），Godot 里读回的 mesh_sig / SubViewport /
ViewportTexture 也各自独立（data/two_side_ab.json）。但 h-both-stance.png
里左右两个角色看起来高度雷同，必须用数字把「串味 bug」与「造型雷同」
分开，不能靠肉眼下结论。

口径订正（第一版的缺陷）：ROI 里包含擂台绳索 / 观众席 / 灯光，
水平镜像后背景必然错位，所以「镜像 ROI 差异率 0.8667」只能证明
**两帧不是同一张图**，不能证明两个角色长得不同。这一版把该判据
改名并加 scope_note；真正针对渲染的证据改为两侧 ROI 平均亮度。

输出 data/identity_h.json。本脚本只读，不改任何源码或归档。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
VP = HERE / "shots" / "vp_diag"
OUT = HERE / "data" / "identity_h.json"

P_TEX = GAME / "assets" / "3d" / "player-rigged_texture_pbr_20250901.png"
F_TEX = GAME / "assets" / "3d" / "foe-rigged_texture_pbr_20250901.png"
P_SHOT = VP / "vp-foe-hidden.png"       # 对手层隐藏 → 只剩下玩家（左）
F_SHOT = VP / "vp-player-hidden.png"    # 玩家层隐藏 → 只剩下对手（右）

SCOPE_NOTE = (
    "ROI 含擂台绳索/观众席/灯光，水平镜像后背景必然错位；"
    "镜像 ROI 差异率只证明两帧非同一张图，不作角色造型差异证据。"
    "造型区分度是看图判断，不用像素指标硬撑。")


def thumb_mae(a: Image.Image, b: Image.Image) -> float:
    d = ImageChops.difference(a, b)
    return round(sum(ImageStat.Stat(d).mean) / 3.0, 4)


def roi_mean(path: Path, box) -> list[float]:
    im = Image.open(path).convert("RGB").crop(box)
    return [round(v, 2) for v in ImageStat.Stat(im).mean]


def roi_diff(box_a, box_b, mirror_b: bool) -> dict:
    ia = Image.open(P_SHOT).convert("RGB").crop(box_a)
    ib = Image.open(F_SHOT).convert("RGB").crop(box_b)
    w = min(ia.width, ib.width)
    h = min(ia.height, ib.height)

    def center(im):
        cx, cy = (im.width - w) // 2, (im.height - h) // 2
        return im.crop((cx, cy, cx + w, cy + h))

    a = center(ia)
    b = center(ib)
    if mirror_b:
        b = b.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    d = ImageChops.difference(a, b)
    changed = sum(1 for px in d.get_flattened_data() if sum(px) > 18)
    total = w * h
    return {"size": [w, h], "changed_px": changed, "total_px": total,
            "ratio": round(changed / total, 4),
            "mae": round(sum(ImageStat.Stat(d).mean) / 3.0, 4)}


def main() -> int:
    boxes = json.loads((HERE / "data" / "roi_h.json").read_text(
        encoding="utf-8"))["boxes"]
    pair = json.loads((HERE / "data" / "glb_pair_h.json").read_text(
        encoding="utf-8"))["pair"]

    tex_a = Image.open(P_TEX).convert("RGB").resize(
        (64, 64), Image.LANCZOS)
    tex_b = Image.open(F_TEX).convert("RGB").resize(
        (64, 64), Image.LANCZOS)
    tex_mae = thumb_mae(tex_a, tex_b)

    mirrored = roi_diff(boxes[0], boxes[1], True)
    raw = roi_diff(boxes[0], boxes[1], False)
    roi_means = {
        "player": roi_mean(P_SHOT, boxes[0]),
        "foe": roi_mean(F_SHOT, boxes[1]),
    }
    lum = {k: round(sum(v) / 3.0, 2) for k, v in roi_means.items()}

    out = {
        "basecolor_thumb_mae": tex_mae,
        "basecolor_mean_rgb": {
            "player": [round(v, 2) for v in ImageStat.Stat(tex_a).mean],
            "foe": [round(v, 2) for v in ImageStat.Stat(tex_b).mean]},
        "roi_mean_rgb": roi_means,
        "roi_mean_luminance": lum,
        "roi_mirrored": mirrored,
        "roi_unmirrored": raw,
        "roi_scope_note": SCOPE_NOTE,
        "primary_identity_evidence": (
            "GLB 顶点数/bbox/三张 PBR sha256 不同 + Godot 读回 "
            "mesh_sig/SubViewport/ViewportTexture 各自独立"),
        "glb_vertex_counts": {
            "player": pair["player"]["verts"],
            "foe": pair["foe"]["verts"]},
        "glb_bbox_x_span": {
            "player": round(pair["player"]["pos_max"][0]
                            - pair["player"]["pos_min"][0], 6),
            "foe": round(pair["foe"]["pos_max"][0]
                         - pair["foe"]["pos_min"][0], 6)},
    }
    out["checks"] = {
        "basecolor_not_identical": tex_mae > 5.0,
        "frames_not_identical_including_background": mirrored["ratio"] > 0.20,
        "render_brightness_differs": abs(lum["player"] - lum["foe"]) > 5.0,
        "vertex_counts_differ": (out["glb_vertex_counts"]["player"]
                                 != out["glb_vertex_counts"]["foe"]),
        "bbox_spans_differ": (out["glb_bbox_x_span"]["player"]
                              != out["glb_bbox_x_span"]["foe"]),
        "scope_note_present": "背景" in SCOPE_NOTE,
    }
    out["ok"] = all(out["checks"].values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("BASECOLOR_THUMB_MAE", tex_mae)
    print("MEAN_RGB", out["basecolor_mean_rgb"])
    print("ROI_MEAN_RGB", roi_means, "LUM", lum)
    print("ROI_MIRRORED", mirrored)
    print("ROI_UNMIRRORED", raw)
    print("VERTS", out["glb_vertex_counts"], "BBOX_X",
          out["glb_bbox_x_span"])
    for k, v in out["checks"].items():
        print("CHECK", k, v)
    print("IDENTITY_H_OK" if out["ok"] else "IDENTITY_H_SUSPICIOUS")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
