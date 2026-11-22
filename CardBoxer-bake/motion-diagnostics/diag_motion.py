"""《牌拳》角色动作现状诊断（纯读盘 + 纯计算，不改任何文件）。

复算 rig_driver.gd::retarget_delta 的同一套公式，量化 3D 侧 72 帧
每根骨头的实际角度范围；再对照 2D 侧 228 帧动作表与 resolve 节奏时钟，
算出「3D 角色在一回里到底动了几秒、哪些状态完全不动」。

用法：python diag_motion.py
输出：data/motion_diagnosis.json
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
OUT = HERE / "data" / "motion_diagnosis.json"

MOTION = GAME / "data" / "motion_input.json"
MOTION_FOE = GAME / "data" / "motion_input_foe.json"
CARD_MOTION = GAME / "data" / "card_motion.json"
RHYTHM = GAME / "scripts" / "battle_rhythm.gd"
LAYER = GAME / "scripts" / "fighter_3d_layer.gd"
ARENA = GAME / "scripts" / "arena.gd"
DRIVER = GAME / "scripts" / "rig_driver.gd"

REVEAL_S = 1.5  # arena.gd 的 reveal 阶段时长（设计说明与源码一致）


def lerp2(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def angle(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])


def wrap_pi(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def make_points(j):
    hip, sh, hd = j["hip"], j["shoulder"], j["head"]
    return {
        "A": hip,
        "B": lerp2(hip, sh, 0.26),
        "C": lerp2(hip, sh, 0.60),
        "D": sh,
        "E": lerp2(sh, hd, 0.58),
        "F": hd,
        "f_elbow": j["f_elbow"], "f_hand": j["f_hand"],
        "b_elbow": j["b_elbow"], "b_hand": j["b_hand"],
        "f_knee": j["f_knee"], "f_foot": j["f_foot"],
        "b_knee": j["b_knee"], "b_foot": j["b_foot"],
        "tf_head": (hip[0] + 4.0, hip[1]),
        "tb_head": (hip[0] - 4.0, hip[1]),
    }


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def retarget_delta(frame_j, stance_j, chain, mapping, stance_points):
    """与 rig_driver.gd:107-146 逐字同公式，返回 (delta_deg, raw_deg)。"""
    fp = make_points(frame_j)
    raw = {}
    for e in chain:
        n, _parent, u, v = e[0], e[1], e[2], e[3]
        raw[n] = math.degrees(wrap_pi(
            angle(fp[u], fp[v]) - angle(stance_points[u], stance_points[v])))
    torso = math.degrees(wrap_pi(
        angle(fp["A"], fp["D"]) - angle(stance_points["A"], stance_points["D"])))
    cap = float(mapping["torso_cap_deg"])
    used = max(-cap, min(cap, torso * float(mapping["torso_gain"])))
    mf = dist(frame_j["f_hand"], stance_j["f_hand"])
    mb = dist(frame_j["b_hand"], stance_j["b_hand"])
    reach = float(mapping["reach_norm_px"])
    tf = min(1.0, mf / reach)
    tb = min(1.0, mb / reach)
    tw = min(1.0, min(mf, mb) /
             float(mapping["wave_min_norm_px"])) * float(mapping["wave_arm_weight"])
    af, ab = max(tf, tw), max(tb, tw)
    g = mapping["arm_gain_deg"]
    leg_cap = float(mapping["leg_cap_deg"])
    d = {
        "hips": 0.0, "spine": used, "chest": 0.0, "neck": 0.0,
        "head": -used * float(mapping["head_compensation"]),
        "upperarm_f": -float(g["f_upper"]) * af,
        "forearm_f": -float(g["f_fore"]) * af,
        "upperarm_b": float(g["b_upper"]) * ab,
        "forearm_b": float(g["b_fore"]) * ab,
        "thigh_f": max(-leg_cap, min(leg_cap, raw["thigh_f"])),
        "shin_f": max(-leg_cap, min(leg_cap, raw["shin_f"])),
        "thigh_b": max(-leg_cap, min(leg_cap, raw["thigh_b"])),
        "shin_b": max(-leg_cap, min(leg_cap, raw["shin_b"])),
    }
    return d, raw


def const_of(src: str, name: str) -> float:
    m = re.search(r"^const\s+" + re.escape(name) + r"\s*:=\s*([0-9.]+)",
                  src, re.M)
    return float(m.group(1)) if m else -1.0


def main() -> int:
    m = json.loads(MOTION.read_text(encoding="utf-8"))
    mf = json.loads(MOTION_FOE.read_text(encoding="utf-8"))
    cm = json.loads(CARD_MOTION.read_text(encoding="utf-8"))
    rhythm_src = RHYTHM.read_text(encoding="utf-8")
    layer_src = LAYER.read_text(encoding="utf-8")
    arena_src = ARENA.read_text(encoding="utf-8")
    driver_src = DRIVER.read_text(encoding="utf-8")

    stance_j = {k: tuple(v) for k, v in m["stance"].items()}
    stance_points = make_points(stance_j)
    chain, mapping = m["chain"], m["mapping"]
    leg_cap = float(mapping["leg_cap_deg"])

    per_card = {}
    all_deltas = {}
    cap_hits = {"leg": 0, "torso": 0}
    total_frames = 0
    for card, body in m["cards"].items():
        track = body["track"]
        total_frames += len(track)
        rows = []
        for j in track:
            fj = {k: tuple(v) for k, v in j.items()}
            d, raw = retarget_delta(fj, stance_j, chain, mapping,
                                    stance_points)
            rows.append(d)
            for n, v in d.items():
                all_deltas.setdefault(n, []).append(v)
            for key in ("thigh_f", "shin_f", "thigh_b", "shin_b"):
                if abs(raw[key]) > leg_cap:
                    cap_hits["leg"] += 1
                    break
            torso_raw = math.degrees(wrap_pi(
                angle(make_points(fj)["A"], make_points(fj)["D"])
                - angle(stance_points["A"], stance_points["D"])))
            if abs(torso_raw * float(mapping["torso_gain"])) > float(
                    mapping["torso_cap_deg"]):
                cap_hits["torso"] += 1
        hand_max = max(dist({k: tuple(v) for k, v in j.items()}["f_hand"],
                            stance_j["f_hand"]) for j in track)
        # ATTACK_S 结束时从末帧瞬间跳回 stance 的最大骨角差
        snap = max(abs(v) for v in rows[-1].values()) if rows else 0.0
        per_card[card] = {
            "frames": len(track),
            "front_hand_max_px": round(hand_max, 2),
            "snap_back_max_deg": round(snap, 2),
            "bone_range_deg": {
                n: round(max(r[n] for r in rows) - min(r[n] for r in rows), 2)
                for n in rows[0]
            },
        }

    bone_stats = {
        n: {"min": round(min(v), 2), "max": round(max(v), 2),
            "range": round(max(v) - min(v), 2)}
        for n, v in all_deltas.items()
    }

    # 2D 动作表规模（从卡表本身读，不抄文档）
    cards2d = cm.get("cards", {})
    n2d = 0
    for _k, v in cards2d.items():
        n2d += len(v.get("track", [])) if isinstance(v, dict) else len(v)
    reacts = cm.get("motions", {})
    react_frames = 0
    for _k, v in reacts.items():
        react_frames += len(v.get("track", [])) if isinstance(v, dict) else len(v)

    attack_s = const_of(rhythm_src, "ATTACK_S")
    total_s = const_of(rhythm_src, "TOTAL_S")
    round_s = REVEAL_S + total_s
    # 只在 apply() 函数体内取白名单；"stance" 是兜底赋值不是允许的动作，
    # 首版把整份源码一起扫得到 4 个，判据假红，这里按形态订正。
    apply_m = re.search(r"func apply\(.*?\n(.*?)(?=\nfunc )", layer_src, re.S)
    apply_body = apply_m.group(1) if apply_m else ""
    whitelist = sorted(set(re.findall(
        r'c\s*!=\s*"([a-z]+)"', apply_body)) - {"stance"})
    fallback_to_stance = 'c = "stance"' in apply_body
    loser_static = "73 帧表里没有受击轨道" in arena_src or \
        "没有受击轨道" in arena_src
    winner_only = "tk_rhythm_winner" in arena_src

    report = {
        "inputs": {
            "motion_input": str(MOTION),
            "motion_input_foe": str(MOTION_FOE),
            "card_motion": str(CARD_MOTION),
            "foe_same_cards": (
                {k: len(v["track"]) for k, v in mf["cards"].items()}
                == {k: len(v["track"]) for k, v in m["cards"].items()}),
        },
        "3d": {
            "cards": {k: len(v["track"]) for k, v in m["cards"].items()},
            "total_frames": total_frames,
            "bones": len(m["bones"]), "chain": len(chain),
            "whitelist_in_apply": whitelist,
            "mapping": mapping,
            "bone_delta_deg": bone_stats,
            "cap_hit_frames": cap_hits,
            "per_card": per_card,
        },
        "2d": {
            "cards": len(cards2d), "card_frames": n2d,
            "react_tracks": len(reacts), "react_frames": react_frames,
        },
        "timeline": {
            "reveal_s": REVEAL_S, "resolve_s": total_s,
            "round_s": round_s, "attack_window_s": attack_s,
            "winner_motion_window_ratio": round(attack_s / round_s, 4),
            "loser_motion_window_s": 0.0,
            "loser_is_static_by_source": loser_static,
            "winner_only_branch_present": winner_only,
        },
        "gaps": {
            "3d_frame_coverage_of_2d": round(total_frames / max(1, n2d), 4),
            "3d_has_react_track": any(
                k.startswith("hit") for k in m["cards"]),
            # 首版假设「ATTACK_S 结束会硬跳回 stance」，实测末帧本来就
            # 几乎回到站架，最大只剩 1.42°，不构成可见跳变，如实订正。
            "snap_back_max_deg": max(
                v["snap_back_max_deg"] for v in per_card.values()),
            "snap_back_visible": max(
                v["snap_back_max_deg"] for v in per_card.values()) > 5.0,
            "cross_front_hand_frozen": (
                per_card.get("cross", {}).get("front_hand_max_px", -1) == 0.0),
            "apply_fallback_to_stance": fallback_to_stance,
            "driver_is_runtime_gdscript": (
                "skel.set_bone_pose_rotation" in driver_src),
        },
        "checks": {
            "read_3d_cards": len(m["cards"]) == 3,
            "read_3d_frames": total_frames == 72,
            "read_13_bones": len(m["bones"]) == 13 and len(chain) == 13,
            "read_2d_bigger_than_3d": n2d > total_frames,
            "read_attack_window": attack_s > 0 and total_s > attack_s,
            "read_whitelist_is_three": len(whitelist) == 3,
            "apply_fallback_recorded": fallback_to_stance,
            "leg_cap_actually_clamps": cap_hits["leg"] > 0,
        },
    }
    report["ok"] = all(report["checks"].values())
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    print("3D cards", report["3d"]["cards"], "total", total_frames,
          "| 2D cards", len(cards2d), "frames", n2d,
          "react", len(reacts), report["2d"]["react_frames"])
    print("whitelist", whitelist, "| ATTACK_S", attack_s,
          "TOTAL_S", total_s, "round", round_s,
          "winner_window_ratio", report["timeline"]["winner_motion_window_ratio"])
    print("cap_hits", cap_hits)
    for n in ("upperarm_f", "forearm_f", "spine", "head",
              "thigh_f", "shin_f", "thigh_b", "shin_b"):
        print("BONE", n, bone_stats[n])
    for c, v in per_card.items():
        print("CARD", c, "frames", v["frames"],
              "hand_max_px", v["front_hand_max_px"],
              "snap_back_deg", v["snap_back_max_deg"])
    for k, v in report["checks"].items():
        print("CHECK", k, v)
    print("DIAG_OK" if report["ok"] else "DIAG_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
