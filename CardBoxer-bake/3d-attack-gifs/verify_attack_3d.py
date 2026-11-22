"""3D 攻击 GIF 交付的承重判据。

分三类：
  A. 产物完整性（帧数 / PNG / GIF / 板图）
  B. 链路正确性（逐帧关节来自 baked2.json、站架恒等、重定向语义、角度环绕）
  C. 边界诚实性（真 3D 网格撕裂的量化证伪、两个角色确实是不同 3D 资产、
     游戏源码 0 改动）
每条给 PASS/FAIL，结果写 verify_attack_3d_result.json，有 FAIL 退出 1。
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(HERE))
from make_puppet import (CHAIN, JOINTS, TABLE, joints_of, make_points,  # noqa: E402
                         matrices_for, retarget)

SPEC = HERE / "apose_joints.json"
MAPPING = HERE / "puppet_mapping.json"
BASELINE = BAKE / "combat-motion-design" / "source-baseline.json"
IDS = ["jab", "cross", "wave"]
EXPECT = {"jab": 14, "cross": 22, "wave": 36}
TAGS = ["puppet_player", "puppet_foe", "foe"]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def joint_sha(j):
    payload = json.dumps({k: list(v) for k, v in sorted(j.items())}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 -- 判据自身异常必须算红，不能静默
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    results.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(f"{'PASS' if ok else 'FAIL'} {name}  {detail}", flush=True)
    return ok


def manifests():
    return {tag: json.loads((HERE / "frames" / tag / "manifest.json").read_text(
        encoding="utf-8")) for tag in TAGS}


def frames_dir(tag):
    return HERE / "frames" / tag


# --- A. 产物完整性 ---------------------------------------------------------
def c_frame_counts():
    for tag, m in manifests().items():
        n = len(m["frames"])
        if n != 73:
            return False, f"{tag}: manifest frames={n}, expected 73"
        pngs = list(frames_dir(tag).glob("*_f*.png"))
        if len(pngs) != 73:
            return False, f"{tag}: on-disk png={len(pngs)}"
        for cid in IDS:
            cnt = sum(1 for f in m["frames"] if f["label"] == cid)
            if cnt != EXPECT[cid]:
                return False, f"{tag}/{cid}: {cnt} != {EXPECT[cid]}"
    return True, "3 routes x (1 stance + 14 + 22 + 36) = 219 PNG, all on disk"


def c_png_bytes_hash():
    total = 0
    for tag, m in manifests().items():
        for e in m["frames"]:
            p = frames_dir(tag) / e["file"]
            b = p.read_bytes()
            if b[:8] != b"\x89PNG\r\n\x1a\n" or len(b) < 10000:
                return False, f"bad png {tag}/{e['file']}"
            if sha(b) != e["png_sha256"] or len(b) != e["bytes"]:
                return False, f"hash/size mismatch {tag}/{e['file']}"
            total += 1
    return True, f"{total} PNG: magic + >10KB + sha256 + size all match manifest"


def gif_timeline(path):
    im = Image.open(path)
    total = 0
    for i in range(im.n_frames):
        im.seek(i)
        total += im.info.get("duration", 0)
    return im.n_frames, total


def c_gif_frames():
    """GIF 会合并像素相同的连续帧，但必须把被合并帧的时长累加回去。

    判据不写死「GIF 帧数 == 源帧数」，而是查：
      总播放时长 == 源帧数 x FRAME_MS，且 2 <= 编码帧数 <= 源帧数，
    再与 gif_stats.json 自报的 encoded_frames / duration_sum_ms 双算对账。
    """
    s = json.loads((HERE / "gif_stats.json").read_text(encoding="utf-8"))
    step = s["frame_ms"]
    n, merged = 0, 0
    for key, route in s["routes"].items():
        for cid in IDS:
            rec = route["cards"][cid]
            f = HERE / rec["file"]
            enc, total = gif_timeline(f)
            want = EXPECT[cid] * step
            if total != want:
                return False, f"{key}/{cid}: duration {total}ms != {want}ms"
            if not (2 <= enc <= EXPECT[cid]):
                return False, f"{key}/{cid}: encoded frames={enc} out of range"
            if enc != rec["encoded_frames"] or total != rec["duration_sum_ms"]:
                return False, f"{key}/{cid}: stats/actual mismatch"
            if sha(f.read_bytes()) != rec["sha256"]:
                return False, f"{key}/{cid}: gif sha256 mismatch"
            merged += EXPECT[cid] - enc
            n += 1
        rec = route["combo"]
        f = HERE / rec["file"]
        enc, total = gif_timeline(f)
        want = rec["expected_duration_ms"]
        if total != want or not (2 <= enc <= rec["frames"]):
            return False, f"{key} combo: duration={total}/{want} enc={enc}"
    return (True,
            f"{n} attack GIFs + 3 combos: duration conserved exactly "
            f"(840/1320/2160 ms), {merged} duplicate frames merged with "
            f"duration carried forward")


def c_gif_animated():
    s = json.loads((HERE / "gif_stats.json").read_text(encoding="utf-8"))
    for key, route in s["routes"].items():
        for f in [HERE / route["cards"][c]["file"] for c in IDS]:
            im = Image.open(f)
            if not im.is_animated or im.n_frames < 2:
                return False, f"{f.name}: not animated"
            if im.info.get("loop") != 0:
                return False, f"{f.name}: loop={im.info.get('loop')}"
            if not (im.info.get("duration") or 0) > 0:
                return False, f"{f.name}: duration missing"
    return True, "9 GIFs: is_animated, loop=0, duration>0"


def c_boards():
    files = ["three-routes-impact-frame-overview.png", "player-V4b-motion-timeline.png",
             "three-driver-paths-comparison.png", "player-V4b-keyframe-comparison.png",
             "foe-V1-keyframe-comparison.png", "falsification-mesh-keyframe-comparison.png"]
    for fn in files:
        p = HERE / fn
        if not p.is_file() or p.stat().st_size < 50000:
            return False, f"{fn} missing/too small"
        im = Image.open(p)
        if im.width < 600 or im.height < 400:
            return False, f"{fn} size={im.size}"
    return True, f"{len(files)} boards >=50KB and >=600x400"


# --- B. 链路正确性 ---------------------------------------------------------
def c_joint_hashes():
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    n = 0
    for tag, m in manifests().items():
        for e in m["frames"]:
            card, frame = e["card"], e["frame"]
            j = joints_of(table, card, frame)
            if joint_sha(j) != e["joints_sha256"]:
                return False, f"{tag}/{e['file']}: joint hash != baked2.json"
            n += 1
    return True, f"{n} frames independently recomputed from baked2.json"


def c_stance_untouched():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    for tag in ("player", "foe"):
        m = json.loads((frames_dir(f"puppet_{tag}") / "manifest.json").read_text(
            encoding="utf-8"))
        e = next(x for x in m["frames"] if x["label"] == "stance")
        if not (e.get("stance_pixel_identical_to_source") and e.get("identity_shortcut")):
            return False, f"{tag}: stance flags not set"
        src = Image.open(BAKE / spec["source_images"][tag]).convert("RGBA")
        out = Image.open(frames_dir(f"puppet_{tag}") / e["file"]).convert("RGBA")
        if src.tobytes() != out.tobytes():
            return False, f"{tag}: stance PNG differs from source portrait"
    return True, "both stance PNGs are byte-identical RGBA to the 3D portraits"


def c_stance_matrices_identity():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    stance = joints_of(table, None, 0)
    for tag in ("player", "foe"):
        apose = {k: tuple(v) for k, v in spec[tag].items()}
        pts = make_points(apose, spec["camera"]["px_per_game_px"])
        delta, _raw, _sig, extras = retarget(stance, stance, mapping)
        mats = matrices_for(delta, (0.0, 0.0), pts, extras)
        for name, M in mats.items():
            for i in range(3):
                for k in range(3):
                    want = 1.0 if i == k else 0.0
                    if abs(M[i][k] - want) > 1e-9:
                        return False, f"{tag}/{name}: M[{i}][{k}]={M[i][k]}"
    return True, "26 affine matrices (2 tags x 13 bones) all identity at stance"


def c_single_arm_semantics():
    picks = [("jab", 7, "arm_f", 0.5, "arm_b", 0.0),
             ("cross", 11, "arm_b", 0.9, "arm_f", 0.0)]
    for tag in ("player", "foe"):
        m = json.loads((frames_dir(f"puppet_{tag}") / "manifest.json").read_text(
            encoding="utf-8"))
        for cid, fr, hi_key, hi_min, lo_key, lo_val in picks:
            e = next(x for x in m["frames"] if x["label"] == cid and x["frame"] == fr)
            s = e["retarget_signals"]
            if not (s[hi_key] > hi_min and s[lo_key] == lo_val):
                return False, f"{tag}/{cid}#{fr}: f={s['arm_f']} b={s['arm_b']}"
        e = next(x for x in m["frames"] if x["label"] == "wave" and x["frame"] == 18)
        s = e["retarget_signals"]
        if not (s["arm_f"] > 0 and s["arm_b"] > 0):
            return False, f"{tag}/wave#18 is not two-armed"
    return True, "jab=front only, cross=back only, wave=both (both characters)"


def c_push_active_forearm():
    for tag in ("player", "foe"):
        m = json.loads((frames_dir(f"puppet_{tag}") / "manifest.json").read_text(
            encoding="utf-8"))
        j = next(x for x in m["frames"] if x["label"] == "jab" and x["frame"] == 7)
        c = next(x for x in m["frames"] if x["label"] == "cross" and x["frame"] == 11)
        js, cs = j["retarget_signals"], c["retarget_signals"]
        if not (js["push_scale_f"] > 1.15 and js["push_scale_b"] == 1.0):
            return False, f"{tag}/jab push f={js['push_scale_f']} b={js['push_scale_b']}"
        if not (cs["push_scale_b"] > 1.25 and cs["push_scale_f"] == 1.0):
            return False, f"{tag}/cross push f={cs['push_scale_f']} b={cs['push_scale_b']}"
    return True, "punch perspective applied only to the active forearm"


def c_angle_wrap():
    src = (HERE / "make_puppet.py").read_text(encoding="utf-8")
    if "wrap_pi(angle(fp[u], fp[v])" not in src:
        return False, "wrap_pi is no longer used on raw per-bone angles"
    if "def wrap_pi(a):" not in src or "% (2.0 * math.pi)" not in src:
        return False, "wrap_pi definition altered"
    worst = 0.0
    for tag in ("player", "foe"):
        m = json.loads((frames_dir(f"puppet_{tag}") / "manifest.json").read_text(
            encoding="utf-8"))
        for e in m["frames"]:
            worst = max(worst, e["max_abs_delta_deg"])
    if worst > 40.0:
        return False, f"max mapped bone rotation {worst} deg > 40"
    return True, f"wrap_pi wired in source; worst mapped rotation {worst} deg <= 40"


# --- C. 边界诚实性 ---------------------------------------------------------
def c_mesh_falsified():
    m = json.loads((frames_dir("foe") / "manifest.json").read_text(encoding="utf-8"))
    d = m["deform_probe"]
    if d["vertices"] != 64024 or d["moved_gt_1mm"] != d["vertices"]:
        return False, f"coverage changed: {d}"
    if not (d["mean_displacement_m"] > 0.2 and d["max_displacement_m"] > 0.5):
        return False, f"deform magnitude no longer falsifying: {d}"
    if "rotation only" not in m["driver"]:
        return False, "driver description changed"
    return (True,
            f"64,024/64,024 verts moved, mean={d['mean_displacement_m']} m, "
            f"max={d['max_displacement_m']} m -> rigid-weight route falsified")


def c_sources_distinct():
    a = json.loads((frames_dir("puppet_player") / "manifest.json").read_text(
        encoding="utf-8"))
    b = json.loads((frames_dir("puppet_foe") / "manifest.json").read_text(
        encoding="utf-8"))
    if a["source_image"] == b["source_image"] or a["source_sha256"] == b["source_sha256"]:
        return False, "two puppets resolve to the same source image"
    for m in (a, b):
        p = BAKE / m["source_image"]
        if not p.is_file() or sha(p.read_bytes()) != m["source_sha256"]:
            return False, f"source missing/hash changed: {m['source_image']}"
    if "V4b" not in a["source_image"] or "对手怪" not in b["source_image"]:
        return False, "sources are not the two generated 3D model probes"
    return True, "player V4b + foe V1: distinct 3D-render portraits, sha256 verified"


def c_game_untouched():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    root = Path(base["game_dir"])
    if not root.is_dir():
        return False, f"game dir missing: {root}"
    for rel, want in base["files"].items():
        p = root / rel
        if not p.is_file() or sha(p.read_bytes()) != want["sha256"]:
            return False, f"game source changed: {rel}"
    return True, f"{len(base['files'])} game sources byte-identical to baseline"


def c_spec_consistency():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    for tag in ("player", "foe"):
        m = json.loads((frames_dir(f"puppet_{tag}") / "manifest.json").read_text(
            encoding="utf-8"))
        if m["spec_sha256"] != sha(SPEC.read_bytes()):
            return False, f"{tag}: apose spec sha mismatch"
        if m["mapping_sha256"] != sha(MAPPING.read_bytes()):
            return False, f"{tag}: mapping sha mismatch"
        if m["table_sha256"] != sha(TABLE.read_bytes()):
            return False, f"{tag}: baked2.json sha mismatch"
        if m["chain"] != [{"name": n, "parent": p, "head": u, "tail": v}
                          for n, p, u, v in CHAIN]:
            return False, f"{tag}: chain differs from live CHAIN"
        if m["apose_joints"] != {k: list(v) for k, v in spec[tag].items()}:
            return False, f"{tag}: apose joints differ from spec"
        if m["mapping"] != {k: v for k, v in mapping.items()
                            if not k.startswith("_")}:
            return False, f"{tag}: mapping values differ from live file"
    return True, "spec/mapping/table/chain hashes and values all match live files"


CHECKS = [
    ("frame_counts_exact", c_frame_counts),
    ("png_bytes_and_hash", c_png_bytes_hash),
    ("gifs_timeline_conserved", c_gif_frames),
    ("gifs_animated", c_gif_animated),
    ("boards_nonempty", c_boards),
    ("joint_hashes_recomputed", c_joint_hashes),
    ("stance_is_untouched_portrait", c_stance_untouched),
    ("stance_matrices_identity", c_stance_matrices_identity),
    ("single_arm_semantics", c_single_arm_semantics),
    ("push_only_on_active_forearm", c_push_active_forearm),
    ("angle_wrap_wired_and_bounded", c_angle_wrap),
    ("mesh_deform_falsified", c_mesh_falsified),
    ("sources_are_distinct_3d_assets", c_sources_distinct),
    ("game_sources_untouched", c_game_untouched),
    ("spec_mapping_table_consistency", c_spec_consistency),
]


def main():
    for name, fn in CHECKS:
        check(name, fn)
    red = [r["name"] for r in results if not r["ok"]]
    verdict = "ATTACK_3D_VERIFIED" if not red else "ATTACK_3D_FAILED"
    print(f"\n{len(results) - len(red)}/{len(results)} PASS  red={red}  {verdict}",
          flush=True)
    (HERE / "verify_attack_3d_result.json").write_text(json.dumps({
        "verdict": verdict, "passed": len(results) - len(red),
        "total": len(results), "red": red, "checks": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not red else 1


if __name__ == "__main__":
    sys.exit(main())
