"""Bake CardBoxer's 12 cards from Blender into the game's own joint-dict format.

The rhythm is SNK's, not Blender's default. A KOF move is a handful of drawings
with the extremes *held* for a few frames and one or two frames of snap between
them; Blender's default Bezier eases through every key, which reads as 3D
interpolation and is the one thing a sprite fighter never does. So each key
carries a segment mode:

    hold    CONSTANT -- the pose freezes until the next key (the anticipation)
    snap    LINEAR   -- straight to the next key at speed (the impact frames)
    ease    BEZIER   -- Blender's default, for the return to guard

Blender owns two things here: the timing (keys sit on the card's real
windup/active/recover boundaries, and the F-curves interpolate between them) and
the rig evaluation. The limbs are posed by `boxer_rig.solve_limb` and then read
back out of the evaluated armature, so what lands in the JSON is what Blender
actually drew.

Every card starts and ends on the rest pose.

    blender --background --factory-startup --python boxer_bake.py -- out.json
"""

import json
import math
import os
import sys

import bpy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import boxer_rig as R  # noqa: E402

HAND_F = (48.0, -122.0)
HAND_B = (-2.0, -112.0)
FOOT_F = (30.0, 0.0)
FOOT_B = (-34.0, 0.0)

# Card timing copied from scripts/card_data.gd (windup, active, recover). The
# frame budget is what the game actually spends on the card, so the baked track
# is directly indexable by the action's frame counter. KOF's normals start in 3-13
# frames at 60 fps; these cards (4/6/7/8/10) already sit in that range, so the
# work is all in the shape of the curve, not in the frame budget.
#
# Layout used by every card below:
#   f1        rest
#   early     the extreme: reached fast, then HELD  (this is the anticipation read)
#   snap      1-2 frames to the impact
#   impact    held on the frame damage resolves          <- the KOF "hit stop"
#   settle    a small recoil back past the impact pose
#   last      rest
CARDS = {
    "jab": {
        "frames": (4, 3, 7),
        "keys": [
            (1, {}),
            (2, {"hand_f": (36, -126), "bend_f": 30, "hip": (-5, 0), "lean": -6, "mode": "hold"}),
            (5, {"hand_f": (96, -129), "bend_f": 12, "hip": (5, 0), "lean": 5, "mode": "snap"}),
            (7, {"hand_f": (130, -132), "bend_f": 3, "hip": (11, 0), "lean": 13, "chest": 6,
                 "mode": "hold"}),
            (9, {"hand_f": (122, -130), "bend_f": 7, "hip": (9, 0), "lean": 10, "chest": 4}),
            (14, {}),
        ],
    },
    "cross": {
        "frames": (6, 4, 12),
        "keys": [
            (1, {}),
            (2, {"hand_f": (42, -125), "bend_f": 28, "hip": (-4, 0), "lean": -4}),
            (4, {"hand_f": (32, -124), "bend_f": 32, "hip": (-7, -1), "lean": -8, "mode": "hold"}),
            (7, {"hand_f": (92, -126), "bend_f": 14, "hip": (8, 0), "lean": 8, "chest": 5,
                 "mode": "snap"}),
            (10, {"hand_f": (130, -127), "bend_f": 4, "hip": (14, 0), "lean": 15, "chest": 9,
                  "mode": "hold"}),
            (13, {"hand_f": (120, -125), "bend_f": 9, "hip": (11, 0), "lean": 11, "chest": 6}),
            (22, {}),
        ],
    },
    "uppercut": {
        "frames": (7, 4, 13),
        "keys": [
            (1, {}),
            (3, {"hand_f": (44, -106), "bend_f": 32, "hip": (-5, -10), "lean": -7}),
            (5, {"hand_f": (40, -100), "bend_f": 36, "hip": (-6, -13), "lean": -9, "mode": "hold"}),
            # Below the dip->impact chord on purpose: the fist rises *through* the
            # middle instead of sliding along a straight diagonal.
            (8, {"hand_f": (86, -132), "bend_f": 26, "hip": (4, -6), "lean": 6, "chest": 4,
                 "mode": "snap"}),
            (11, {"hand_f": (104, -172), "bend_f": 10, "hip": (12, 6), "lean": 12, "chest": 8,
                  "mode": "hold"}),
            (14, {"hand_f": (94, -164), "bend_f": 15, "hip": (9, 3), "lean": 9, "chest": 5}),
            (24, {}),
        ],
    },
    "sweep": {
        "frames": (8, 5, 15),
        "keys": [
            (1, {}),
            (4, {"hand_b": (-30, -100), "bend_b": 24, "hip": (-6, -9), "lean": -6}),
            (6, {"hand_b": (-32, -98), "bend_b": 22, "hip": (-7, -14), "lean": -5, "mode": "hold"}),
            (10, {"foot_f": (60, -12), "hand_b": (-34, -96), "bend_b": 20, "hip": (-2, -15),
                  "lean": 0, "mode": "snap"}),
            (13, {"foot_f": (96, -8), "hand_b": (-34, -94), "bend_b": 18, "hip": (2, -16),
                  "lean": 2, "mode": "hold"}),
            (16, {"foot_f": (86, -4), "hand_b": (-32, -96), "bend_b": 20, "hip": (0, -15)}),
            (28, {}),
        ],
    },
    "wave": {
        "frames": (10, 8, 18),
        "keys": [
            (1, {}),
            (4, {"hand_f": (34, -116), "bend_f": 36, "hand_b": (-24, -108), "bend_b": 36,
                 "hip": (-6, 0), "lean": -4}),
            (7, {"hand_f": (26, -112), "bend_f": 42, "hand_b": (-30, -106), "bend_b": 42,
                 "hip": (-9, 0), "lean": -7, "mode": "hold"}),
            (13, {"hand_f": (48, -120), "bend_f": 24, "hand_b": (16, -118), "bend_b": 24,
                  "hip": (-3, 0), "lean": 2, "mode": "snap"}),
            (18, {"hand_f": (62, -126), "bend_f": 8, "hand_b": (48, -120), "bend_b": 8,
                  "hip": (0, 0), "lean": 8, "chest": 4, "mode": "hold"}),
            (22, {"hand_f": (58, -124), "bend_f": 12, "hand_b": (44, -118), "bend_b": 12,
                  "hip": (0, 0), "lean": 6, "chest": 2}),
            (36, {}),
        ],
    },
    "throw": {
        "frames": (5, 4, 11),
        "keys": [
            (1, {}),
            (3, {"hand_f": (60, -127), "bend_f": 20, "hand_b": (22, -118), "bend_b": 20,
                 "hip": (0, 0), "lean": -2}),
            (5, {"hand_f": (72, -128), "bend_f": 18, "hand_b": (40, -120), "bend_b": 18,
                 "hip": (4, 0), "lean": 4, "mode": "hold"}),
            (7, {"hand_f": (80, -126), "bend_f": 22, "hand_b": (54, -120), "bend_b": 22,
                 "hip": (9, 0), "lean": 9, "chest": 4, "mode": "snap"}),
            (9, {"hand_f": (62, -120), "bend_f": 30, "hand_b": (34, -115), "bend_b": 30,
                 "hip": (1, -2), "lean": 0, "mode": "hold"}),
            (12, {"hand_f": (56, -118), "bend_f": 26, "hip": (-2, 0), "lean": -3}),
            (20, {}),
        ],
    },
    "rush": {
        "frames": (4, 0, 9),
        "keys": [
            (1, {}),
            (2, {"hand_f": (42, -116), "bend_f": 22, "hip": (-7, -7), "lean": -5, "mode": "hold"}),
            (5, {"hand_f": (56, -124), "bend_f": 12, "hip": (26, 2), "lean": 22, "chest": 10,
                 "foot_b": (-52, -6), "mode": "snap"}),
            (8, {"hand_f": (50, -122), "bend_f": 16, "hip": (11, 0), "lean": 9, "chest": 3,
                 "foot_b": (-40, 0)}),
            (13, {}),
        ],
    },
    "backstep": {
        "frames": (3, 0, 8),
        "keys": [
            (1, {}),
            (3, {"hand_f": (44, -124), "bend_f": 18, "hip": (-15, -5), "lean": -13,
                 "foot_b": (-44, 0), "mode": "hold"}),
            (5, {"hand_f": (41, -123), "bend_f": 16, "hip": (-18, -6), "lean": -15,
                 "foot_b": (-44, 0), "mode": "snap"}),
            (7, {"hand_f": (46, -123), "bend_f": 15, "hip": (-6, -2), "lean": -6}),
            (11, {}),
        ],
    },
    "guard": {
        "frames": (2, 0, 12),
        "keys": [
            (1, {}),
            (3, {"hand_f": (10, -172), "bend_f": 46, "hand_b": (26, -164), "bend_b": 46,
                 "hip": (-4, -4), "lean": -4, "chest": -6, "mode": "hold"}),
            (9, {"hand_f": (8, -174), "bend_f": 47, "hand_b": (25, -165), "bend_b": 47,
                 "hip": (-4, -4), "lean": -4, "chest": -6}),
            (14, {}),
        ],
    },
    "sidestep": {
        "frames": (2, 0, 8),
        "keys": [
            (1, {}),
            (2, {"hand_f": (42, -118), "bend_f": 24, "hip": (-10, -4), "lean": -5, "chest": -3}),
            (4, {"hand_f": (38, -117), "bend_f": 26, "hip": (-18, -7), "lean": -9, "chest": -6,
                 "mode": "hold"}),
            (7, {"hand_f": (44, -120), "bend_f": 18, "hip": (-6, -2), "lean": -3, "chest": -2}),
            (10, {}),
        ],
    },
    "focus": {
        "frames": (10, 0, 12),
        "keys": [
            (1, {}),
            (3, {"hand_f": (46, -110), "bend_f": 34, "hand_b": (-34, -104), "bend_b": 34,
                 "hip": (0, -6), "lean": 2}),
            (6, {"hand_f": (46, -96), "bend_f": 46, "hand_b": (-40, -96), "bend_b": 46,
                 "hip": (0, -13), "lean": 2, "mode": "hold"}),
            (14, {"hand_f": (44, -104), "bend_f": 38, "hand_b": (-36, -100), "bend_b": 38,
                  "hip": (0, -6), "lean": 2}),
            (22, {}),
        ],
    },
    "recover": {
        "frames": (4, 0, 10),
        "keys": [
            (1, {}),
            (2, {"hand_f": (46, -112), "bend_f": 26, "hip": (0, -5), "lean": 4}),
            (4, {"hand_f": (44, -108), "bend_f": 30, "hand_b": (-8, -104), "bend_b": 30,
                 "hip": (0, -9), "lean": 6, "mode": "hold"}),
            (8, {"hand_f": (46, -114), "bend_f": 22, "hip": (0, -3), "lean": 2}),
            (14, {}),
        ],
    },
}

