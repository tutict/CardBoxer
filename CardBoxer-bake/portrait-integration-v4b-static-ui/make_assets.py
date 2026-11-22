"""制备 8 张透明 PNG，供《牌拳》静态 UI 位接入。

几何常量从可运行工程的 hud.gd 正则现读，不写死数字；复算命令：
  python make_assets.py            # 本脚本每次都会重新读 hud.gd
四视角人物包围盒来自 probe_v4b_assets.json::suggested_subject，统一以
y1=672 为脚底线；所有输出都补到「绘制尺寸」并用底对齐，运行时不再算脚线。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
V4B = BAKE / "3d-model-probe-v4b"
FOE = BAKE / "foe-blender-modeling-v1"
ASSETS = HERE / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

GEO_JSON = json.loads((BAKE / "portrait-integration-preview-v4b" / "probe_v4b_assets.json").read_text(encoding="utf-8"))
SUBJECT = {k: tuple(v) for k, v in GEO_JSON["suggested_subject"].items()}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def source_constants() -> dict[str, float]:
    """从 hud.gd 现读卡牌几何，避免注释里的数字过期。"""
    src = (GAME / "scripts" / "hud.gd").read_text(encoding="utf-8")
    out = {}
    for key in ("CARD_W", "CARD_H", "CARD_GAP", "HAND_Y", "BAR_W"):
        m = re.search(r"const\s+" + key + r"\s*:=\s*([0-9.]+)", src)
        if m is None:
            raise RuntimeError(f"missing const {key} in hud.gd")
        out[key] = float(m.group(1))
    return out


def load_v4b(key: str) -> Image.Image:
    with Image.open(V4B / f"v4b-{key}.png") as src:
        return src.convert("RGBA")


def subject_crop(key: str) -> Image.Image:
    """裁出人物包围盒（头顶 96 / 脚底 672），返回 RGBA。"""
    return load_v4b(key).crop(SUBJECT[key])


def bust(key: str, w: int, h: int, crop_h: int = 250) -> Image.Image:
    """头到腰一段，contain 进目标框。"""
    im = load_v4b(key)
    bb = SUBJECT[key]
    im = im.crop((bb[0], bb[1], bb[2], bb[1] + crop_h))
    return ImageOps.contain(im, (w, h), Image.Resampling.LANCZOS)


def pad_bottom(im: Image.Image, w: int, h: int) -> Image.Image:
    """补到精确绘制尺寸，水平居中 + 底对齐，其余全透明。"""
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(im.convert("RGBA"), ((w - im.width) // 2, h - im.height))
    return out


def portrait_crop_v4b() -> Image.Image:
    """玩家头像母图：1024² 脸特写中心 600² 正方形（沿用预览版已看图确认的口径）。"""
    with Image.open(V4B / "v4b-face-front.png") as src:
        im = src.convert("RGBA")
    cx, cy, side = im.width // 2, im.height // 2, 600
    return im.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2))


def portrait_crop_foe() -> Image.Image:
    """对手怪头像母图：foe-upper.png 是胸像不是脸特写，头（覆面/防毒面具）
    实测在 1024² 画布的 x≈380..640 / y≈20..380，故取以 (512,190) 为中心的
    360² 正方形。这不是「中心 600²」——照抄会把胸甲占满圆框、脸只剩一小条。
    """
    with Image.open(FOE / "foe-upper.png") as src:
        im = src.convert("RGBA")
    cx, cy, side = 512, 190, 360
    im = im.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2))
    # 对手怪是炭黑金属覆面，缩到 40px 又叠在暗色 HUD 上会整块糊成黑饼
    # （资产样张实测）。只提 RGB 明度 + 轻对比，alpha 原样带回来。
    rgb = ImageEnhance.Brightness(im.convert("RGB")).enhance(1.75)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.10)
    out = rgb.convert("RGBA")
    out.putalpha(im.getchannel("A"))
    return out


def circular_avatar(src: Image.Image, size: int = 40) -> Image.Image:
    side = min(src.size)
    src = ImageOps.fit(src, (side, side), Image.Resampling.LANCZOS)
    src = src.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(src, (0, 0), mask)
    return out


def probe_output(path: Path) -> dict:
    with Image.open(path) as src:
        mode = src.mode
        size = list(src.size)
        im = src.convert("RGBA")
    corners = [im.getpixel(p)[3] for p in
               [(0, 0), (size[0] - 1, 0), (0, size[1] - 1), (size[0] - 1, size[1] - 1)]]
    center = im.getpixel((size[0] // 2, size[1] // 2))[3]
    # 单像素中心可能正好落在 55° 侧身剪影的手臂空隙里（实测 card_p55 为 0），
    # 所以用「alpha>8 的像素占比」判非空，而不是一个脆弱的点采样。
    hist = im.getchannel("A").histogram()
    coverage = sum(hist[9:]) / (size[0] * size[1])
    return {
        "file": path.name,
        "size": size,
        "mode": mode,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "alpha_bbox": list(im.getchannel("A").getbbox()),
        "corner_alpha": corners,
        "center_alpha": center,
        "alpha_gt8_pct": round(coverage, 4),
    }


def main() -> None:
    g = source_constants()
    card_w, card_h = int(g["CARD_W"]), int(g["CARD_H"])
    art_w, art_h = card_w - 12, 104          # 与预览版 char_card 的插画区一致
    av = 40
    prof_h = 500
    thumb_w, thumb_h = 196, 258

    jobs: list[tuple[str, Image.Image, str]] = []

    jobs.append(("card_p1.png",
                 pad_bottom(bust("front", art_w, art_h, crop_h=250), art_w, art_h),
                 "v4b-front.png"))
    jobs.append(("card_p55.png",
                 pad_bottom(bust("angle55", art_w, art_h, crop_h=250), art_w, art_h),
                 "v4b-angle55.png"))
    jobs.append(("avatar_player.png", circular_avatar(portrait_crop_v4b(), av),
                 "v4b-face-front.png"))
    jobs.append(("avatar_foe.png", circular_avatar(portrait_crop_foe(), av),
                 "foe-upper.png"))

    front = subject_crop("front")
    big = front.resize((round(front.width * prof_h / front.height), prof_h),
                       Image.Resampling.LANCZOS)
    jobs.append(("profile_front.png", big, "v4b-front.png"))
    for key, name in (("angle25", "profile_25.png"),
                      ("angle55", "profile_55.png"),
                      ("back35", "profile_back35.png")):
        # 半身（头到腰）+ 左右收窄 40px 后 fit 填满竖框：
        # 全身 contain 三个视角几乎一样（样张实测）；纯半身 contain 又会在
        # 竖框顶部留 100px 空档、人物更小。fit 只裁少量左右、顶对齐头部。
        raw = load_v4b(key)
        bb = SUBJECT[key]
        raw = raw.crop((bb[0] + 40, bb[1], bb[2] - 40, bb[1] + 330))
        thumb = ImageOps.fit(raw, (thumb_w, thumb_h), Image.Resampling.LANCZOS,
                             centering=(0.5, 0.0))
        jobs.append((name, thumb, f"v4b-{key}.png"))

    rows = []
    for name, im, source in jobs:
        path = ASSETS / name
        im.save(path, "PNG")
        row = probe_output(path)
        row["source"] = source
        row["source_sha256"] = sha256((V4B if source.startswith("v4b-") else FOE) / source)
        rows.append(row)

    # 四视角脚底线一致性 + 输出健全性
    foot_y = [SUBJECT[k][3] for k in ("front", "angle25", "angle55", "back35")]
    head_y = [SUBJECT[k][1] for k in ("front", "angle25", "angle55", "back35")]
    checks = {
        "all_rgba": all(r["mode"] == "RGBA" for r in rows),
        "all_corners_transparent": all(all(a == 0 for a in r["corner_alpha"]) for r in rows),
        "all_non_empty": all(r["alpha_gt8_pct"] > 0.05 for r in rows),
        "foot_line_672": all(y == 672 for y in foot_y),
        "head_line_96": all(y == 96 for y in head_y),
        "card_art_exact_size": all(r["size"] == [art_w, art_h]
                                   for r in rows if r["file"].startswith("card_")),
        "avatar_exact_size": all(r["size"] == [av, av]
                                 for r in rows if r["file"].startswith("avatar_")),
        "profile_thumb_exact_size": all(r["size"] == [thumb_w, thumb_h]
                                        for r in rows if r["file"] in
                                        ("profile_25.png", "profile_55.png", "profile_back35.png")),
    }

    sil = json.loads((FOE / "silhouette_stats.json").read_text(encoding="utf-8")) \
        if (FOE / "silhouette_stats.json").is_file() else None

    manifest = {
        "note": "静态 UI 位用的透明 PNG；离线 Pillow 制备，非引擎实渲，非动作帧",
        "geometry_from_hud_gd": g,
        "draw_boxes": {
            "card_art": [art_w, art_h],
            "avatar": [av, av],
            "profile_thumb": [thumb_w, thumb_h],
            "profile_front_height": prof_h,
        },
        "subject_boxes": {k: list(v) for k, v in SUBJECT.items()},
        "outputs": rows,
        "checks": checks,
        "checks_all_pass": all(checks.values()),
        "foe_silhouette_stats": sil,
        "foe_silhouette_caveat": (
            "对手怪 V1 剪影体量实测未达标（aspect_bulky_enough=false）；"
            "本轮仍用其真渲染作 HUD 头像，与玩家 V4b 形成配色/覆面对立，"
            "但『宽肩厚躯压过纤细玩家』这一条没有做到，须如实记账。"
        ),
        "recompute": "python make_assets.py  # 每次从 hud.gd 现读几何并重算 sha256",
    }
    (HERE / "assets_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for r in rows:
        print(f"{r['file']:22s} {r['size']} {r['mode']} "
              f"bbox={r['alpha_bbox']} corners={r['corner_alpha']} center_a={r['center_alpha']}")
    print("CHECKS=" + json.dumps(checks, ensure_ascii=False))
    print("ASSETS_OK" if manifest["checks_all_pass"] else "ASSETS_FAILED")


if __name__ == "__main__":
    main()
