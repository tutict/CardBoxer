"""B 路线 P0 收尾：把隔离实证固化成 B-P1 要用的删除规则。

输入 probe_shell_isolate_b.py 的 data/shell_isolate_b.json + 11 张图；
输出 data/shell_targets_b.json（壳 ID 清单 + 空间/UV 锚点）
与 boards/B-壳隔离实证.png（看图证据拼板）。

关键纪律：删除规则写「壳 ID + 分组锚点 + 空间范围」三重，绝不只写区域名；
隔离图非空由 PIL 独立复核（Blender 侧只 File 大小，容易真空通过）。
用法：python make_shell_targets_b.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC = HERE / "data" / "shell_isolate_b.json"
OUT = HERE / "data" / "shell_targets_b.json"
BOARD = HERE / "boards" / "B-shell-isolation-evidence.png"
SHOTS = HERE / "shots" / "shell_isolate"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")

TARGET_GROUPS = ("G0_CAPE", "G1_SKIRT", "G2_HEAD_SMALL")
GROUP_MEANING = {
    "G0_CAPE": "背后一整片从肩垂到腿弯的破损长披风（V4b 黑披风）",
    "G1_SKIRT": "正面腰间倒三角长衫下摆 + 两侧细长布条（V4b 白衫）",
    "G2_HEAD_SMALL": "头顶圆顶发髻 + 双环/尖角结晶与头花（V4b 头饰）",
}
PANELS = [
    ("b-groups-front.png", "组色 · 正面"),
    ("b-groups-back.png", "组色 · 背面（披风全貌）"),
    ("b-groups-side.png", "组色 · 侧面"),
    # 负结果如实留档：本机 Workbench TEXTURE 与 MATERIAL 同色，
    # b-texture-front.png 没取得真实贴图外观参照，不进板子冒充证据。
    ("b-groups-angle45.png", "组色 · 45°"),
    ("b-only-G0_CAPE.png", "隔离 · 披风"),
    ("b-only-G1_SKIRT.png", "隔离 · 长衫下摆"),
    ("b-only-G2_HEAD_SMALL.png", "隔离 · 头顶装饰"),
    ("b-shells-front.png", "逐壳随机色 · 正面"),
]


def opaque_pixels(p: Path) -> int:
    im = Image.open(p).convert("RGBA")
    a = im.getchannel("A")
    return sum(1 for v in a.getdata() if v > 16)


def color_ratio(p: Path, kind: str) -> float:
    im = Image.open(p).convert("RGBA")
    px = list(im.getdata())
    n = len(px)
    hit = 0
    for r, g, b, a in px:
        if a <= 16:
            continue
        if kind == "blue" and b > g + 40 and b > r + 40 and b > 140:
            hit += 1
        elif kind == "green" and g > r + 40 and g > b + 30 and g > 140:
            hit += 1
        elif kind == "red" and r > g + 60 and r > b + 60 and r > 140:
            hit += 1
    return round(hit / n, 6)


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    table = src["shells_table"]
    assert src["checks"]["all_other_meshes_hidden"], \
        "探针没隐藏源对象，隔离图不可信"
    by_id = {r["shell_id"]: r for r in table}
    assert len(by_id) == len(table) == src["shells"]

    groups = {}
    for g in TARGET_GROUPS:
        rows = [r for r in table if r["group"] == g]
        ids = sorted(r["shell_id"] for r in rows)
        zs = [r["centroid"][2] for r in rows]
        zspans = [r["hi"][2] - r["lo"][2] for r in rows]
        groups[g] = {
            "meaning": GROUP_MEANING[g],
            "shells": len(ids), "verts": sum(r["verts"] for r in rows),
            "centroid_z_range": [round(min(zs), 4), round(max(zs), 4)],
            "max_z_span": round(max(zspans), 4),
            "anchor_region": sorted({r["region"] for r in rows}),
            "shell_ids": ids,
        }
    all_ids = [i for g in TARGET_GROUPS for i in groups[g]["shell_ids"]]

    # ── 拼板 ────────────────────────────────────────────────────
    cw, ch, pad, label = 300, 360, 16, 34
    cols = 4
    rows_n = (len(PANELS) + cols - 1) // cols
    W = cols * cw + (cols + 1) * pad
    H = rows_n * (ch + label) + (rows_n + 1) * pad
    canvas = Image.new("RGB", (W, H), (22, 26, 36))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 15) if FONT.is_file() \
        else ImageFont.load_default()
    for i, (name, title) in enumerate(PANELS):
        p = SHOTS / name
        im = Image.open(p).convert("RGBA").resize((cw, ch), Image.LANCZOS)
        x = pad + (i % cols) * (cw + pad)
        y = pad + (i // cols) * (ch + label + pad)
        tile = Image.new("RGB", (cw, ch), (238, 240, 246))
        tile.paste(im, (0, 0), im)
        canvas.paste(tile, (x, y))
        d.text((x + 2, y + ch + 4), title, font=f, fill=(215, 225, 245))
    d.text((pad, H - 22),
           "蓝=披风 绿=长衫下摆 红=头顶装饰 灰=保留本体；"
           "隔离图只显示目标组，其余壳移出视锥",
           font=f, fill=(235, 205, 140))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)

    # ── 判据（PIL 侧独立复核图非空，防 Blender 侧真空通过）──────
    iso = {g: SHOTS / f"b-only-{g}.png" for g in TARGET_GROUPS}
    iso_px = {g: opaque_pixels(p) for g, p in iso.items()}
    gf = SHOTS / "b-groups-front.png"
    gb = SHOTS / "b-groups-back.png"
    checks = {
        "source_probe_ok": src["ok"] and not src["failed"],
        "shell_table_covers_2809": len(table) == 2809,
        "target_ids_unique": len(all_ids) == len(set(all_ids)),
        "target_ids_all_in_table": all(i in by_id for i in all_ids),
        "cape_shell_count_2": groups["G0_CAPE"]["shells"] == 2,
        "skirt_shell_count_19": groups["G1_SKIRT"]["shells"] == 19,
        "head_small_shell_count_174": (
            groups["G2_HEAD_SMALL"]["shells"] == 174),
        "target_verts_8753": (
            sum(groups[g]["verts"] for g in TARGET_GROUPS) == 8753),
        "cape_spans_full_back": groups["G0_CAPE"]["max_z_span"] > 1.0,
        "skirt_below_waist": (
            groups["G1_SKIRT"]["centroid_z_range"][1] < 0.95),
        "head_ornament_above_head": (
            groups["G2_HEAD_SMALL"]["centroid_z_range"][0] > 1.48),
        "isolation_images_nonempty": all(v > 500 for v in iso_px.values()),
        "group_colors_visible_front": all(
            color_ratio(gf, k) > 0.001 for k in ("green", "red")),
        "cape_visible_from_back": color_ratio(gb, "blue") > 0.02,
        "board_written": BOARD.is_file()
                         and BOARD.stat().st_size > 100000,
    }
    report = {
        "source": str(SRC),
        "source_blend_sha256": src["source_blend_sha256"],
        "base_color_sha256": src["base_color_sha256"],
        "surgery_method": (
            "目标壳所有顶点塌缩到该壳自身质心（+1e-5 微抖动保法线），"
            "面退化成零面积不可见；不是 r1 的轴向压缩，不撕面。"
            "顶点/面/UV 层/材质/权重数组数量逐项守恒。"),
        "target_groups": groups,
        "target_shell_ids": sorted(all_ids),
        "totals": {
            "shells": len(all_ids),
            "verts": sum(groups[g]["verts"] for g in TARGET_GROUPS),
            "verts_ratio": round(
                sum(groups[g]["verts"] for g in TARGET_GROUPS)
                / src["verts"], 6),
            "kept_shells": src["shells"] - len(all_ids),
        },
        "isolation_opaque_px": iso_px,
        "board": str(BOARD), "board_bytes": BOARD.stat().st_size,
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
    }
    report["ok"] = not report["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for g in TARGET_GROUPS:
        v = groups[g]
        print("GROUP", g, "shells", v["shells"], "verts", v["verts"],
              "z", v["centroid_z_range"], "span", v["max_z_span"])
    print("ISO_PX", iso_px)
    print("COLOR front green/red", color_ratio(gf, "green"),
          color_ratio(gf, "red"), "back blue", color_ratio(gb, "blue"))
    for k, v in checks.items():
        print("CHECK", k, v)
    print("SHELL_TARGETS_B_OK" if report["ok"]
          else "SHELL_TARGETS_B_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