MODES = {"hold": "CONSTANT", "snap": "LINEAR", "ease": "BEZIER"}

JOINT_KEYS = ("hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
              "f_knee", "f_foot", "b_knee", "b_foot")


def key_defaults():
    return {
        "hand_f": HAND_F, "hand_b": HAND_B, "foot_f": FOOT_F, "foot_b": FOOT_B,
        "bend_f": None, "bend_b": None, "hip": (0.0, 0.0), "lean": 0.0,
        "chest": 0.0, "mode": "ease",
    }


def resolve_keys(spec):
    """Fill each key out to a full channel set, then hand it to Blender."""
    out = []
    for frame, partial in spec["keys"]:
        key = key_defaults()
        key.update(partial)
        key["frame"] = frame
        out.append(key)
    # If a card bends an elbow anywhere, every key must carry a bend value or the
    # F-curve would interpolate the unspecified ones from the specified ones.
    if any(k["bend_f"] is not None or k["bend_b"] is not None for k in out):
        for key in out:
            if key["bend_f"] is None:
                key["bend_f"] = R.REST_BEND["f_arm"]
            if key["bend_b"] is None:
                key["bend_b"] = R.REST_BEND["b_arm"]
    return out


def _fcurves(action):
    """Blender 5 puts fcurves under action layers; 4.x has them on the action."""
    if hasattr(action, "fcurves") and action.fcurves:
        return list(action.fcurves)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


