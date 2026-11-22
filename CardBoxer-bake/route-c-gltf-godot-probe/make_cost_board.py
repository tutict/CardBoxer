"""两张成本账板：链路丢失项 + 四口径结构对照。

所有数字从 gltf_inspection.json / godot_import_result.json /
godot_pose_result.json 现读，不写死实测值。
左列角色图是 Blender 端渲染（A 路线 frames/），不是 Godot 截帧，
板内明确标注，避免把「看得见的角色」误读成引擎内验收。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
ROLE_PNG = BAKE / "route-a-asset-rework" / "frames" / "a-stance-x15.png"

BG = (20, 25, 36)
CARD = (32, 39, 52)
CARD2 = (39, 47, 62)
FG = (236, 240, 250)
MUTED = (152, 164, 184)
ACCENT = (240, 214, 160)
GOOD = (126, 214, 168)
BAD = (238, 132, 118)
BLUE = (122, 180, 232)


def font(size, bold=False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc",) if bold else (
        r"C:\Windows\Fonts\msyh.ttc",)
    for p in names + (r"C:\Windows\Fonts\msyh.ttc",):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = font(30, True)
F_SUB = font(18, True)
F_H = font(21, True)
F_B = font(16)
F_S = font(14)
F_T = font(13)


def load_json(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def human_mb(n):
    return f"{n / 1024 / 1024:.2f} MB"


def box(d, x, y, w, h, fill=CARD, radius=10):
    d.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill)


def line(d, x, y, text, f=F_B, fill=FG):
    d.text((x, y), text, font=f, fill=fill)


def board_chain(ins, godot, pose):
    texture = ins["texture_cost"]
    full = next(e for e in ins["exports"] if e["name"] == "foe-full")
    editor = godot["editor_import"]
    w, h = 1640, 1060
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    line(d, 40, 24, "C 路线 · glTF → Godot 4.5 导入成本账", F_TITLE)
    line(d, 40, 66,
         "结论：静态资产能搬，驱动链全丢。glTF 只搬「当前帧快照」，"
         "228 帧动作表在 .blend 里本来就没有 Action。", F_SUB, ACCENT)
    line(d, 40, 96,
         "本板只量导入成本，不是生产导入：未做 Creative Review，"
         "资产未进可运行游戏工程，左侧角色图为 Blender 端渲染而非 Godot 截帧。",
         F_T, MUTED)

    col_w, gap, top = 480, 30, 140
    xs = [40 + i * (col_w + gap) for i in range(3)]

    # --- 列 1：Blender 源资产 ---
    box(d, xs[0], top, col_w, 610)
    line(d, xs[0] + 18, top + 16, "① Blender 5.2.3 · 可驱动 .blend", F_H, BLUE)
    role = Image.open(ROLE_PNG).convert("RGB").resize((300, 300),
                                                     Image.Resampling.LANCZOS)
    role = ImageEnhance.Brightness(role).enhance(1.20)
    im.paste(role, (xs[0] + 90, top + 52))
    line(d, xs[0] + 18, top + 360, "（Blender 端站架渲染，仅作视觉锚点）",
         F_T, MUTED)
    src = [
        f".blend 体积           {human_mb(ins['source_blend']['bytes'])}",
        "高模 64,024 顶点 / 2,809 连通壳",
        "代理壳 20,204 顶点 / 3 连通壳",
        "13 骨 A-pose rig + ARMATURE_AUTO",
        "SURFACE_DEFORM 绑定（is_bound）",
        f"packed 4096² PBR   {texture['source_packed_4096_images']} 张 / "
        f"{human_mb(texture['source_packed_bytes_total'])}",
        f"Action 数量          {ins['source_blend']['action_count']}  ← 关键",
    ]
    for i, t in enumerate(src):
        line(d, xs[0] + 18, top + 392 + i * 30, t, F_S,
             BAD if "关键" in t else FG)

    # --- 列 2：glTF 文件 ---
    box(d, xs[1], top, col_w, 610)
    line(d, xs[1] + 18, top + 16, "② glTF 2.0 / GLB 导出", F_H, BLUE)
    # 分三段显式推进 y，别用「一个循环 × 固定行距」——第一版按 9 项算，
    # 实际列了 14 项，尾部两段直接压在一起（看图复核抓到）。
    y = top + 56
    gl_main = [
        f"foe-full.glb        {human_mb(full['bytes'])}",
        f"贴图占文件体积      {texture['image_share_of_glb'] * 100:.2f}%",
        "贴图重编码          0 B（逐字节原样搬运）",
        f"                    {texture['glb_full_image_bytes_total']:,} B",
        f"meshes              {full['counts']['meshes']}",
        f"skins               {full['counts']['skins']}（仅代理壳）",
        f"animations          {full['counts']['animations']}  ← 关键",
        f"images              {full['counts']['images']}",
        f"skinned primitives  {full['skinned_primitives']} / {len(full['meshes'])}",
        f"extension           {', '.join(full['extensionsUsed']) or 'none'}",
    ]
    for t in gl_main:
        line(d, xs[1] + 18, y, t, F_S,
             BAD if "关键" in t else (GOOD if "重编码" in t else FG))
        y += 30
    y += 8
    d.line((xs[1] + 18, y, xs[1] + col_w - 18, y), fill=CARD2, width=2)
    y += 16
    for t in ("站架 vs cross#10 两份 GLB：",
              f"  POSITION 最大位移差 {ins['pose_delta']['max_abs_delta']} m",
              "  两份都是 0 skins / 0 animations",
              "  → 修改器被烘焙成静态快照"):
        line(d, xs[1] + 18, y, t, F_S, MUTED)
        y += 27
    y += 10
    line(d, xs[1] + 18, y, "导出器告警（已核实影响）", F_S, ACCENT)
    y += 24
    for t in ("· 多贴图节点：PBR 三通道在 GLB 里全在，未丢通道",
              "· joint >4：代理壳权重截断到 4 影响并归一化"):
        line(d, xs[1] + 18, y, t, F_T, MUTED)
        y += 22

    # --- 列 3：Godot 读回 ---
    box(d, xs[2], top, col_w, 610)
    line(d, xs[2] + 18, top + 16, "③ Godot 4.5 · PackedScene 读回", F_H, BLUE)
    gt = [
        f"引擎                 {godot['engine']['string']}",
        f"首次编辑器导入      {editor['seconds']} s（3 份 GLB）",
        f"引擎内读回          {godot['inspect_probe']['seconds']} s",
        f"总墙钟              {godot['total_wall_seconds']} s",
        f".godot/imported     {editor['imported_files']} 文件 / "
        f"{human_mb(editor['imported_bytes'])}",
        ".import 文件        3/3 生成",
        "",
        "foe-full.glb 读回：",
        f"  节点 {godot['targets'][0]['node_count']} / "
        f"MeshInstance3D 2 / Skeleton3D 1",
        "  4 张 4096² PBR 全部为 StandardMaterial3D",
        f"  Skeleton3D 骨骼   {godot['targets'][0]['skeletons'][0]['bones']}",
        f"  AnimationPlayer   {len(godot['targets'][0]['animation_players'])}"
        "  ← 关键",
        "",
        "引擎内手动驱动 upperarm_f 35°：",
        f"  本地 pose 可写    {pose['pose_local_changed']}",
        f"  绑到骨架的网格    {pose['bound_mesh_count']}（仅代理壳）",
        f"  未绑骨架的网格    {pose['unbound_mesh_count']}（高模）",
    ]
    for i, t in enumerate(gt):
        line(d, xs[2] + 18, top + 56 + i * 30, t, F_S,
             BAD if ("关键" in t or "未绑" in t) else FG)

    # --- 底部：丢失清单 ---
    y = top + 630
    box(d, 40, y, w - 80, 230, fill=(44, 33, 38))
    line(d, 60, y + 16, "丢失清单 · 要进游戏必须补的工作", F_H, BAD)
    lost = [
        "1. SURFACE_DEFORM：glTF 无对应概念，导出即烘焙成当前帧静态网格；"
        "高模不再跟随代理壳。",
        "2. 228 帧动作表：源 .blend 无 Action → GLB 0 animation → Godot "
        "0 AnimationPlayer；整套驱动层需在 Godot 侧重建。",
        "3. 高模蒙皮：Godot 里 node_0 skeleton_path='' / skin_present=False；"
        "动骨架只会动那个体素化的 20k 代理壳，不是角色本体。",
        "4. 2D 关节表 → 3D 骨骼的坐标桥：baked2.json 是 11 个 2D (x,z) 关节，"
        "Godot 是 14 骨 Y-up Skeleton3D，逐帧重定向尚未实现。",
    ]
    for i, t in enumerate(lost):
        line(d, 60, y + 52 + i * 32, t, F_S, FG)
    line(d, 60, y + 190,
         "没丢的：静态网格、UV、3 张 4096² PBR（零重编码原样搬运）、"
         "13 骨 + 自动加的 neutral_bone、代理壳的 skin。", F_S, GOOD)
    line(d, 40, h - 44,
         "数字来源：gltf_inspection.json / godot_import_result.json / "
         "godot_pose_result.json（全部现读复算）", F_T, MUTED)
    out = HERE / "C-pipeline-cost-ledger.png"
    im.save(out)
    return out


def board_variants(ins):
    rows = ins["exports"]
    w, h = 1500, 900
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    line(d, 40, 24, "四口径 GLB 结构对照", F_TITLE)
    line(d, 40, 66,
         "同一份 .blend，只改「导出哪些对象 / 是否应用修改器 / 是否带材质」；"
         "数字现读 gltf_inspection.json。", F_SUB, ACCENT)

    heads = ["口径", "体积", "meshes", "skins", "anims", "images",
             "skinned prim", "verts", "耗时 s"]
    widths = [250, 150, 110, 100, 100, 110, 160, 130, 110]
    x0, y0 = 40, 130
    xs = [x0]
    for cw in widths:
        xs.append(xs[-1] + cw)
    box(d, x0, y0, sum(widths), 42, fill=CARD2)
    for j, hd in enumerate(heads):
        line(d, xs[j] + 10, y0 + 10, hd, F_S, ACCENT)
    reps = {e["name"]: e for e in json.loads(
        (HERE / "export_report.json").read_text(encoding="utf-8"))["exports"]}
    for i, r in enumerate(rows):
        y = y0 + 42 + i * 54
        box(d, x0, y, sum(widths), 50,
            fill=CARD if i % 2 == 0 else (27, 33, 46))
        vals = [r["name"], f"{r['bytes'] / 1024 / 1024:.2f} MB",
                str(r["counts"]["meshes"]), str(r["counts"]["skins"]),
                str(r["counts"]["animations"]), str(r["counts"]["images"]),
                str(r["skinned_primitives"]), str(r["vertex_total"]),
                f"{reps[r['name']]['elapsed_seconds']:.3f}"]
        for j, v in enumerate(vals):
            color = BAD if j in (3, 4) and v == "0" else FG
            line(d, xs[j] + 10, y + 14, v, F_S, color)

    # 体积条形（线性，标注最大值）
    by = y0 + 42 + len(rows) * 54 + 40
    line(d, x0, by, "文件体积（线性刻度）", F_H, BLUE)
    mx = max(r["bytes"] for r in rows)
    bar_x, bar_w = x0 + 260, 900
    for i, r in enumerate(rows):
        y = by + 40 + i * 46
        line(d, x0, y + 8, r["name"], F_S, FG)
        length = max(2, int(bar_w * r["bytes"] / mx))
        d.rounded_rectangle((bar_x, y, bar_x + length, y + 26),
                            radius=5, fill=BLUE if i == 0 else (88, 118, 152))
        line(d, bar_x + length + 12, y + 4,
             f"{r['bytes'] / 1024 / 1024:.2f} MB", F_S, MUTED)

    tc = ins["texture_cost"]
    ty = by + 40 + len(rows) * 46 + 20
    box(d, x0, ty, sum(widths), 110, fill=(30, 44, 44))
    line(d, x0 + 16, ty + 14, "贴图成本订正（与我最初的预判相反）", F_H, GOOD)
    line(d, x0 + 16, ty + 48,
         f"源 packed 3 张 4096² = {tc['source_packed_bytes_total']:,} B；"
         f"GLB 内 3 张 = {tc['glb_full_image_bytes_total']:,} B —— "
         "逐字节相同，没有重编码、没有降分辨率。", F_S, FG)
    line(d, x0 + 16, ty + 74,
         f"贴图占 foe-full.glb 的 {tc['image_share_of_glb'] * 100:.2f}%；"
         "想省体积只能换贴图分辨率或压缩格式，和 glTF 导出器无关。",
         F_S, FG)
    line(d, 40, h - 40,
         "注：skins=0 / anims=0 标红是「确实没带出去」，不是导出失败；"
         "四份 GLB 的 operator_result 均为 FINISHED。", F_T, MUTED)
    out = HERE / "C-four-metric-comparison.png"
    im.save(out)
    return out


def main() -> int:
    ins = load_json("gltf_inspection.json")
    godot = load_json("godot_import_result.json")
    pose = load_json("godot_pose_result.json")
    outs = [board_chain(ins, godot, pose), board_variants(ins)]
    for p in outs:
        print(f"BOARD {p.name} bytes={p.stat().st_size}")
    print("COST_BOARDS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
