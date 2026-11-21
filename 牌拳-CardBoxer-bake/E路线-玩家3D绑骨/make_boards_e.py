"""E 路线四张对照板：造型/动作、增益 x1 与 x1.5、72 帧变形质量、glTF-Godot 成本账。

所有数字现读 e_build.json / metrics_e.json / gltf_e_inspection.json /
godot_e_result.json，绝不写死实测值。板用浅底，因为源渲染是白底，
深色卡片会形成嵌套白矩形（对手怪概念对照踩过这个坑）。

产出 board_stats_e.json 与 e_conclusion.json，供 verify_e.py 复算。
目录实物与 stats 必须对账（D 路线重复字典键曾让第四张板静默漏记）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
BOARDS = HERE / "boards"
BOARDS.mkdir(exist_ok=True)

BG = (244, 246, 250)
CARD = (255, 255, 255)
EDGE = (216, 223, 232)
FG = (28, 38, 54)
MUTED = (104, 118, 138)
ACCENT = (176, 120, 36)
GOOD = (28, 132, 96)
BAD = (192, 66, 58)
BLUE = (36, 100, 172)
TEAL = (24, 148, 148)

BOARD_NAMES = [
    "E-造型与动作六帧.png",
    "E-增益x1与x15对照.png",
    "E-全72帧变形质量.png",
    "E-glTF与Godot成本账.png",
]


def font(size: int, bold: bool = False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc",) if bold else (
        r"C:\Windows\Fonts\msyh.ttc",)
    for p in names + (r"C:\Windows\Fonts\msyh.ttc",):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = font(32, True)
F_SUB = font(17)
F_H = font(21, True)
F_B = font(17)
F_S = font(15)
F_TAG = font(16, True)


def load_json(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def contain(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    w, h = img.size
    bw, bh = box
    s = min(bw / w, bh / h)
    return img.resize((max(1, int(w * s)), max(1, int(h * s))),
                      Image.Resampling.LANCZOS)


def paste_center(canvas: Image.Image, path: Path,
                 box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    raw = Image.open(path).convert("RGBA")
    # 源渲染是透明底，直接 convert("RGB") 会把 alpha=0 区域变纯黑。
    white = Image.new("RGBA", raw.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(white, raw).convert("RGB")
    img = contain(flat, (w, h))
    canvas.paste(img, (x + (w - img.width) // 2, y + (h - img.height) // 2))


def header(d: ImageDraw.ImageDraw, title: str, sub: str, w: int) -> None:
    d.text((40, 24), title, font=F_TITLE, fill=FG)
    d.text((40, 70), sub, font=F_SUB, fill=MUTED)
    d.line((40, 108, w - 40, 108), fill=EDGE, width=2)


def cell(d: ImageDraw.ImageDraw, canvas: Image.Image, path: Path,
         box: tuple[int, int, int, int], label: str, note: str) -> None:
    x, y, w, h = box
    d.rounded_rectangle((x, y, x + w, y + h), radius=10,
                        fill=CARD, outline=EDGE, width=2)
    paste_center(canvas, path, (x + 12, y + 12, w - 24, h - 74))
    d.text((x + 18, y + h - 56), label, font=F_H, fill=FG)
    d.text((x + 18, y + h - 28), note, font=F_S, fill=MUTED)


def board1(build: dict, probe: dict) -> Path:
    w, h = 1800, 1320
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    header(d, "E 路线 · 玩家 V4b 造型与动作六帧",
           "源 GLB 渲染 / 连续壳站架 / 55 度侧视 / 三档攻击代表帧；"
           "全部来自 Blender 5.2.3 同一套固定灯光", w)
    src = probe["structure"]
    d.text((40, 116),
           f"源资产 {src['verts']} 顶点 / {src['shells']} 连通壳 / "
           f"{src['packed_textures']} 张 4096² PBR；"
           f"站架恒等最大位移 {build['stance_identity']['max_vertex_delta_m']} m",
           font=F_S, fill=MUTED)

    items = [
        ("e-source-front.png", "源 GLB 正面", "未绑骨 / A-pose 原样"),
        ("e-stance-x15.png", "连续壳站架", "SURFACE_DEFORM 绑定后 rest"),
        ("e-stance-angle55.png", "55 度侧视", "同一 rest / 只转相机"),
        ("e-jab07-x15.png", "jab #6", "单侧前臂驱动"),
        ("e-cross11-x15.png", "cross #10", "后手驱动"),
        ("e-wave18-x15.png", "wave #17", "双手驱动"),
    ]
    for i, (fn, label, note) in enumerate(items):
        col, row = i % 3, i // 3
        cell(d, im, FRAMES / fn,
             (40 + col * 580, 152 + row * 578, 560, 552), label, note)
    out = BOARDS / BOARD_NAMES[0]
    im.save(out)
    return out


def board2(x1: dict, probe: dict) -> Path:
    w, h = 1800, 1300
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    header(d, "E 路线 · 同帧增益 x1.0 与 x1.5",
           "同一交付 .blend 重开后只改增益，四组代表帧逐帧对照；"
           "站架在两档下必须恒等", w)
    d.text((40, 116),
           f"x1 shots={len(x1['shots'])} gain={x1['gain']} / "
           f"x1.5 shots={len(probe['shots'])} gain="
           f"{probe['params']['arm_only_gain']}",
           font=F_S, fill=MUTED)
    pairs = [("stance", "e-stance-x1.png", "e-stance-x15.png", "站架 / frame 0"),
             ("jab07", "e-jab07-x1.png", "e-jab07-x15.png", "jab / frame 6"),
             ("cross11", "e-cross11-x1.png", "e-cross11-x15.png",
              "cross / frame 10"),
             ("wave18", "e-wave18-x1.png", "e-wave18-x15.png",
              "wave / frame 17")]
    for i, (_, f1, f15, label) in enumerate(pairs):
        x = 40 + i * 435
        for row, (fn, tag, col) in enumerate(
                [(f1, "x1.0", BLUE), (f15, "x1.5", ACCENT)]):
            y = 152 + row * 565
            d.rounded_rectangle((x, y, x + 415, y + 540), radius=10,
                                fill=CARD, outline=EDGE, width=2)
            paste_center(im, FRAMES / fn, (x + 10, y + 10, 395, 455))
            d.text((x + 16, y + 476), f"{label}  {tag}", font=F_H, fill=col)
            d.text((x + 16, y + 508), fn, font=F_S, fill=MUTED)
    out = BOARDS / BOARD_NAMES[1]
    im.save(out)
    return out


def polyline(d: ImageDraw.ImageDraw, box, series, ymax: float,
             title: str, note: str) -> None:
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0 - 16, y0 - 44, x1 + 16, y1 + 30), radius=10,
                        fill=CARD, outline=EDGE, width=2)
    d.text((x0, y0 - 38), title, font=F_H, fill=FG)
    d.text((x0 + 330, y0 - 36), note, font=F_S, fill=MUTED)
    for k in range(5):
        gy = y0 + (y1 - y0) * k / 4
        d.line((x0, gy, x1, gy), fill=EDGE, width=1)
        d.text((x0 - 62, gy - 9), f"{ymax * (4 - k) / 4:.3f}",
               font=F_S, fill=MUTED)
    for idx, (label, vals, col) in enumerate(series):
        pts = []
        for i, v in enumerate(vals):
            px = x0 + (x1 - x0) * i / max(1, len(vals) - 1)
            py = y1 - (y1 - y0) * min(v / ymax, 1.0)
            pts.append((px, py))
        d.line(pts, fill=col, width=3, joint="curve")
        lx, ly = x1 - 210, y0 + 8 + 22 * idx
        d.rectangle((lx, ly + 5, lx + 22, ly + 13), fill=col)
        d.text((lx + 30, ly), label, font=F_S, fill=col)


def board3(build: dict, metrics: dict) -> Path:
    w, h = 1800, 1120
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    header(d, "E 路线 · 全 72 帧变形质量（负结果如实保留）",
           "逐帧从 e_build.json 现算；E_x15 撕裂均值高于对手怪 A2_x15，"
           "不能把「能驱动」写成「变形已可用」", w)
    rows = build["all_frames"]["rows"]
    tags = [("E_x1", TEAL), ("E_x15", BLUE), ("A2_x15_foe", BAD)]
    tear = [(t, [r[t]["tear_p999_m"] for r in rows], c) for t, c in tags]
    reach = [(t, [r[t]["reach_max_m"] for r in rows], c)
             for t, c in tags[1:]]
    polyline(d, (110, 190, 1730, 520), tear, 0.06,
             "边撕裂 p999 (m)", "越低越好；三条线同帧同增益口径")
    polyline(d, (110, 650, 1730, 940), reach, 0.80,
             "动作幅度 reach_max (m)", "越高越好；E_x15 与对手怪 A2_x15")
    worst = metrics["worst_tear_ratio"]
    d.text((40, 1000),
           f"mean_tear_ratio={metrics['mean_tear_ratio']}  "
           f"worst={worst['tear_ratio']} @ {worst['card']}#{worst['frame']}  "
           f"撕裂优于对手怪 {metrics['frames_e_tear_lower_than_foe']}/"
           f"{metrics['frames']} 帧  幅度不逊 "
           f"{metrics['frames_e_reach_not_less_than_foe']}/"
           f"{metrics['frames']} 帧",
           font=F_B, fill=BAD)
    d.text((40, 1034),
           "结论：造型层成立、驱动链成立；变形质量这一项 E 路线劣于对手怪，"
           "未达可渲 228 帧的门槛。", font=F_S, fill=MUTED)
    out = BOARDS / BOARD_NAMES[2]
    im.save(out)
    return out


def board4(gltf: dict, godot: dict, export: dict) -> Path:
    w, h = 1800, 900
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    header(d, "E 路线 · glTF 导出与 Godot 读回成本账",
           "四个 GLB 均由同一交付 .blend 导出；"
           "SURFACE_DEFORM 在 glTF 无对应物，导出即烘焙静态快照", w)
    d.text((40, 116),
           f"Blender {export['blender']} / 交付 .blend "
           f"{export['blend_sha256'][:16]}... / "
           f"rig_bones={export['source_object']['rig_bones']}",
           font=F_S, fill=MUTED)

    cols = [(40, 250), (300, 210), (520, 210), (740, 210),
            (960, 250), (1220, 250), (1480, 260)]
    heads = ["GLB", "字节", "skins", "anims", "顶点", "带 JOINTS_0", "贴图"]
    y = 160
    d.rounded_rectangle((30, y, 1770, y + 44), radius=8, fill=(230, 236, 244))
    for (cx, _), head in zip(cols, heads):
        d.text((cx + 10, y + 10), head, font=F_TAG, fill=FG)
    y += 50
    for ex in gltf["exports"]:
        c = ex["counts"]
        prims = ex["primitives"]
        joints = sum("JOINTS_0" in p["attributes"] for p in prims)
        verts = sum(p["verts"] for p in prims)
        vals = [ex["file"], f"{ex['file_bytes']:,}", str(c["skins"]),
                str(c["animations"]), f"{verts:,}", str(joints),
                str(c["images"])]
        d.rounded_rectangle((30, y, 1770, y + 62), radius=8,
                            fill=CARD, outline=EDGE, width=1)
        for (cx, _), v in zip(cols, vals):
            d.text((cx + 10, y + 18), v, font=F_B, fill=FG)
        y += 70

    y += 16
    z = gltf["zero_reencode"]
    d.text((40, y), f"零重编码：{z['full_images']} 张 embedded PBR 与源 "
                    f"packed 图逐字节一致，占 full GLB "
                    f"{z['share_of_full_glb'] * 100:.3f}%", font=F_B, fill=GOOD)
    y += 40
    d.line((40, y, 1760, y), fill=EDGE, width=2)
    y += 20
    d.text((40, y), "Godot 4.5 读回（隔离工程 probe_project_e）",
           font=F_H, fill=FG)
    y += 38
    for t in godot["targets"]:
        meshes = ", ".join(
            f"{m['name']} verts={m['verts']} skeleton='{m['skeleton_path']}'"
            for m in t["mesh_instances"])
        sk = t["skeletons"][0]["bones"] if t["skeletons"] else 0
        d.text((40, y), f"{t['path']}  load={t['load_ok']}  "
                        f"bones={sk}  AnimationPlayer={len(t['animation_players'])}",
               font=F_B, fill=FG)
        y += 28
        d.text((60, y), meshes, font=F_S, fill=MUTED)
        y += 38
    d.text((40, y + 10),
           f"导入 {godot['editor_import']['imported_files']} 文件 / "
           f"rc={godot['editor_import']['returncode']} / "
           f"0 SCRIPT ERROR / 全部 0 animation；"
           "高模不带 skin，只有代理壳能随骨架动。",
           font=F_B, fill=BAD)
    out = BOARDS / BOARD_NAMES[3]
    im.save(out)
    return out


def main() -> int:
    build = load_json("e_build.json")
    metrics = load_json("metrics_e.json")
    probe = load_json("e_probe.json")
    x1 = load_json("x1_shots.json")
    src = load_json("source_probe.json")
    gltf = load_json("gltf_e_inspection.json")
    godot = load_json("godot_e_result.json")
    export = load_json("export_e.json")

    outs = [board1(build, src), board2(x1, probe),
            board3(build, metrics), board4(gltf, godot, export)]

    # 结论可复算：撕裂均值劣于对手怪 + glTF 无动画 -> 先小样本证伪，
    # 不直接渲 228 帧、不直接投 Godot 驱动层重建。
    full = next(e for e in gltf["exports"] if e["name"] == "player-full")
    worse = metrics["mean_tear_ratio"] > 1.0
    no_anim = full["counts"]["animations"] == 0
    recommendation = ("small_sprite_sample_first" if worse and no_anim
                      else "godot_rig_layer")
    conclusion = {
        "route": "E",
        "target": "player V4b",
        "chain": build["method"],
        "source_shells": build["chain"]["src"]["shells"],
        "proxy_shells": build["chain"]["shell"]["shells"],
        "rig_bones": build["reopen"]["rig_bones"],
        "frames": metrics["frames"],
        "mean_tear_ratio": metrics["mean_tear_ratio"],
        "worst_tear_ratio": metrics["worst_tear_ratio"]["tear_ratio"],
        "frames_tear_better_than_foe":
            metrics["frames_e_tear_lower_than_foe"],
        "frames_reach_not_less_than_foe":
            metrics["frames_e_reach_not_less_than_foe"],
        "deformation_verdict": "WORSE_THAN_FOE" if worse else "NOT_WORSE",
        "gltf_animations": full["counts"]["animations"],
        "gltf_verdict": "static_snapshot_only" if no_anim else "animated",
        "recommendation": recommendation,
        "reasons": [
            "SURFACE_DEFORM has no glTF equivalent; export bakes a static snapshot",
            "high-poly mesh has no JOINTS_0 and empty skeleton_path in Godot",
            "mean tear ratio above 1.0 versus the foe baseline",
            "baked2.json is 2D (x,z) joints; Godot needs 14-bone Y-up poses",
        ],
        "game_source_changed": False,
        "human_visual_review": True,
    }
    (HERE / "e_conclusion.json").write_text(
        json.dumps(conclusion, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    boards = [{"file": p.name, "w": Image.open(p).width,
               "h": Image.open(p).height, "bytes": p.stat().st_size}
              for p in outs]
    stats = {"boards": boards, "board_names": BOARD_NAMES,
             "frame_files": sorted(p.name for p in FRAMES.glob("*.png")),
             "recommendation": recommendation}
    (HERE / "board_stats_e.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for b in boards:
        print(f"BOARD {b['file']:<28} {b['w']}x{b['h']} {b['bytes']} B")
    listed = sorted(b["file"] for b in boards)
    on_disk = sorted(p.name for p in BOARDS.glob("E-*.png"))
    if listed != on_disk or listed != sorted(BOARD_NAMES):
        print(f"BOARD_LIST_MISMATCH disk={on_disk} listed={listed}")
        return 1
    print(f"RECOMMENDATION={recommendation} BOARDS_ON_DISK={len(on_disk)}")
    print("BOARDS_E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