def animate(arm, spec):
    keys = resolve_keys(spec)
    total = sum(spec["frames"])
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = total

    for key in keys:
        f = key["frame"]
        assert 1 <= f <= total, "key frame %d outside the card's %d frame budget" % (f, total)
        R.set_targets(hand_f=key["hand_f"], hand_b=key["hand_b"],
                      foot_f=key["foot_f"], foot_b=key["foot_b"])
        for name, bend in (("t_hand_f", key["bend_f"]), ("t_hand_b", key["bend_b"])):
            if bend is None:
                continue
            ob = bpy.data.objects[name]
            ob["bend"] = bend
            ob.keyframe_insert('["bend"]', frame=f)
        # All four units, feet included: the solve reads the empties' animated
        # values, so a foot that is set but never keyed simply never moves
        # (measured: sweep's kick stayed at x=30 for all 28 frames).
        for name in ("t_hand_f", "t_hand_b", "t_foot_f", "t_foot_b"):
            bpy.data.objects[name].keyframe_insert("location", frame=f)
        R.torso(arm, fwd_px=key["hip"][0], up_px=key["hip"][1],
                lean_deg=key["lean"], chest_deg=key["chest"])
        arm.pose.bones["hips"].keyframe_insert("location", frame=f)
        arm.pose.bones["spine"].keyframe_insert("rotation_euler", frame=f)
        arm.pose.bones["chest"].keyframe_insert("rotation_euler", frame=f)

    # Segment mode per key frame. Pose bones are animated through the armature
    # object's action, so the armature is one of the objects to walk.
    by_frame = {k["frame"]: MODES[k["mode"]] for k in keys}
    for ob in list(bpy.data.objects) + [arm]:
        ad = ob.animation_data
        if not ad or not ad.action:
            continue
        for fc in _fcurves(ad.action):
            for kp in fc.keyframe_points:
                mode = by_frame.get(round(kp.co[0]))
                if mode:
                    kp.interpolation = mode
    return total, keys


