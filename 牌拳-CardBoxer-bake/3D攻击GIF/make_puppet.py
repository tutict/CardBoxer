"""用真实 3D 渲染立绘 + 游戏动作表做 2D 骨骼 puppet 攻击帧（纯 PIL，无 numpy）。

为什么不是「直接驱动 3D 网格」：
  AI 生成的模型是 A-pose / 0 skins / 数千个开放薄壳，
  13 骨按「格斗站架骨段」刚性赋权后一动就撕成碎片
  （实测 64,024/64,024 顶点全动、平均位移 0.269 m，见 驱动探针-对手怪.png）。
  C 路线进引擎的本来就是 2D 精灵 PNG，所以这里在**图像空间**做骨骼变形：
  保留 3D 立绘的全部外观细节，动作仍来自 baked2.json 的 11 关节逐帧表。

变换口径（不是目测摆姿势）：
  * 每根骨的本地旋转增量 delta = 该骨段在「当前帧」的方向角 - 在「站架」的方向角；
  * 绕该骨段在 A-pose 立绘上的头端旋转，父变换左乘，形成层级链；
  * 根骨额外叠加 (F.hip - S.hip) 的整体位移，1 game px = 768/2.30/100 px；
  * 站架帧所有 delta=0，输出与原始立绘逐像素一致（最硬的承重判据）。

运行解释器：Fantasy-Agent/.venv/Scripts/python.exe（本机唯一有 Pillow 的）。
用法：
  python make_puppet.py --tag player --probe
  python make_puppet.py --tag player --cards jab,cross,wave
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
TABLE = BAKE / "baked2.json"
SPEC = HERE / "apose_joints.json"
JOINTS = ("hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow",
          "b_hand", "f_knee", "f_foot", "b_knee", "b_foot")

# name, parent, head point, tail point —— 与 boxer_rig.BONES / boxer_3d.chain_of 同构
CHAIN = [
    ("hips", None, "A", "B"),
    ("spine", "hips", "B", "C"),
    ("chest", "spine", "C", "D"),
    ("neck", "chest", "D", "E"),
    ("head", "neck", "E", "F"),
    ("upperarm_f", "chest", "D", "f_elbow"),
    ("forearm_f", "upperarm_f", "f_elbow", "f_hand"),
    ("upperarm_b", "chest", "D", "b_elbow"),
    ("forearm_b", "upperarm_b", "b_elbow", "b_hand"),
    ("thigh_f", "hips", "tf_head", "f_knee"),
    ("shin_f", "thigh_f", "f_knee", "f_foot"),
    ("thigh_b", "hips", "tb_head", "b_knee"),
    ("shin_b", "thigh_b", "b_knee", "b_foot"),
]
# 远层先画、近层后画；b = 后侧（画面左），f = 前侧（画面右）
DRAW_ORDER = ["shin_b", "thigh_b", "forearm_b", "upperarm_b",
              "hips", "spine", "chest", "neck", "head",
              "thigh_f", "shin_f", "upperarm_f", "forearm_f"]


def log(*a):
    print(*a, flush=True)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def make_points(j: dict, px_per_game: float = 1.0):
    hip, sh, hd = j["hip"], j["shoulder"], j["head"]
    return {
        "A": hip, "B": lerp(hip, sh, 0.26), "C": lerp(hip, sh, 0.60),
        "D": sh, "E": lerp(sh, hd, 0.58), "F": hd,
        "f_elbow": j["f_elbow"], "f_hand": j["f_hand"],
        "b_elbow": j["b_elbow"], "b_hand": j["b_hand"],
        "f_knee": j["f_knee"], "f_foot": j["f_foot"],
        "b_knee": j["b_knee"], "b_foot": j["b_foot"],
        "tf_head": (hip[0] + 4.0 * px_per_game, hip[1]),
        "tb_head": (hip[0] - 4.0 * px_per_game, hip[1]),
    }


def angle(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])


def wrap_pi(a):
    """把角度差夹到 (-pi, pi]。

    atan2 的两帧角度都落在 ±pi，跨过分支切线时直接相减会得到 ±2pi 附近的值；
    实测 jab 第 7 帧曾算出 310 度的「旋转增量」，实际只是 -50 度。
    不夹住的话整条手臂会绕肩膀转大半圈。
    """
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def joints_of(table, card, frame):
    if card is None:
        return {k: tuple(v) for k, v in table["stance"].items()}
    tracks = table["cards"] if card in table["cards"] else table["motions"]
    return {k: tuple(tracks[card]["track"][frame][k]) for k in JOINTS}


# --- 3x3 仿射矩阵（纯 Python；最后一列是平移） ----------------------------
def mm(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def mT(x, y):
    return [[1.0, 0.0, x], [0.0, 1.0, y], [0.0, 0.0, 1.0]]


def mR(theta):
    c, s = math.cos(theta), math.sin(theta)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def mS(s):
    return [[s, 0.0, 0.0], [0.0, s, 0.0], [0.0, 0.0, 1.0]]


def local_transform(pivot, theta, scale, dx, dy):
    """绕 pivot 旋转+缩放，再整体平移；用于「出拳朝镜头」的 2D 透视压缩。"""
    about = mm(mm(mT(pivot[0], pivot[1]), mm(mR(theta), mS(scale))),
               mT(-pivot[0], -pivot[1]))
    return mm(mT(dx, dy), about)


def rot_about(p, theta):
    return mm(mm(mT(p[0], p[1]), mR(theta)), mT(-p[0], -p[1]))


def inv3(M):
    a, b, c = M[0]
    d, e, f = M[1]
    det = a * e - b * d
    assert abs(det) > 1e-12, "singular affine"
    return [[e / det, -b / det, (b * f - c * e) / det],
            [-d / det, a / det, (c * d - a * f) / det],
            [0.0, 0.0, 1.0]]


def clamp(v, cap):
    return max(-cap, min(cap, v))


def retarget(frame_j, stance_j, mapping):
    """侧视动作表 -> 正视立绘的显式重定向，返回 (mapped_delta, raw_delta, signals)。

    时间曲线与强度全部来自 baked2.json 逐帧关节，不手工摆关键帧：
      * 躯干：hip->shoulder 方向差，只给 spine 一次，clamp 到可读侧倾；
        hips/chest 固定 0，避免同一角度在层级里被累积三次（实测 27.18*3）。
      * 头：反向补偿，身体侧倾时头基本保持竖直。
      * 两臂：用各自 hand 相对站架的位移幅度做 0..1 强度，按正视抬臂方向旋转；
        另给双手合计幅度一个 wave 信号，让气功波读成双掌前推。
      * 两腿：沿用原始逐骨角度差但 clamp，正面只暗示重心变化。
    """
    fp = make_points(frame_j, 1.0)
    sp = make_points(stance_j, 1.0)
    raw = {n: math.degrees(wrap_pi(angle(fp[u], fp[v]) - angle(sp[u], sp[v])))
           for n, _p, u, v in CHAIN}
    torso = math.degrees(wrap_pi(angle(fp["A"], fp["D"]) - angle(sp["A"], sp["D"])))
    torso_used = clamp(torso * mapping["torso_gain"], mapping["torso_cap_deg"])
    mf = math.dist(frame_j["f_hand"], stance_j["f_hand"])
    mb = math.dist(frame_j["b_hand"], stance_j["b_hand"])
    tf = min(1.0, mf / mapping["reach_norm_px"])
    tb = min(1.0, mb / mapping["reach_norm_px"])
    # 双手信号只在两只手同时离开站架时触发；用 min 而不是 sum，
    # 否则 jab 的单手 80 px 会误把另一只手也抬起来（v1 实测看图翻车）。
    tw = min(1.0, min(mf, mb) / mapping["wave_min_norm_px"]) * mapping["wave_arm_weight"]
    af = max(tf, tw)
    ab = max(tb, tw)
    g = mapping["arm_gain_deg"]
    cap = mapping["leg_cap_deg"]
    delta = {
        "hips": 0.0,
        "spine": math.radians(torso_used),
        "chest": 0.0,
        "neck": 0.0,
        "head": math.radians(-torso_used * mapping["head_compensation"]),
        "upperarm_f": math.radians(-g["f_upper"] * af),
        "forearm_f": math.radians(-g["f_fore"] * af),
        "upperarm_b": math.radians(g["b_upper"] * ab),
        "forearm_b": math.radians(g["b_fore"] * ab),
        "thigh_f": math.radians(clamp(raw["thigh_f"], cap)),
        "shin_f": math.radians(clamp(raw["shin_f"], cap)),
        "thigh_b": math.radians(clamp(raw["thigh_b"], cap)),
        "shin_b": math.radians(clamp(raw["shin_b"], cap)),
    }
    sg, dxy, dyy = (mapping["push_scale_gain"], mapping["push_dx_px"],
                    mapping["push_dy_px"])
    extras = {n: (1.0, 0.0, 0.0) for n, _p, _u, _v in CHAIN}
    extras["forearm_f"] = (1.0 + sg * af, -dxy * af, dyy * af)
    extras["forearm_b"] = (1.0 + sg * ab, dxy * ab, dyy * ab)
    signals = {"torso_raw_deg": round(torso, 3), "torso_used_deg": round(torso_used, 3),
               "hand_f_mag_px": round(mf, 3), "hand_b_mag_px": round(mb, 3),
               "arm_f": round(af, 4), "arm_b": round(ab, 4),
               "push_scale_f": round(extras["forearm_f"][0], 4),
               "push_scale_b": round(extras["forearm_b"][0], 4),
               "raw_max_abs_deg": round(max(abs(v) for v in raw.values()), 3)}
    return delta, raw, signals, extras


def matrices_for(delta, root, apose_pts, extras):
    base = mT(root[0], root[1])
    out = {}
    for name, parent, u, _v in CHAIN:
        parent_m = base if parent is None else out[parent]
        s, dx, dy = extras[name]
        out[name] = mm(parent_m, local_transform(
            apose_pts[u], delta[name], s, dx, dy))
    return out


# --- 分区：每个像素归到最近的 A-pose 骨段 ----------------------------------
def build_masks(ap_pts, W, H):
    segs = [(ap_pts[u], ap_pts[v]) for _n, _p, u, v in CHAIN]
    labels = bytearray(W * H)
    for y in range(H):
        row = y * W
        for x in range(W):
            best, bestd = 0, 1e30
            for bi, ((ax, ay), (bx, by)) in enumerate(segs):
                dx, dy = bx - ax, by - ay
                den = dx * dx + dy * dy
                t = ((x - ax) * dx + (y - ay) * dy) / den if den > 1e-9 else 0.0
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                ex, ey = x - (ax + t * dx), y - (ay + t * dy)
                d = ex * ex + ey * ey
                if d < bestd:
                    bestd, best = d, bi
            labels[row + x] = best
    raw = bytes(labels)
    masks = {}
    for bi, (name, _p, _u, _v) in enumerate(CHAIN):
        table = bytes(255 if i == bi else 0 for i in range(256))
        m = Image.frombytes("L", (W, H), raw.translate(table))
        # 1 px 外扩，用来盖住相邻块因不同变换产生的接缝
        masks[name] = m.filter(ImageFilter.MaxFilter(3))
    counts = [raw.count(i) for i in range(len(CHAIN))]
    return masks, counts


def render_frame(src, src_alpha, masks, mats, W, H):
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for name in DRAW_ORDER:
        inv = inv3(mats[name])
        coeff = (inv[0][0], inv[0][1], inv[0][2],
                 inv[1][0], inv[1][1], inv[1][2])
        block = src.copy()
        block.putalpha(ImageChops.multiply(src_alpha, masks[name]))
        warped = block.transform((W, H), Image.Transform.AFFINE, coeff,
                                 resample=Image.BICUBIC)
        canvas = Image.alpha_composite(canvas, warped)
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", choices=["player", "foe"], required=True)
    ap.add_argument("--cards", default="jab,cross,wave")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    mapping_path = HERE / "puppet_mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    px_per_game = spec["camera"]["px_per_game_px"]
    apose = {k: tuple(v) for k, v in spec[args.tag].items()}
    ap_pts = make_points(apose, px_per_game)
    stance = joints_of(table, None, 0)

    src_path = BAKE / spec["source_images"][args.tag]
    src = Image.open(src_path).convert("RGBA")
    W, H = src.size
    assert (W, H) == (768, 768), f"unexpected source size {src.size}"
    src_alpha = src.getchannel("A")
    log(f"SRC {src_path.relative_to(BAKE)} size={W}x{H} "
        f"alpha_bbox={src_alpha.getbbox()}")

    t0 = time.time()
    masks, counts = build_masks(ap_pts, W, H)
    log(f"MASKS segments={len(CHAIN)} counts={counts} "
        f"build_seconds={round(time.time() - t0, 2)}")

    if args.probe:
        shots = [("stance", None, 0), ("jab", "jab", 7), ("wave", "wave", 18)]
    else:
        shots = [("stance", None, 0)]
        for cid in args.cards.split(","):
            cid = cid.strip()
            shots.extend((cid, cid, f) for f in range(int(table["cards"][cid]["frames"])))

    outdir = HERE / "frames" / f"puppet_{args.tag}"
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for label, card, frame in shots:
        j = joints_of(table, card, frame)
        delta, raw, signals, extras = retarget(j, stance, mapping)
        root = ((j["hip"][0] - stance["hip"][0]) * px_per_game,
                (j["hip"][1] - stance["hip"][1]) * px_per_game)
        mats = matrices_for(delta, root, ap_pts, extras)
        # 站架 = 所有骨增量、前推与根位移都为 0，复合变换恒等；直接输出未改动的
        # 立绘，不让分块 alpha 合成 / 重采样在无损的那一帧上引入伪差异。
        is_identity = (max(abs(v) for v in delta.values()) < 1e-12
                       and max(abs(s - 1.0) for s, _dx, _dy in extras.values()) < 1e-12
                       and max(abs(v) for v in root) < 1e-12)
        shortcut = card is None or is_identity
        out = src.copy() if shortcut else render_frame(
            src, src_alpha, masks, mats, W, H)
        phase = "stance" if card is None else table["cards"][card]["track"][frame]["phase"]
        path = outdir / f"{label}_f{frame:03d}.png"
        out.save(path)
        png = path.read_bytes()
        payload = json.dumps({k: list(v) for k, v in sorted(j.items())}, sort_keys=True)
        entry = {
            "file": path.name, "label": label, "card": card, "frame": frame,
            "phase": phase, "joints_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "png_sha256": hashlib.sha256(png).hexdigest(), "bytes": len(png),
            "root_delta_px": [round(root[0], 3), round(root[1], 3)],
            "max_abs_delta_deg": round(max(abs(math.degrees(v)) for v in delta.values()), 3),
            "retarget_signals": signals,
            "identity_shortcut": bool(shortcut),
        }
        if card is None:
            identical = out.tobytes() == src.tobytes()
            entry["stance_pixel_identical_to_source"] = bool(identical)
            log(f"STANCE_CHECK identical={identical} identity_matrices={is_identity}")
            assert identical and is_identity, (
                "stance must reproduce the untouched 3D portrait")
        manifest.append(entry)
        log(f"FRAME {path.name} card={card} f={frame} phase={phase} "
            f"root={entry['root_delta_px']} maxdeg={entry['max_abs_delta_deg']} "
            f"bytes={len(png)}")

    report = {
        "driver": "2D skeletal puppet over 3D-rendered RGBA portrait (pure PIL affine)",
        "tag": args.tag,
        "source_image": str(src_path.relative_to(BAKE)).replace("\\", "/"),
        "source_sha256": hashlib.sha256(src_path.read_bytes()).hexdigest(),
        "table": "baked2.json",
        "table_sha256": hashlib.sha256(TABLE.read_bytes()).hexdigest(),
        "spec_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "mapping_sha256": hashlib.sha256(mapping_path.read_bytes()).hexdigest(),
        "mapping": {k: v for k, v in mapping.items() if not k.startswith("_")},
        "apose_joints": {k: list(v) for k, v in apose.items()},
        "px_per_game_px": px_per_game,
        "chain": [{"name": n, "parent": p, "head": u, "tail": v}
                  for n, p, u, v in CHAIN],
        "draw_order": DRAW_ORDER,
        "mask_counts": counts,
        "frames": manifest,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    (outdir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"PUPPET_OK tag={args.tag} frames={len(manifest)} "
        f"elapsed={report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
