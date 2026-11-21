"""把 Blender 侧的 gain sweep 与渲染帧合并成「动作幅度 vs 撕裂」可复算报告。

指标选择有实证过程，两次负结果都保留：
  V1 逐像素 RGB/alpha 差异 / 前景并集 -> 0.71..0.80 且与增益无关，被 EEVEE
     光照/量化抖动占满；
  V2 alpha 轮廓 XOR / 前景并集 -> 0.35..0.57 且 jab 随增益反而下降，仍被
     半透明边缘抖动与 root 平移污染；
  V3 采用**确定性几何量**：pose_frame 输出的最大骨角 max_delta_deg 作幅度，
     evaluated 网格的 edge tear p999 作撕裂。两者都不经过渲染，不受抖动影响。
渲染像素指标降级为 diagnostic_only，只记录、不作判据。看图结论见验证记录。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
FRAMES = HERE / "frames"
PUPPET = BAKE / "3D攻击GIF" / "frames" / "puppet_foe"
BLENDER_JSON = HERE / "gain_sweep_blender.json"
OUT_JSON = HERE / "gain_sweep.json"
OUT_PNG = HERE / "增益-撕裂权衡.png"

ALPHA_FG = 32
LOWFREQ = 32
RIGID_BASELINE_P999 = 0.28048  # c_build.json jab8_ab.rigid_tear.p999_edge_tear_m


def font(size, bold=False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc") if bold \
        else (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf")
    for p in names:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def load(path: Path) -> Image.Image:
    assert path.is_file(), f"missing frame: {path}"
    return Image.open(path).convert("RGBA")


def diagnostic_pixels(a: Image.Image, b: Image.Image) -> dict:
    """只作记录、不作判据的渲染像素对照。"""
    assert a.size == b.size, (a.size, b.size)
    ma = a.getchannel("A").point(lambda v: 255 if v > ALPHA_FG else 0)
    mb = b.getchannel("A").point(lambda v: 255 if v > ALPHA_FG else 0)
    union = ImageChops.lighter(ma, mb).histogram()[255]
    xor = ImageChops.difference(ma, mb).point(
        lambda v: 255 if v > 128 else 0).histogram()[255]
    la = a.convert("L").resize((LOWFREQ, LOWFREQ), Image.LANCZOS)
    lb = b.convert("L").resize((LOWFREQ, LOWFREQ), Image.LANCZOS)
    mae = ImageStat.Stat(ImageChops.difference(la, lb)).mean[0]
    return {"alpha_xor_ratio": round(xor / union, 6) if union else 0.0,
            "lowfreq_mae": round(mae, 4)}


def main() -> int:
    data = json.loads(BLENDER_JSON.read_text(encoding="utf-8"))
    rest = load(FRAMES / "c-rest-unposed.png")

    rows = []
    for entry in data["sweep"]:
        g, mode = entry["gain"], entry["mode"]
        for r in entry["rows"]:
            card, fr = r["card"], r["frame"]
            png = FRAMES / r["png"]["file"]
            diag = diagnostic_pixels(rest, load(png))
            rows.append({"gain": g, "mode": mode, "card": card, "frame": fr,
                         "png": r["png"]["file"],
                         "max_delta_deg": r["max_delta_deg"],
                         "p999_edge_tear_m": r["tear"]["p999_edge_tear_m"],
                         "edges_gt_5cm": r["tear"]["edges_gt_5cm"],
                         "max_displacement_m": r["displacement"]["max_displacement_m"],
                         "diagnostic_only": diag})

    all_mode = [r for r in rows if r["mode"] == "all"]
    arm_mode = [r for r in rows if r["mode"] == "arm_only"]
    gains = sorted({r["gain"] for r in all_mode})

    # 确定性结论：所有档的 p999 撕裂都要远低于刚性权重基线
    worst_p999 = max(r["p999_edge_tear_m"] for r in rows)
    verdict = {
        "primary_amplitude_metric": "max_delta_deg (pose_frame geometry)",
        "primary_tear_metric": "p999_edge_tear_m (evaluated mesh edges)",
        "rigid_baseline_p999_m": RIGID_BASELINE_P999,
        "worst_sweep_p999_m": worst_p999,
        "worst_over_rigid": round(worst_p999 / RIGID_BASELINE_P999, 4),
        "all_gains_deltas_deg": {
            str(g): {r["card"]: r["max_delta_deg"]
                     for r in all_mode if r["gain"] == g} for g in gains},
        "arm_only_deltas_deg": {
            str(g): {r["card"]: r["max_delta_deg"]
                     for r in arm_mode if r["gain"] == g}
            for g in sorted({r["gain"] for r in arm_mode})},
        "visual_review": {
            "x1.0_all": "upright, continuous silhouette, modest reach",
            "x1.5_all": "upright, continuous silhouette, clearly larger reach",
            "x2.0_all": "slight body lean, silhouette still complete",
            "x3.0_all": "torso tilted ~45deg, arm out of frame: unusable",
            "x3.0_arm_only": "torso upright but arm raised past frame top: unusable",
        },
        "usable_gain_range": "1.0 .. 1.5 (2.0 marginal)",
        "root_cause": "amplitude limited by retarget gains tuned for 2D puppet, "
                      "not by mesh topology; raise arm_gain_deg only, never torso_gain/cap",
    }

    report = {
        "method": "deterministic geometry: max pose-bone delta angle as amplitude, "
                  "evaluated-mesh edge tear p999 as tearing; rendered-pixel metrics "
                  "kept as diagnostic_only negative results",
        "rejected_metrics": [
            "per-pixel RGB/alpha diff ratio: 0.71..0.80, gain-independent (TAA noise)",
            "alpha silhouette XOR ratio: 0.35..0.57, jab decreases with gain",
        ],
        "baseline_mapping_sha256": data["baseline_mapping_sha256"],
        "rows": rows,
        "verdict": verdict,
        "rigid_baseline_source": "c_build.json jab8_ab.rigid_tear.p999_edge_tear_m",
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # --- 图：几何幅度 vs 撕裂（all 模式四档） ---
    W, H = 1120, 720
    BG, PANEL = (24, 27, 38), (38, 43, 58)
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    FH, FL, FS = font(24, True), font(17, True), font(14)
    d.text((32, 18), "C 路线 · 增益扫描：确定性几何幅度 vs 边撕裂",
           font=FH, fill=(238, 242, 252))
    d.text((32, 52), "青=最大骨角 max_delta_deg（幅度）  橙=边撕裂 p999（米）  "
           "刚性权重基线 0.28048 m 见下方数字",
           font=FS, fill=(160, 170, 190))

    for ci, card in enumerate(("jab", "cross", "wave")):
        cx, cy, cw, ch = 32 + ci * 360, 92, 336, 300
        d.rectangle((cx, cy, cx + cw, cy + ch), fill=PANEL)
        d.text((cx + 12, cy + 8), f"{card} · 命中帧", font=FL, fill=(240, 214, 160))
        cr = [r for r in all_mode if r["card"] == card]
        amps = [r["max_delta_deg"] for r in cr]
        tears = [r["p999_edge_tear_m"] for r in cr]
        x0, x1 = cx + 46, cx + cw - 22
        y0, y1 = cy + 48, cy + ch - 48
        amax = max(amps + [1]) * 1.25
        tmax = max(tears + [0.01]) * 1.25
        for k in range(5):
            gy = y0 + (y1 - y0) * k / 4
            d.line((x0, gy, x1, gy), fill=(60, 66, 84), width=1)
        pa, pt = [], []
        for i in range(len(gains)):
            gx = x0 + (x1 - x0) * i / (len(gains) - 1)
            pa.append((gx, y1 - (y1 - y0) * amps[i] / amax))
            pt.append((gx, y1 - (y1 - y0) * tears[i] / tmax))
        d.line(pa, fill=(108, 208, 236), width=3)
        d.line(pt, fill=(244, 148, 96), width=3)
        # 橙色点必须先画：数值标签的底板要盖在它上面，否则橙点会吃掉数字
        for gx, gy in pt:
            d.ellipse((gx - 4, gy - 4, gx + 4, gy + 4), fill=(244, 148, 96))
        for (gx, gy), v in zip(pa, amps):
            d.ellipse((gx - 4, gy - 4, gx + 4, gy + 4), fill=(108, 208, 236))
            label = f"{v:.0f}°"
            f12 = font(12)
            tw = d.textbbox((0, 0), label, font=f12)[2]
            lx = min(max(gx - tw / 2, cx + 8), cx + cw - tw - 8)
            ly = gy - 26
            d.rectangle((lx - 4, ly - 2, lx + tw + 4, ly + 16), fill=PANEL)
            d.text((lx, ly), label, font=f12, fill=(150, 224, 246))
        for i, g in enumerate(gains):
            gx = x0 + (x1 - x0) * i / (len(gains) - 1)
            d.text((gx - 12, y1 + 8), f"x{g}", font=FS, fill=(190, 198, 214))

    ty = 410
    d.text((32, ty), "逐档数字 · all 模式（躯干 / 腿 / 臂增益一起放大）",
           font=FL, fill=(240, 214, 160))
    hdr = ["gain", "jab 幅度", "jab 撕裂", "cross 幅度", "cross 撕裂",
           "wave 幅度", "wave 撕裂"]
    colx = [32, 148, 296, 444, 592, 740, 888]
    for x, t in zip(colx, hdr):
        d.text((x, ty + 30), t, font=FS, fill=(176, 186, 204))
    for ri, g in enumerate(gains):
        yy = ty + 56 + ri * 28
        d.text((colx[0], yy), f"x{g}", font=FS, fill=(220, 226, 238))
        for ci, card in enumerate(("jab", "cross", "wave")):
            r = next(z for z in all_mode if z["gain"] == g and z["card"] == card)
            d.text((colx[1 + ci * 2], yy), f"{r['max_delta_deg']:.2f}°",
                   font=FS, fill=(150, 224, 246))
            d.text((colx[2 + ci * 2], yy), f"{r['p999_edge_tear_m']:.5f} m",
                   font=FS, fill=(244, 178, 132))
    d.text((32, ty + 182),
           f"刚性基线 jab#8 p999 = {RIGID_BASELINE_P999} m / >5cm 边 916；"
           f"全部 7 档最坏 p999 = {worst_p999:.5f} m（基线的 {verdict['worst_over_rigid']*100:.1f}%）。",
           font=FS, fill=(190, 198, 214))
    d.text((32, ty + 206),
           "看图：x1.5 人形完整且幅度更大；x2.0 略斜；x3.0 躯干斜转、手臂出框。只放大手臂不斜转但过抬。",
           font=FS, fill=(190, 198, 214))
    im.save(OUT_PNG)

    print("ANALYZE_SWEEP_OK")
    print(f"  worst_p999={worst_p999:.5f} m  rigid={RIGID_BASELINE_P999}  "
          f"ratio={verdict['worst_over_rigid']}")
    print(f"  usable_gain_range={verdict['usable_gain_range']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
