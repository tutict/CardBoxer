"""侧身角色逐帧动作帧：站架 S2 + baked2.json 侧视原始角度差（局部相对角差）。

与 3d-attack-gifs/make_puppet.py 的三点差别：
  1. 源图 55° 侧视 + 水平翻转，与动作表同向，不做正视 retarget；
  2. 每根骨拿「相对父骨」的局部角差，hips 强制 0，消除三重累积；
  3. 用 mesh_warp.MeshWarp 的共享顶点连续位移场，而不是 13 个分块
     各自仿射（后者会把头/披风/下摆撕出白色楔形缺口）。

站架帧必须与 make_side_stance.py 选出的 S2 探针 PNG 逐字节一致，
这是「站架偏移来源」最硬的承重判据。

用法： <venv>/python.exe make_side_frames.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(HERE))
import make_side_stance as S  # noqa: E402

P = S.P
MeshWarp = S.MeshWarp
JOINTS = HERE / "side_joints.json"
STANCE = HERE / "side_stance.json"
ACTION = HERE / "side_action.json"
TABLE = BAKE / "baked2.json"
CARDS = ("jab", "cross", "wave")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def clamp(v, cap):
    return max(-cap, min(cap, v))


def action_delta(frame_j, stance_j, cfg):
    """侧视动作表 -> 骨局部相对角差（弧度），返回 (delta, diagnostics)。"""
    fp = P.make_points(frame_j, 1.0)
    sp = P.make_points(stance_j, 1.0)
    world = {n: math.degrees(P.wrap_pi(
        P.angle(fp[u], fp[v]) - P.angle(sp[u], sp[v])))
        for n, _p, u, v in P.CHAIN}
    caps, gain = cfg["caps_deg"], cfg["gain"]
    out, capped = {}, []
    for n, parent, _u, _v in P.CHAIN:
        if n == "hips":
            raw = 0.0
        else:
            pw = 0.0 if parent in (None, "hips") else world[parent]
            raw = wrap_deg(world[n] - pw)
        used = clamp(raw * gain, caps[n])
        if abs(raw * gain) > caps[n] + 1e-9:
            capped.append(n)
        out[n] = math.radians(used)
    diag = {
        "world_abs_max_deg": round(max(abs(v) for v in world.values()), 3),
        "local_abs_max_deg": round(max(abs(math.degrees(v))
                                       for v in out.values()), 3),
        "capped_bones": sorted(set(capped)),
        "hips_delta_deg": 0.0,
    }
    return out, diag


def main() -> int:
    spec = json.loads(JOINTS.read_text(encoding="utf-8"))
    stance_cfg_all = json.loads(STANCE.read_text(encoding="utf-8"))
    action_cfg = json.loads(ACTION.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    selected = stance_cfg_all["selected"]
    assert selected in stance_cfg_all["candidates"], \
        "run make_side_stance.py --select S1|S2|S3 first"
    s_cfg = stance_cfg_all["candidates"][selected]
    assert spec["flip_source_horizontally"] is True
    px = spec["camera"]["px_per_game_px"]
    stance_j = P.joints_of(table, None, 0)
    s_delta = S.stance_delta(s_cfg)
    t0 = time.time()

    report = {
        "driver": "side-view 55deg portrait + shared-vertex mesh warp, "
                  "local-relative FK deltas from baked2.json",
        "stance_selected": selected,
        "stance_config": s_cfg,
        "stance_sha256": sha(STANCE.read_bytes()),
        "action_sha256": sha(ACTION.read_bytes()),
        "joints_sha256": sha(JOINTS.read_bytes()),
        "table_sha256": sha(TABLE.read_bytes()),
        "flip_source_horizontally": True,
        "px_per_game_px": px,
        "gain": action_cfg["gain"],
        "root_gain": action_cfg["root_gain"],
        "caps_deg": action_cfg["caps_deg"],
        "tags": {},
    }

    for tag in ("player", "foe"):
        src_path = BAKE / spec["source_images"][tag]
        src = Image.open(src_path).convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
        assert src.size == (768, 768)
        apose = {k: tuple(v) for k, v in spec[tag].items()}
        ap_pts = P.make_points(apose, px)
        warp = MeshWarp(ap_pts, P.CHAIN, 768, 768, cell=24,
                        far_px=stance_cfg_all["far_px"])
        extras = {n: (1.0, 0.0, 0.0) for n, _p, _u, _v in P.CHAIN}
        outdir = HERE / "frames" / tag
        outdir.mkdir(parents=True, exist_ok=True)

        shots = [("stance", None, 0)]
        for cid in CARDS:
            shots.extend((cid, cid, f) for f in range(int(table["cards"][cid]["frames"])))
        manifest = []
        for label, card, frame in shots:
            j = P.joints_of(table, card, frame)
            act, diag = action_delta(j, stance_j, action_cfg) if card else \
                ({n: 0.0 for n, _p, _u, _v in P.CHAIN},
                 {"world_abs_max_deg": 0.0, "local_abs_max_deg": 0.0,
                  "capped_bones": [], "hips_delta_deg": 0.0})
            total = {n: s_delta[n] + act[n] for n in s_delta}
            rg = action_cfg["root_gain"]
            root = ((j["hip"][0] - stance_j["hip"][0]) * px * rg,
                    (j["hip"][1] - stance_j["hip"][1]) * px * rg)
            mats = P.matrices_for(total, root, ap_pts, extras)
            im = warp.warp(src, mats)
            path = outdir / f"{label}_f{frame:03d}.png"
            im.save(path)
            png = path.read_bytes()
            payload = json.dumps({k: list(v) for k, v in sorted(j.items())},
                                 sort_keys=True)
            entry = {
                "file": path.name, "label": label, "card": card, "frame": frame,
                "phase": "stance" if card is None
                         else table["cards"][card]["track"][frame]["phase"],
                "joints_sha256": sha(payload.encode()),
                "png_sha256": sha(png), "bytes": len(png),
                "root_delta_px": [round(root[0], 3), round(root[1], 3)],
                "stance_abs_max_deg": round(max(abs(math.degrees(v))
                                                for v in s_delta.values()), 3),
                "action_diag": diag,
                "total_abs_max_deg": round(max(abs(math.degrees(v))
                                               for v in total.values()), 3),
            }
            if card is None:
                probe = HERE / "frames" / "stance_probe" / f"{tag}-{selected}.png"
                same = sha(probe.read_bytes()) == sha(png)
                entry["stance_matches_selected_probe"] = bool(same)
                print(f"[{tag}] STANCE_MATCH_{selected} identical={same}", flush=True)
                assert same, "stance frame must equal the selected probe PNG byte-for-byte"
            manifest.append(entry)
            if frame == 0 or (card and frame in (7, 13, 18, 21, 35)):
                print(f"[{tag}] {path.name} root={entry['root_delta_px']} "
                      f"world_max={diag['world_abs_max_deg']}deg "
                      f"local_max={diag['local_abs_max_deg']}deg "
                      f"capped={len(diag['capped_bones'])}", flush=True)

        report["tags"][tag] = {
            "source_image": str(src_path.relative_to(BAKE)).replace("\\", "/"),
            "source_sha256": sha(src_path.read_bytes()),
            "mesh_grid_count": warp.grid_count,
            "mesh_far_vertices": warp.far_vertices,
            "frames": len(manifest),
            "cards": {c: int(table["cards"][c]["frames"]) for c in CARDS},
            "manifest": manifest,
        }
        (outdir / "manifest.json").write_text(
            json.dumps(report["tags"][tag], ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"[{tag}] SIDE_FRAMES_OK frames={len(manifest)}", flush=True)

    report["elapsed_seconds"] = round(time.time() - t0, 2)
    (HERE / "side_frames.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SIDE_FRAMES_ALL_OK elapsed={report['elapsed_seconds']}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
