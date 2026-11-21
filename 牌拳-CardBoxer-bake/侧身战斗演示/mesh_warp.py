"""连续网格位移场：用 PIL MESH 做骨骼驱动的图像变形，消除分块仿射的裂缝。

V1/V2 的做法是 13 个刚性分区各自 AFFINE 变换再 alpha 合成。相邻分区
变换差几十度时，边界必然出现白色楔形缺口 / 悬浮三角（对手怪头部被
水平切开、披风被挖空、玩家下摆横缝）。MaxFilter 扩 1px 盖不住。

这里改成：规则网格的每个**顶点**按「最近两段骨的位移混合」求一个
连续位移场，再用 Image.Transform.MESH 把每个格子映射成四边形。
相邻格子共享同一个顶点位移，四边形边界严丝合缝 -> 不会有裂缝。

口径与 V2 一致（不是新一套动作语义）：
  * 离所有骨段 > far_px 的像素判为附属物，位移取 hips（delta 恒 0，
    只剩 root 平移），所以长发 / 披风 / 下摆只跟着整体走，不被拉碎；
  * 骨段内部刚性、边界 blend_px 内两骨混合，避免橡皮人；
  * far_px 附近 fade_px 平滑衰减，避免位移场跳变。

MESH 的 quad 是「源图坐标」，bbox 是目标矩形。用位移场的一阶逆近似
quad = p - d(p)；变形幅度不大时误差是二阶，且逐顶点连续。

纯 PIL，无 numpy。运行解释器：Fantasy-Agent/.venv/Scripts/python.exe
"""
from __future__ import annotations

from PIL import Image


def apply(M, p):
    x, y = p
    return (M[0][0] * x + M[0][1] * y + M[0][2],
            M[1][0] * x + M[1][1] * y + M[1][2])


def seg_dist2(px, py, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    den = dx * dx + dy * dy
    t = ((px - ax) * dx + (py - ay) * dy) / den if den > 1e-9 else 0.0
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    ex, ey = px - (ax + t * dx), py - (ay + t * dy)
    return ex * ex + ey * ey


class MeshWarp:
    def __init__(self, ap_pts, chain, W=768, H=768, cell=24,
                 blend_px=14.0, far_px=90.0, fade_px=28.0):
        self.W, self.H, self.cell = W, H, cell
        self.names = [n for n, _p, _u, _v in chain]
        self.segs = [(ap_pts[u], ap_pts[v]) for _n, _p, u, v in chain]
        self.xs = list(range(0, W, cell)) + ([W] if W % cell else [W])
        self.ys = list(range(0, H, cell)) + ([H] if H % cell else [H])
        # 去重（W 能被 cell 整除时末尾会重复）
        if self.xs[-1] == self.xs[-2]:
            self.xs.pop()
        if self.ys[-1] == self.ys[-2]:
            self.ys.pop()
        self.vertex = {}
        self.far_vertices = 0
        for j, y in enumerate(self.ys):
            for i, x in enumerate(self.xs):
                ds = sorted((seg_dist2(x, y, a, b), k)
                            for k, (a, b) in enumerate(self.segs))
                d0, i0 = ds[0]
                d1, i1 = ds[1]
                r0, r1 = d0 ** 0.5, d1 ** 0.5
                if r0 > far_px:
                    self.vertex[(i, j)] = None
                    self.far_vertices += 1
                    continue
                t = min(1.0, max(0.0, (r1 - r0) / blend_px))
                w0, w1 = 0.5 + 0.5 * t, 0.5 - 0.5 * t
                fade = min(1.0, max(0.0, (far_px - r0) / fade_px))
                self.vertex[(i, j)] = (i0, i1, w0, w1, fade)
        self.grid_count = (len(self.xs) - 1) * (len(self.ys) - 1)

    def displacement(self, i, j, mats):
        x, y = self.xs[i], self.ys[j]
        info = self.vertex[(i, j)]
        if info is None:
            mx, my = apply(mats["hips"], (x, y))
            return (mx - x, my - y)
        i0, i1, w0, w1, fade = info
        out = [0.0, 0.0]
        for w, idx in ((w0, i0), (w1, i1)):
            if w <= 0.0:
                continue
            mx, my = apply(mats[self.names[idx]], (x, y))
            out[0] += w * (mx - x)
            out[1] += w * (my - y)
        return (out[0] * fade, out[1] * fade)

    def warp(self, src: Image.Image, mats) -> Image.Image:
        disp = {}
        for j, y in enumerate(self.ys):
            for i, x in enumerate(self.xs):
                disp[(i, j)] = self.displacement(i, j, mats)
        mesh = []
        for j in range(len(self.ys) - 1):
            for i in range(len(self.xs) - 1):
                bbox = (self.xs[i], self.ys[j], self.xs[i + 1], self.ys[j + 1])
                ul, ll = disp[(i, j)], disp[(i, j + 1)]
                lr, ur = disp[(i + 1, j + 1)], disp[(i + 1, j)]
                x0, y0, x1, y1 = bbox
                # PIL QUAD 顺序：左上、左下、右下、右上（源图坐标）
                quad = (x0 - ul[0], y0 - ul[1],
                        x0 - ll[0], y1 - ll[1],
                        x1 - lr[0], y1 - lr[1],
                        x1 - ur[0], y0 - ur[1])
                mesh.append((bbox, quad))
        return src.transform((self.W, self.H), Image.Transform.MESH, mesh,
                             resample=Image.BICUBIC)
