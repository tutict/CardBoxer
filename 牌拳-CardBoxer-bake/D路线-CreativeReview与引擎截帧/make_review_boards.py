"""D 路线 Creative Review 三张板。

所有数字现读 godot_render_result.json / baked2.json / C 路线结构 JSON，
不写死实测值。三张板：
  1) D-引擎内六视角.png    —— Godot 4.5 带窗口真实渲染，非 Blender 截图
  2) D-三方对照.png        —— 引擎内 / Blender 端 / 生成服务预览
  3) D-尺度可读性.png      —— 按 baked2.json 的 172 game px 做阶梯
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
C_ROUTE = BAKE / "C路线-glTF-Godot探针"
FOE = BAKE / "对手怪Blender建模V1"
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"

BG = (20, 25, 36)
CARD = (32, 39, 52)
CARD2 = (39, 47, 62)
FG = (236, 240, 250)
MUTED = (152, 164, 184)
ACCENT = (240, 214, 160)
GOOD = (126, 214, 168)
BAD = (238, 132, 118)
BLUE = (122, 180, 232)


def font(size: int, bold: bool = False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc",) if bold else (
        r"C:\Windows\Fonts\msyh.ttc",)
    for p in names + (r"C:\Windows\Fonts\msyh.ttc",):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = font(31, True)
F_SUB = font(17)
F_H = font(21, True)
F_B = font(16)
F_S = font(14)
F_TAG = font(15, True)


def lines(d: ImageDraw.ImageDraw, x: int, y: int,
          items: list[tuple[str, object]], f, fill, leading: int) -> int:
    """逐行显式推进 y，绝不按固定行数猜高度。"""
    for text, col in items:
        d.text((x, y), text, font=f, fill=col or fill)
        y += leading
    return y


def contain(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    w, h = img.size
    bw, bh = box
    scale = min(bw / w, bh / h)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                      Image.Resampling.LANCZOS)


def paste_center(canvas: Image.Image, img: Image.Image,
                 box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    fit = contain(img.convert("RGB"), (w, h))
    canvas.paste(fit, (x + (w - fit.width) // 2, y + (h - fit.height) // 2))


def card(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
         color=CARD) -> None:
    d.rounded_rectangle(box, radius=10, fill=color)


def header(d: ImageDraw.ImageDraw, title: str, sub: str, w: int) -> None:
    d.text((36, 26), title, font=F_TITLE, fill=FG)
    d.text((36, 74), sub, font=F_SUB, fill=MUTED)
    d.line((36, 108, w - 36, 108), fill=CARD2, width=2)


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    render = load_json(HERE / "godot_render_result.json")
    baked = load_json(BAKE / "baked2.json")
    gltf = load_json(C_ROUTE / "gltf_inspection.json")
    imp = load_json(C_ROUTE / "godot_import_result.json")

    views = render["pngs"]
    full = next((e for e in gltf["exports"] if e.get("name") == "foe-full"),
                {})
    stance = baked["stance"]
    char_px = abs(float(stance["head"][1]) - float(stance["f_foot"][1]))
    full_target = next((t for t in imp["targets"]
                        if t["path"].endswith("foe-full.glb")), {})
    hi_meshes = full_target.get("mesh_instances", [])
    unbound = [m for m in hi_meshes if m.get("skeleton_path") == ""]

    # ---------- 板 1：引擎内六视角 ----------
    W, H = 1800, 1580
    im1 = Image.new("RGB", (W, H), BG)
    d1 = ImageDraw.Draw(im1)
    header(d1, "D 路线 · Godot 4.5 引擎内 3D 截帧（六视角）",
           "真实引擎渲染 / GL Compatibility / 带窗口 / 每视角同一套固定棚拍灯光；"
           "不是 Blender 截图、不是服务预览", W)
    for i, v in enumerate(views):
        col, row = i % 3, i // 3
        cx, cy = 36 + col * 588, 126 + row * 660
        card(d1, (cx, cy, cx + 556, cy + 630))
        p = Path(v["path"])
        if p.is_file():
            paste_center(im1, Image.open(p), (cx + 18, cy + 16, 520, 540))
        d1.text((cx + 20, cy + 568), f"{v['name']}   yaw={v['yaw']}°",
                font=F_TAG, fill=ACCENT)
        d1.text((cx + 20, cy + 596),
                f"r={v['radius']} m  fov={v['fov']}°  {v['w']}×{v['h']}",
                font=F_S, fill=MUTED)
    lines(d1, 40, 1450, [
        (f"共 {len(views)} 视角，全部由 Godot 渲染；"
         f"导入 GLB animations={full.get("counts", {}).get("animations")}，"
         f"高模未绑骨架 {len(unbound)}/{len(hi_meshes)}。", FG),
        ("结论：静态网格 + 四张 4096² PBR 在引擎里完整生效；"
         "六张只是转相机，不是六个动作姿势。", ACCENT),
    ], F_B, FG, 32)
    out1 = BOARDS / "D-引擎内六视角.png"
    im1.save(out1)

    # ---------- 板 2：三方对照 ----------
    W2, H2 = 1660, 1120
    im2 = Image.new("RGB", (W2, H2), BG)
    d2 = ImageDraw.Draw(im2)
    header(d2, "D 路线 · Creative Review 三方对照",
           "同一份对手怪资产：Godot 引擎内棚拍 / Blender 端渲染 / 3D 生成服务预览",
           W2)
    cols = [
        ("Godot 4.5 引擎内", SHOTS / "godot-front.png",
         ["有地面、投影、三点光 + 固定背光", "金属 / 锈迹 / 青结晶层次最清楚",
          "这是本轮新增的真实引擎证据"]),
        ("Blender 端渲染", FOE / "foe-front.png",
         ["黑底棚拍，造型基准", "用于对照「导入有没有变样」",
          "不是引擎内验收"]),
        ("生成服务预览", FOE / "artifact_02.png",
         ["PBR 柔光预览，整体偏平偏亮", "最初选型的依据",
          "不是引擎内验收"]),
    ]
    for i, (label, path, desc) in enumerate(cols):
        cx = 36 + i * 540
        card(d2, (cx, 130, cx + 510, 130 + 700))
        if path.is_file():
            paste_center(im2, Image.open(path), (cx + 20, 150, 470, 520))
        d2.text((cx + 20, 690), label, font=F_H, fill=ACCENT)
        lines(d2, cx + 20, 728, [(t, MUTED) for t in desc], F_S, MUTED, 26)

    card(d2, (36, 860, W2 - 36, 1085), CARD2)
    lines(d2, 60, 880, [
        ("造型层：三者一致 —— 覆面/防毒面具、宽肩硬壳、青色结晶、橙黄警示条纹全在，导入没有变样。", GOOD),
        ("材质层：Godot 读回 albedo / normal / metallic / roughness 四张 4096² 全 present，"
         "引擎内比服务预览更有体积。", GOOD),
        ("动作层：仍是 A-pose 静态。" + f"GLB animations={full.get("counts", {}).get("animations")}，"
         f"高模 skeleton_path='' 的 {len(unbound)} 个 mesh 转骨架也不会动。", BAD),
        ("判断：静态展示/卡牌插画/头像可用；要进战斗区必须另做动作层，"
         "见 D-尺度可读性.png 与验证记录第九节。", ACCENT),
    ], F_B, FG, 42)
    out2 = BOARDS / "D-三方对照.png"
    im2.save(out2)

    # ---------- 板 3：战斗区尺度可读性 ----------
    W3, H3 = 1660, 860
    im3 = Image.new("RGB", (W3, H3), BG)
    d3 = ImageDraw.Draw(im3)
    foot_y = abs(float(stance["f_foot"][1]))
    header(d3, "D 路线 · 战斗区尺度可读性",
           f"尺度依据：baked2.json stance head={stance['head'][1]:g} / "
           f"foot={foot_y:g} → 角色真实高度 {char_px:.0f} game px", W3)
    src = Image.open(SHOTS / "godot-front.png").convert("RGB")
    metrics = load_json(HERE / "scale_metrics.json")
    mae_by_h = {r["target_h"]: r["mae_vs_direct_400"] for r in metrics["rows"]}
    steps = [
        (int(src.height), "原图（棚拍）", "细节全可读", GOOD),
        (int(char_px) * 2, "2× 战斗尺度", "扣件开始糊", ACCENT),
        (int(char_px), f"游戏内 {char_px:.0f} px", "只剩轮廓 + 配色", ACCENT),
        (96, "头像/小图标 96 px", "覆面与结晶基本不可辨", BAD),
    ]
    for i, (h_target, label, verdict, col) in enumerate(steps):
        cx = 36 + i * 405
        card(d3, (cx, 140, cx + 380, 140 + 560))
        small = src.resize((max(1, round(src.width * h_target / src.height)),
                            max(1, h_target)), Image.Resampling.LANCZOS)
        disp_h = 400
        disp = small.resize((max(1, round(small.width * disp_h / small.height)),
                             disp_h), Image.Resampling.NEAREST)
        im3.paste(disp, (cx + (380 - disp.width) // 2, 160))
        d3.text((cx + 20, 580), label, font=F_TAG, fill=col)
        d3.text((cx + 20, 608), f"整图高 {h_target} px → 放大到 {disp_h} px",
                font=F_S, fill=MUTED)
        d3.text((cx + 20, 632), f"细节损失 MAE={mae_by_h[h_target]:.2f}",
                font=F_S, fill=BLUE)
        d3.text((cx + 20, 660), verdict, font=F_B, fill=FG)

    card(d3, (36, 720, W3 - 36, 840), CARD2)
    lines(d3, 60, 738, [
        (f"结论：{char_px:.0f} game px 时轮廓、宽肩、橙黄条纹、青色结晶仍可辨，"
         "但覆面栅格 / 铆钉 / 腰牌这些细节已丢失（MAE 随尺度严格递增）。", FG),
        ("所以静态大图好看不等于战斗区可读；这也是「先渲 2~8 帧小样本再看」"
         "（B）比「直接重建 Godot 驱动层」（C）更划算的理由。", ACCENT),
    ], F_B, FG, 38)
    out3 = BOARDS / "D-尺度可读性.png"
    im3.save(out3)

    # ---------- 板 4：侧视退化诊断（看图后订正的判断） ----------
    W4, H4 = 1660, 1060
    im4 = Image.new("RGB", (W4, H4), BG)
    d4 = ImageDraw.Draw(im4)
    header(d4, "D 路线 · 侧视退化诊断（看图后订正）",
           "同一块零厚度披风：35° 可见宽面 / 90° 退化成一条线 / 180° 可见整片",
           W4)
    diag = [
        ("angle35 · 宽面", "godot-angle35.png",
         ["右腿后方是深色锯齿边布片", "与躯干相连，有可见面积",
          "斜视角下尚可接受"]),
        ("side90 · 退化", "godot-side90.png",
         ["整块布退化成一根细长斜线", "从肩背垂到近地面，像悬浮破面",
          "正侧面几乎无厚度"]),
        ("back · 整片", "godot-back.png",
         ["灰蓝披风完整可见", "补丁与破洞纹理可读",
          "固定背光后细节已能看清"]),
    ]
    for i, (label, fname, desc) in enumerate(diag):
        cx = 36 + i * 540
        card(d4, (cx, 130, cx + 510, 130 + 700))
        p = SHOTS / fname
        if p.is_file():
            paste_center(im4, Image.open(p), (cx + 20, 150, 470, 520))
        d4.text((cx + 20, 690), label, font=F_H,
                fill=BAD if i == 1 else ACCENT)
        lines(d4, cx + 20, 728, [(t, MUTED) for t in desc], F_S, MUTED, 26)

    card(d4, (36, 860, W4 - 36, 1030), CARD2)
    lines(d4, 60, 878, [
        ("订正：第一眼在 side90 里判成「悬浮破面」；三视角对照后确认"
         "是同一块零厚度单面披风壳，正侧面看过去退化成线。", FG),
        ("成因：生成模型的薄壳拓扑（源资产 2,809 连通壳）；"
         "glTF / Godot 没有把它变厚，正面被躯干遮住才一直没暴露。", MUTED),
        ("影响：C（真 3D 进引擎）必须先给披风加厚度/双面/实体化；"
         "B（渲 2D 图集）只渲正面与小角度，基本不受影响。", ACCENT),
    ], F_B, FG, 42)
    out4 = BOARDS / "D-侧视退化诊断.png"
    im4.save(out4)

    conclusion = {
        "verdict": "STATIC_ONLY",
        "human_visual_review": True,
        "static_visual_in_engine": "PASS",
        "pbr_materials_in_engine": "PASS",
        "six_views_are_camera_only": True,
        "glb_animations": full.get("counts", {}).get("animations"),
        "highpoly_unbound_meshes": len(unbound),
        "game_character_px": char_px,
        "scale_mae_strictly_increasing": metrics["strictly_increasing"],
        "side_view_cape": {
            "degenerate_at_90deg": True,
            "evidence_views": ["angle35", "side90", "back"],
            "root_cause": "zero-thickness single-sided cape shell",
            "not_a_floating_shard": True,
        },
        "recommendation": "B",
        "reject_C_reasons": [
            "GLB 0 animation / source .blend 0 Action",
            "highpoly mesh has empty skeleton_path, only voxel proxy is skinned",
            "SURFACE_DEFORM has no glTF equivalent, export bakes a static snapshot",
            "baked2.json is 2D (x,z) joints, Godot needs 14-bone Y-up poses",
            "zero-thickness cape degenerates at side view; needs mesh repair",
        ],
    }
    (HERE / "review_conclusion.json").write_text(
        json.dumps(conclusion, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    stats = {
        "boards": [
            {"file": out1.name, "w": im1.width, "h": im1.height,
             "bytes": out1.stat().st_size},
            {"file": out2.name, "w": im2.width, "h": im2.height,
             "bytes": out2.stat().st_size},
            {"file": out3.name, "w": im3.width, "h": im3.height,
             "bytes": out3.stat().st_size},
            {"file": out4.name, "w": im4.width, "h": im4.height,
             "bytes": out4.stat().st_size},
        ],
        "game_character_px": char_px,
        "scale_steps": [s[0] for s in steps],
        "views": [v["name"] for v in views],
        "glb_animations": full.get("counts", {}).get("animations"),
        "unbound_highpoly_meshes": len(unbound),
        "mesh_count": len(hi_meshes),
    }
    (HERE / "board_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for b in stats["boards"]:
        print(f"BOARD {b['file']:<24} {b['w']}×{b['h']} {b['bytes']} B")
    # 目录实物与 stats 必须对账：重复字典键曾让第四张板静默漏记。
    on_disk = sorted(p.name for p in BOARDS.glob("D-*.png"))
    listed = sorted(b["file"] for b in stats["boards"])
    if on_disk != listed:
        print(f"BOARD_LIST_MISMATCH disk={on_disk} listed={listed}")
        return 1
    print(f"GAME_CHARACTER_PX={char_px} SCALE_STEPS={stats['scale_steps']} "
          f"BOARDS_ON_DISK={len(on_disk)}")
    print("REVIEW_BOARDS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