def body_step(a, b):
    """Largest joint displacement between two frames: is the body moving at all?"""
    return max(math.dist(a[j], b[j]) for j in JOINT_KEYS)


def sample(arm, cid, spec, total):
    scene = bpy.context.scene
    windup, active, recover = spec["frames"]
    impact = windup + max(active, 1)
    track = []
    worst_err = 0.0
    for f in range(1, total + 1):
        scene.frame_set(f)
        targets = {limb: R.game_px(bpy.data.objects[empty])
                   for limb, (_u, _fo, empty) in R.LIMBS.items()}
        ks = R.solve_all(arm)
        joints = R.joint_table(arm)
        worst_err = max(worst_err,
                        math.dist(joints["f_hand"], targets["f_arm"]),
                        math.dist(joints["b_hand"], targets["b_arm"]),
                        math.dist(joints["f_foot"], targets["f_leg"]),
                        math.dist(joints["b_foot"], targets["b_leg"]))
        if f <= windup:
            phase = "windup"
        elif f <= windup + active:
            phase = "active"
        else:
            phase = "recover"
        lean_deg = math.degrees(-arm.pose.bones["spine"].rotation_euler.z) + \
            math.degrees(-arm.pose.bones["chest"].rotation_euler.z)
        torso_deg = round(lean_deg, 1)
        # `lean` is fighter.gd's shear knob: the game shifts the torso polygon's
        # top edge by this many px-ish. Derived from the actual torso angle so a
        # future renderer can rotate instead of shear.
        lean = max(-0.45, min(0.45, 0.9 * math.tan(math.radians(torso_deg))))
        track.append({
            "f": f,
            "phase": phase,
            "torso_deg": torso_deg,
            "lean": round(lean, 3),
            "k": ks,
            **joints,
        })
    return track, worst_err, impact


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "baked.json"

    report = {"units": "game px; origin at the feet; +x forward; -y up",
              "rhythm": "hold=CONSTANT, snap=LINEAR, ease=BEZIER",
              "cards": {}, "warnings": []}
    for cid, spec in CARDS.items():
        arm = R.build()
        total, keys = animate(arm, spec)
        track, worst_err, impact = sample(arm, cid, spec, total)
        held = sum(1 for i in range(1, len(track))
                   if body_step(track[i], track[i - 1]) < 0.5)
        report["cards"][cid] = {
            "frames": total,
            "split": spec["frames"],
            "impact": impact,
            "held_frames": held,
            "readback_error_px": round(worst_err, 3),
            "track": track,
        }
        print("[%s] %d frames, impact @%d, held %d/%d, readback err %.3f px" % (
            cid, total, impact, held, total - 1, worst_err))
        if worst_err > 0.5:
            report["warnings"].append("%s: readback error %.2f px" % (cid, worst_err))

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("wrote %s (%d cards)" % (out_path, len(report["cards"])))


main()
