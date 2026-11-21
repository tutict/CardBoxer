"""侧身格斗站架探针：55° 立绘 A-pose -> 三组格斗站架偏移，出对照板供看图选组。

复用 3D攻击GIF/make_puppet.py 的 13 段分区仿射引擎，但两处口径不同：
  * 源图先水平翻转（见 side_joints.json._flip_why）；
  * 不做正视 retarget，站架偏移本身就是骨局部角，之后动作帧直接叠加
    baked2.json 的「局部相对角差」。

用法：
  <venv>/python.exe make_side_stance.py            # 渲探针 + 对照板
  <venv>/python.exe make_side_stance.py --select S2  # 看图后钉选组
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(BAKE / "3D攻击GIF"))
import make_puppet as P  # noqa: E402
from mesh_warp import MeshWarp  # noqa: E402

JOINTS = HERE / "side_joints.json"
STANCE = HERE / "side_stance.json"
OUT = HERE / "frames" / "stance_probe"
STATS = HERE / "stance_probe.json"


def font(size, bold=False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc") if bold \
        else (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf")
    for p in names:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_TITLE = font(22, True)
F_MID = font(16, True)
F_SM = font(13)
BG = (232, 236, 244, 255)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rad(d):
    return math.radians(d)


def stance_delta(cfg):
    t = cfg["torso_deg"]
    return {
        "hips": 0.0,
        "spine": rad(t),
        "chest": 0.0,
        "neck": 0.0,
        "head": rad(-t * cfg["head_comp"]),
        "upperarm_f": rad(cfg["f_upper"]),
        "forearm_f": rad(cfg["f_fore"]),
        "upperarm_b": rad(cfg["b_upper"]),
        "forearm_b": rad(cfg["b_fore"]),
        "thigh_f": rad(cfg["thigh_f"]),
        "shin_f": rad(cfg["shin_f"]),
        "thigh_b": rad(cfg["thigh_b"]),
        "shin_b": rad(cfg["shin_b"]),
    }


def build_masks_safe(ap_pts, W, H, far_px):
    """V2 分区：离所有骨段都太远的像素判为「附属物」，归 hips 恒等层。

    V1 直接复用 P.build_masks 的「最近骨段」规则，长发 / 披风 / 长衫下摆
    离 13 段都超过 100px，却仍被硬分给 upperarm_b / forearm_b，于是跟着
    手臂变换飞出去，看图就是悬浮黑发片与被水平切开的头。
    这里只按几何距离判定（不按部位名字列白名单）：超过 far_px 的像素
    归到 hips；站架与所有动作帧里 hips 的 delta 恒 0，变换为恒等，
    这些像素原地不动，连续结构因此保住。
    """
    segs = [(ap_pts[u], ap_pts[v]) for _n, _p, u, v in P.CHAIN]
    hips_idx = next(i for i, (n, _p, _u, _v) in enumerate(P.CHAIN) if n == "hips")
    far2 = far_px * far_px
    labels = bytearray(W * H)
    far_count = 0
    for y in range(H):
        row = y * W
        for x in range(W):
            best, bestd = 0, 1e30
            for bi, ((ax, ay), (bx, by)) in enumerate(segs):
                dx, dy = bx - ax, by - ay
                den = dx * dx + dy * dy
                t = ((x - ax) * dx + (y - ay) * dy) / den if den > 1e-9 else 0.0
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                ex, ey = x - (ax + t * dx), y - (ay + t * dy)
                d = ex * ex + ey * ey
                if d < bestd:
                    bestd, best = d, bi
            if bestd > far2:
                labels[row + x] = hips_idx
                far_count += 1
            else:
                labels[row + x] = best
    raw = bytes(labels)
    masks = {}
    for bi, (name, _p, _u, _v) in enumerate(P.CHAIN):
        table = bytes(255 if i == bi else 0 for i in range(256))
        m = Image.frombytes("L", (W, H), raw.translate(table))
        masks[name] = m.filter(ImageFilter.MaxFilter(3))
    counts = [raw.count(i) for i in range(len(P.CHAIN))]
    return masks, counts, far_count


def alpha_count(im: Image.Image, box) -> int:
    a = im.getchannel("A").crop(box)
    return sum(a.histogram()[17:])


def diff_px(a: Image.Image, b: Image.Image, threshold=18) -> int:
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    return sum(d.histogram()[threshold + 1:])


def flat(im: Image.Image) -> Image.Image:
    return Image.alpha_composite(Image.new("RGBA", im.size, BG), im).convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", choices=["S1", "S2", "S3"])
    args = ap.parse_args()

    cfg_all = json.loads(STANCE.read_text(encoding="utf-8"))
    if args.select:
        cfg_all["selected"] = args.select
        cfg_all["_selected_after_review"] = (
            f"看图 站架三档对照.png 后选定 {args.select}；理由见 侧身战斗-验证记录.txt")
        STANCE.write_text(json.dumps(cfg_all, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        print(f"STANCE_SELECTED {args.select}")
        return 0

    spec = json.loads(JOINTS.read_text(encoding="utf-8"))
    assert spec["flip_source_horizontally"] is True
    px_per_game = spec["camera"]["px_per_game_px"]
    guard = tuple(cfg_all["guard_zone"])
    cands = cfg_all["candidates"]
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"sources": {}, "candidates": {}, "guard_zone": list(guard),
              "far_px": cfg_all["far_px"],
              "warp_rule": "MeshWarp shared-vertex displacement field (PIL MESH)"}

    for tag in ("player", "foe"):
        src_path = BAKE / spec["source_images"][tag]
        src = Image.open(src_path).convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
        assert src.size == (768, 768)
        src_alpha = src.getchannel("A")
        apose = {k: tuple(v) for k, v in spec[tag].items()}
        ap_pts = P.make_points(apose, px_per_game)
        # V2 的 13 分块版保留在 build_masks_safe 里作对照；V3 起改用
        # 共享顶点的连续网格位移场，消除分区边界的白色楔形裂缝。
        warp = MeshWarp(ap_pts, P.CHAIN, 768, 768, cell=24,
                        far_px=cfg_all["far_px"])
        counts = [0] * len(P.CHAIN)
        far_count = warp.far_vertices
        extras = {n: (1.0, 0.0, 0.0) for n, _p, _u, _v in P.CHAIN}
        zero = {n: 0.0 for n, _p, _u, _v in P.CHAIN}
        mats0 = P.matrices_for(zero, (0.0, 0.0), ap_pts, extras)
        assert all(abs(mats0[n][i][j] - (1.0 if i == j else 0.0)) < 1e-9
                   for n in mats0 for i in range(2) for j in range(2)), \
            "zero delta must be identity"

        base = src.copy()
        base.save(OUT / f"{tag}-A-pose.png")
        report["sources"][tag] = {
            "path": str(src_path.relative_to(BAKE)).replace("\\", "/"),
            "sha256": sha(src_path),
            "flipped_png_sha256": sha(OUT / f"{tag}-A-pose.png"),
            "alpha_bbox": list(src_alpha.getbbox()),
            "mesh_grid_count": warp.grid_count,
            "mesh_far_vertices": far_count,
            "mesh_cell_px": warp.cell,
            "source_pixel_identical_to_flipped": True,
        }
        print(f"[{tag}] mesh_grid={warp.grid_count} far_vertices={far_count}",
              flush=True)

        for key, cfg in cands.items():
            delta = stance_delta(cfg)
            mats = P.matrices_for(delta, (0.0, 0.0), ap_pts, extras)
            im = warp.warp(src, mats)
            path = OUT / f"{tag}-{key}.png"
            im.save(path)
            entry = {
                "file": path.name,
                "sha256": sha(path),
                "bytes": path.stat().st_size,
                "alpha_bbox": list(im.getchannel("A").getbbox()),
                "alpha_pixels": alpha_count(im, (0, 0, 768, 768)),
                "guard_zone_alpha": alpha_count(im, guard),
                "diff_px_vs_A_pose": diff_px(flat(base), flat(im)),
                "max_abs_delta_deg": round(max(abs(math.degrees(v))
                                               for v in delta.values()), 3),
                "config": cfg,
            }
            report["candidates"].setdefault(key, {})[tag] = entry
            print(f"[{tag}/{key}] guard={entry['guard_zone_alpha']} "
                  f"diff={entry['diff_px_vs_A_pose']} "
                  f"bbox={entry['alpha_bbox']} maxdeg={entry['max_abs_delta_deg']}",
                  flush=True)

    # 对照板：4 列（A-pose / S1 / S2 / S3）× 2 行（玩家 / 对手）
    CW = 260
    cols = [("A-pose", "原始 A-pose（翻转后）")] + \
           [(k, f"{k} · {cands[k]['label']}偏移") for k in cands]
    left, label_w, gap, top = 20, 100, 16, 104
    board = Image.new("RGB", (label_w + len(cols) * CW + (len(cols) - 1) * gap + left,
                              top + 2 * (CW + 44) + 20), (22, 25, 36))
    d = ImageDraw.Draw(board)
    d.text((left, 12), "《牌拳》侧身格斗站架探针 · 55° 立绘 A-pose → 格斗预备式",
           font=F_TITLE, fill=(238, 242, 252))
    d.text((left, 44),
           "观察项：① 双拳是否抬到下颌前护脸  ② 上身是否前倾收腰  ③ 前后脚是否分开、脚是否仍贴地",
           font=F_SM, fill=(160, 170, 190))
    d.text((left, 68), "源图已水平翻转（角色朝右 = 游戏 +x），与 baked2.json 侧视语义同向",
           font=F_SM, fill=(150, 226, 246))
    for ci, (_key, label) in enumerate(cols):
        x = label_w + ci * (CW + gap)
        d.text((x + 4, top - 24), label, font=F_MID, fill=(240, 214, 160))
    for ri, tag in enumerate(("player", "foe")):
        y = top + ri * (CW + 44)
        d.text((8, y + CW // 2 - 10), "玩家 V4b" if tag == "player" else "对手怪 V1",
               font=F_MID, fill=(196, 206, 224))
        for ci, (key, _label) in enumerate(cols):
            x = label_w + ci * (CW + gap)
            name = f"{tag}-A-pose.png" if key == "A-pose" else f"{tag}-{key}.png"
            im = flat(Image.open(OUT / name).convert("RGBA"))
            board.paste(im.resize((CW, CW), Image.LANCZOS), (x, y))
            e = None if key == "A-pose" else report["candidates"][key][tag]
            txt = "基准" if e is None else \
                f"护脸区 {e['guard_zone_alpha']} px · 差异 {e['diff_px_vs_A_pose']} px"
            d.text((x + 4, y + CW + 4), txt, font=F_SM, fill=(160, 170, 190))
    board.save(HERE / "站架三档对照.png")
    report["board"] = "站架三档对照.png"
    report["board_sha256"] = sha(HERE / "站架三档对照.png")
    STATS.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print("STANCE_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
