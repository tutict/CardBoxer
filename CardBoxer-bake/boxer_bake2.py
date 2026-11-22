"""Re-model CardBoxer's motion on a fighting stance, and bake it to joint tables.

What changed from v1, and why:

* **The rest pose is a stance, not a mannequin.** v1's rest was straight-legged
  with both hands at waist height, so every card was an upright figure sliding
  around. The rig now rests with the knees bent 40 px lower, weight on the back
  leg, both hands at chin height, and both elbows folded. Every card is an offset
  from here; a bad stance poisons all twelve.

* **Weight actually moves.** Each attack carries hip travel (fwd/up), and the back
  heel lifts on the cross. The knees are solved from feet + hips, so hip travel is
  what produces knee bend -- there is no separate "bend the knee" channel.

* **The head arrives late.** `neck` is a real channel now. On every snap the body
  starts forward while the skull is still going back, which is the cheapest
  secondary motion there is.

* **Hit reactions exist.** v1 had none; the game tilted the whole upper body by a
  fixed angle instead. Three tracks here, played normalised over the stun duration
  so they always finish exactly when control comes back.

Rhythm is still SNK's: few drawings, extremes held, one or two frames of snap.

    blender --background --factory-startup --python boxer_bake2.py -- out.json

Frames per card come from scripts/card_data.gd (windup, active, recover), so a
baked track is indexable by the game's own phase counter.
"""

import json
import math
import os
import sys

import bpy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import boxer_rig as R  # noqa: E402

# The stance in game px. Only used for authoring readability; the rig owns the
# actual rest geometry, and these must match boxer_rig.BONES.
#
# 后手从 (-6,-146) 挪到 (-24,-138)：原来那只拳头距肩只有 4.5 px，等于长在三角肌
# 里，画面上看不见，而且躯干一前倾肩就压到拳头上，后臂被迫折到极限、再被缩短
# （实测 k 掉到 0.23）。挪到护肋位置后距肩 27.9 px，弦朝后，肘的侧别不变。
STANCE = {
    "hip": (0, -80), "shoulder": (2, -148), "head": (4, -172),
    "f_elbow": (30, -132), "f_hand": (44, -156),
    "b_elbow": (-18.0, -130.0), "b_hand": (-24, -152),
    "f_knee": (34, -40), "f_foot": (36, 0),
    "b_knee": (-24.2, -42.1), "b_foot": (-44, 0),
}

#: 关节名，与 boxer_rig.joint_table / fighter.gd _build_pose 一一对应。
JOINTS = ["hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
          "f_knee", "f_foot", "b_knee", "b_foot"]


def joint_gap(a, b):
    """两组关节的最大单轴差（px）。缺键当作无穷大 —— 静默当 0 会让检查瞎掉。"""
    worst = 0.0
    for k in JOINTS:
        if k not in a or k not in b:
            return float("inf")
        worst = max(worst, abs(a[k][0] - b[k][0]), abs(a[k][1] - b[k][1]))
    return worst

# Elbow bend in degrees off straight. The rest fold is what the rig computes
# (~170 deg: a guard hand sits ~10 px from its own shoulder), so "straight" has to
# be spelled out on every key that extends.
S = 6      # extended
MID = 30
HALF = 70
#: leave the bend at the stance fold
G = None

CARDS = {
    # ---- 直拳类 ------------------------------------------------------------
    "jab": {
        "frames": (4, 3, 7),
        "keys": [
            (1, {}),
            # load: weight shifts back onto the rear leg, lead hand pulls in
            (2, {"hip": (-5, -2), "lean": -5, "chest": -2, "hand_f": (34, -152), "neck": -2, "mode": "hold"}),
            # snap: hips fire first, hand follows, head trails
            (5, {"hip": (8, 1), "lean": 13, "chest": 7, "hand_f": (98, -152), "neck": -7, "mode": "snap"}),
            # impact: arm straight, shoulder pushed out, skull still behind
            (7, {"hip": (13, 0), "lean": 19, "chest": 10, "hand_f": (124, -150), "neck": -9, "mode": "hold"}),
            # settle: hand drops a touch, head catches up and overshoots
            (9, {"hip": (10, -1), "lean": 15, "chest": 7, "hand_f": (110, -152), "neck": 2}),
            (14, {}),
        ],
    },
    "cross": {
        "frames": (6, 4, 12),
        "keys": [
            (1, {}),
            (3, {"hip": (-7, -3), "lean": -7, "chest": -4, "hand_b": (-16, -148), "neck": -2}),
            (4, {"hip": (-8, -4), "lean": -8, "chest": -5, "hand_b": (-18, -148), "neck": -3, "mode": "hold"}),
            # rear heel lifts and the hips rotate through
            (7, {"hip": (11, 1), "lean": 17, "chest": 11, "hand_b": (94, -150), "foot_b": (-40, -3), "neck": -9, "mode": "snap"}),
            (10, {"hip": (19, 0), "lean": 25, "chest": 15, "hand_b": (122, -148), "foot_b": (-38, -5), "neck": -11, "mode": "hold"}),
            (13, {"hip": (15, -1), "lean": 19, "chest": 10, "hand_b": (108, -150), "foot_b": (-40, -2), "neck": 3}),
            (22, {}),
        ],
    },
    "uppercut": {
        "frames": (7, 4, 13),
        "keys": [
            (1, {}),
            # sink: this is the whole read of the move
            (3, {"hip": (-4, -7), "lean": -8, "chest": -5, "hand_f": (40, -142), "neck": -3}),
            (5, {"hip": (-5, -12), "lean": -11, "chest": -7, "hand_f": (36, -136), "neck": -5, "mode": "hold"}),
            # rise: the fist travels *up* the chord, not along it
            (8, {"hip": (5, -4), "lean": 6, "chest": 4, "hand_f": (72, -158), "neck": -8, "mode": "snap"}),
            # impact: above the chin, hips extended, rear heel up
            # 拳头伸到 x=112 而不是 92：判定距离就是 112，画不出来就是隔空命中。
            # y 从 -186 收到 -178 换来 8 px 的水平余量（d 从 88.4 降到 85.2，
            # k 1.48 → 1.42），仍然在刺拳 1.45 这条已有的拉伸上限以内。
            (11, {"hip": (12, 4), "lean": 14, "chest": 10, "hand_f": (112, -178), "foot_b": (-42, -4), "neck": -10, "mode": "hold"}),
            (14, {"hip": (9, 2), "lean": 10, "chest": 6, "hand_f": (100, -172), "foot_b": (-43, -2), "neck": 2}),
            (24, {}),
        ],
    },
    # ---- 腿法与位移 --------------------------------------------------------
    # 扫堂腿。原来那版是「身体压低了往前蹬一脚」，量出来三个毛病：
    #   * 躯干前倾 12°、头压到扫腿那一侧 —— 整个人像弓步扑出去，不是扫；
    #   * 扫的那条腿脚掌贴着地面（y=-4），跟支撑脚一样平 —— 画面上是**两只站着
    #     的脚**，读成劈叉的宽站架；
    #   * 前手落在躯干里面（手在 x=30 而髋在 26、肩在 42），剪影上一个圆圈浮在
    #     胸口上，像画坏了。
    # 扫堂腿的读法：髋沉到 46（站位是 80），支撑腿折到 0.67 倍骨链压住，扫的腿
    # 几乎水平地甩出去、脚离地 18 px，躯干**反着往支撑腿那边仰**当配重，前手垂到
    # 髋以下当平衡。支撑脚也不是硬滑过去的：起势时抬起来跨一步再落地。
    "sweep": {
        "frames": (8, 5, 15),
        "keys": [
            (1, {}),
            # 起势：重心压到后腿；后脚抬起，准备往身下跨一步
            (4, {"hip": (-6, -14), "lean": -6, "chest": -3, "neck": 2,
                 "foot_b": (-40, -4), "foot_f": (30, -4),
                 "hand_f": (38, -146), "hand_b": (-34, -140)}),
            # 后脚往身前跨（腾空），扫的腿收回来从身前过
            (6, {"hip": (-8, -22), "lean": -8, "chest": -4, "neck": 4,
                 "foot_b": (-20, -8), "foot_f": (-6, -12),
                 "hand_f": (30, -118), "hand_b": (-36, -132), "mode": "hold"}),
            # 蓄满：后脚落到身下、支撑腿折起来，扫的腿甩到身后 -72、离地 16
            (8, {"hip": (-4, -30), "lean": -6, "chest": -3, "neck": 6,
                 "foot_b": (2, -6), "foot_f": (-72, -16),
                 "hand_f": (26, -96), "hand_b": (-30, -124), "mode": "hold"}),
            # 抽回来：腿从身体底下穿过（折叠、抬高 16 px 免得跟支撑脚糊在一起）
            (10, {"hip": (8, -32), "lean": -8, "chest": -4, "neck": 2,
                  "foot_b": (8, 0), "foot_f": (-10, -16),
                  "hand_f": (32, -90), "hand_b": (-20, -118), "mode": "snap"}),
            # 命中 f13：人坐在折起来的支撑腿上，扫的腿几乎水平甩到 98、离地 16，
            # 躯干往支撑腿那边仰回去当配重，前手垂到髋以下
            (13, {"hip": (18, -34), "lean": -9, "chest": -5, "neck": 6,
                  "foot_b": (12, 0), "foot_f": (98, -16),
                  # 前手要伸到躯干外面去。原来 x=46 时手圈正好压在躯干右缘上，
                  # 剪影看着像胸口长了个瘤；肩在 (9,-114)、臂链 60，x=54 是能
                  # 够到的最外侧（弦 57），再远就要拉长胳膊了。
                  "hand_f": (54, -78), "hand_b": (-14, -106), "mode": "hold"}),
            # 收：脚抬回来、后脚撤回站架（也是抬起来的，不在地上蹭）
            (16, {"hip": (12, -26), "lean": -5, "chest": -3,
                  "foot_b": (-10, -8), "foot_f": (76, -12),
                  "hand_f": (36, -96), "hand_b": (-22, -124)}),
            (22, {"hip": (4, -10), "lean": -2, "foot_b": (-38, -4),
                  "foot_f": (52, -4), "hand_f": (40, -140), "hand_b": (-30, -140),
                  "mode": "snap"}),
            (28, {}),
        ],
    },
    "rush": {
        "frames": (4, 0, 9),
        "keys": [
            (1, {}),
            # gather: hips back, both feet loaded
            (2, {"hip": (-8, -5), "lean": -6, "hand_f": (38, -154), "neck": -2, "mode": "hold"}),
            # push-off: rear foot drives back, body way ahead of the feet
            # 后手必须跟着身体走：不 key 的话它还停在站架的 (-24,-138)，而肩已经冲到
            # x=53.9，后臂被拉到 1.57 倍长（明显的橡皮胳膊）。这里让它少跟一点，
            # 留出 6~18 px 的滞后（跑动时手臂本来就该拖后），但不再拉断。
            (5, {"hip": (24, 0), "lean": 24, "chest": 12, "hand_f": (52, -146),
                 "hand_b": (-6, -140), "foot_b": (-56, -8), "neck": -10, "mode": "snap"}),
            (8, {"hip": (12, -2), "lean": 14, "chest": 6, "hand_f": (46, -150),
                 "hand_b": (-10, -138), "foot_b": (-48, -2), "neck": 2}),
            (13, {}),
        ],
    },
    "backstep": {
        "frames": (3, 0, 8),
        "keys": [
            (1, {}),
            # front foot pushes, torso leans away, hands stay up
            (3, {"hip": (-14, -4), "lean": -14, "chest": -8, "hand_f": (40, -158),
                 "foot_f": (30, -2), "neck": 4, "mode": "hold"}),
            (5, {"hip": (-17, -6), "lean": -17, "chest": -9, "hand_f": (38, -158),
                 "foot_f": (26, -1), "neck": 5, "mode": "snap"}),
            (7, {"hip": (-6, -2), "lean": -7, "chest": -3, "hand_f": (42, -156),
                 "foot_f": (34, 0)}),
            (11, {}),
        ],
    },
    # ---- 守御/蓄力 ---------------------------------------------------------
    "guard": {
        "frames": (2, 0, 12),
        "keys": [
            (1, {}),
            # shoulders hunch, both gloves squeeze to the chin, chin drops
            (3, {"hip": (-5, -4), "lean": -5, "chest": -6, "hand_f": (30, -158),
                 "hand_b": (-10, -150),
                 "neck": 6, "mode": "hold"}),
            # a呼吸-level tremble so a held guard is not a still image
            (9, {"hip": (-5, -3), "lean": -5, "chest": -5, "hand_f": (31, -157),
                 "hand_b": (-9, -149), "neck": 5}),
            (14, {}),
        ],
    },
    "sidestep": {
        "frames": (2, 0, 8),
        "keys": [
            (1, {}),
            (2, {"hip": (-8, -3), "lean": -6, "chest": -3, "hand_f": (40, -152),
                 "foot_f": (32, 0)}),
            (4, {"hip": (-15, -6), "lean": -10, "chest": -6, "hand_f": (36, -150),
                 "foot_f": (28, -1), "neck": 3, "mode": "hold"}),
            (7, {"hip": (-5, -2), "lean": -4, "chest": -2, "hand_f": (42, -154),
                 "foot_f": (34, 0)}),
            (10, {}),
        ],
    },
    "focus": {
        "frames": (10, 0, 12),
        "keys": [
            (1, {}),
            (3, {"hip": (0, -6), "lean": 3, "hand_f": (38, -136), "hand_b": (-14, -132)}),
            # deep sink, fists at the ribs, chin tucked
            (6, {"hip": (0, -14), "lean": 4, "hand_f": (34, -124), "hand_b": (-18, -124), "neck": 6, "mode": "hold"}),
            (14, {"hip": (0, -6), "lean": 3, "hand_f": (40, -138), "hand_b": (-12, -134), "neck": 2}),
            (22, {}),
        ],
    },
    "recover": {
        "frames": (4, 0, 10),
        "keys": [
            (1, {}),
            # exhale: shoulders drop, stance widens a little
            (2, {"hip": (0, -5), "lean": 3, "hand_f": (42, -150), "neck": 3}),
            (4, {"hip": (0, -9), "lean": 5, "hand_f": (40, -146),
                 "hand_b": (-10, -140), "neck": 4, "mode": "hold"}),
            (8, {"hip": (0, -4), "lean": 2, "hand_f": (43, -152), "neck": 1}),
            (14, {}),
        ],
    },
    # 气功波：蓄力的手走「合 → 推」，髋先沉再顶出去
    "wave": {
        "frames": (10, 8, 18),
        "keys": [
            (1, {}),
            (4, {"hip": (-6, -2), "lean": -4, "hand_f": (36, -150), "hand_b": (-12, -142)}),
            (7, {"hip": (-8, -4), "lean": -7, "hand_f": (30, -146), "hand_b": (-16, -138), "neck": -3, "mode": "hold"}),
            (13, {"hip": (4, 0), "lean": 4, "hand_f": (54, -152), "hand_b": (14, -146), "neck": -7, "mode": "snap"}),
            (18, {"hip": (9, 1), "lean": 9, "chest": 5, "hand_f": (66, -154),
                  "hand_b": (34, -148),
                  "neck": -8, "mode": "hold"}),
            (22, {"hip": (7, 0), "lean": 7, "chest": 3, "hand_f": (60, -152),
                  "hand_b": (28, -146), "neck": 2}),
            (36, {}),
        ],
    },
    "throw": {
        "frames": (5, 4, 11),
        "keys": [
            (1, {}),
            # 前摇：双手往回收、重心下沉 —— 抓之前先蓄，别在风摇里就伸出去
            # （原来 f5 伸到 64 而命中帧 f9 只有 38：画面上「伸手」和「命中」是反的，
            #  玩家看到的是手已经收回胸前人才飞出去）
            (3, {"hip": (-3, -2), "lean": -3, "hand_f": (36, -150), "hand_b": (-26, -140), "neck": -2}),
            (5, {"hip": (-5, -3), "lean": -5, "chest": -3, "hand_f": (32, -148),
                 "hand_b": (-28, -140), "neck": -3, "mode": "hold"}),
            # 出手抓人：双臂一起甩出去，命中落在 active 最后一帧（f9）
            (7, {"hip": (6, 0), "lean": 9, "chest": 7, "hand_f": (80, -148),
                 "hand_b": (44, -142), "neck": -6, "mode": "snap"}),
            # 抓住：前手到 98（判定距离就是 98）
            (9, {"hip": (10, -1), "lean": 14, "chest": 11, "hand_f": (98, -146),
                 "hand_b": (62, -140), "foot_b": (-40, -3), "neck": -9, "mode": "hold"}),
            # 收招：把人收进来，重心落回后腿
            (12, {"hip": (4, -2), "lean": 5, "chest": 3, "hand_f": (60, -150),
                  "hand_b": (6, -140), "foot_b": (-43, -1), "neck": 3}),
            (20, {}),
        ],
    },
}

# Hit reactions. Played normalised over the stun duration, so the last frame is
# always the stance and control returns without a pop. Frame counts are only the
# authoring resolution, not a duration.
REACTS = {
    # 轻受击：2 帧被打出去，停住，再回来
    "hit_light": {
        "frames": 16,
        "keys": [
            (1, {}),
            (2, {"hip": (-7, -1), "lean": -13, "chest": -9, "neck": 14,
                 "hand_f": (36, -146), "hand_b": (-18, -140), "mode": "snap"}),
            (4, {"hip": (-8, -1), "lean": -14, "chest": -10, "neck": 15,
                 "hand_f": (35, -146), "hand_b": (-19, -140), "mode": "hold"}),
            (7, {"hip": (-2, -1), "lean": 3, "chest": 2, "neck": -4,
                 "hand_f": (44, -154), "hand_b": (-8, -146)}),
            (11, {"hip": (1, 0), "lean": -2, "chest": -1, "neck": 1}),
            (16, {}),
        ],
    },
    # 重受击：整个人被推出去一步，后脚拖行
    "hit_heavy": {
        "frames": 30,
        "keys": [
            (1, {}),
            (2, {"hip": (-14, -2), "lean": -24, "chest": -16, "neck": 22,
                 "hand_f": (28, -136), "hand_b": (-26, -132), "foot_b": (-50, -2), "mode": "snap"}),
            (5, {"hip": (-16, -3), "lean": -26, "chest": -18, "neck": 24,
                 "hand_f": (26, -134), "hand_b": (-28, -130), "foot_b": (-56, -1), "mode": "hold"}),
            (10, {"hip": (-8, -4), "lean": -10, "chest": -6, "neck": 8,
                  "hand_f": (34, -146), "hand_b": (-20, -140), "foot_b": (-52, 0)}),
            (16, {"hip": (-4, -2), "lean": 4, "chest": 3, "neck": -6,
                  "hand_f": (40, -152), "hand_b": (-12, -144)}),
            (22, {"hip": (-1, -1), "lean": -2, "chest": -1, "neck": 2}),
            (30, {}),
        ],
    },
    # 格挡：只退半步，手不离下巴
    "block": {
        "frames": 10,
        "keys": [
            (1, {}),
            (2, {"hip": (-6, -1), "lean": -7, "chest": -4, "neck": 6,
                 "hand_f": (34, -160), "hand_b": (-10, -152), "mode": "snap"}),
            (4, {"hip": (-6, -1), "lean": -7, "chest": -4, "neck": 6,
                 "hand_f": (34, -160), "hand_b": (-10, -152), "mode": "hold"}),
            (7, {"hip": (-2, 0), "lean": -2, "chest": -1, "neck": 1,
                 "hand_f": (40, -158), "hand_b": (-8, -148)}),
            (10, {}),
        ],
    },
}

MODES = {"hold": "CONSTANT", "snap": "LINEAR", "ease": "BEZIER"}

JOINT_KEYS = ("hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
              "f_knee", "f_foot", "b_knee", "b_foot")


def key_defaults():
    """Every channel rests at the stance unless the key says otherwise."""
    return {
        "hand_f": STANCE["f_hand"], "hand_b": STANCE["b_hand"],
        "foot_f": STANCE["f_foot"], "foot_b": STANCE["b_foot"],
        "hip": (0.0, 0.0), "lean": 0.0, "chest": 0.0, "neck": 0.0, "mode": "ease",
    }


def resolve_keys(keys_spec):
    out = []
    for frame, partial in keys_spec:
        key = key_defaults()
        key.update(partial)
        key["frame"] = frame
        out.append(key)
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


def animate(arm, frames, keys_spec):
    keys = resolve_keys(keys_spec)
    total = sum(frames) if isinstance(frames, tuple) else int(frames)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = total

    for key in keys:
        f = key["frame"]
        assert 1 <= f <= total, "key frame %d outside the %d frame budget" % (f, total)
        R.set_targets(hand_f=key["hand_f"], hand_b=key["hand_b"],
                      foot_f=key["foot_f"], foot_b=key["foot_b"])
        # No bend channel: the elbow angle is derived from each target's distance
        # every frame (boxer_rig.solve_limb), so it is continuous by construction
        # and never needs a key. Authoring it as a separate curve is what produced
        # the 9.8x rubber limb -- see the note in solve_limb.
        #
        # All four units, feet included: the solve reads the empties' animated
        # values, so a foot that is set but never keyed simply never moves.
        for name in ("t_hand_f", "t_hand_b", "t_foot_f", "t_foot_b"):
            bpy.data.objects[name].keyframe_insert("location", frame=f)
        R.torso(arm, fwd_px=key["hip"][0], up_px=key["hip"][1],
                lean_deg=key["lean"], chest_deg=key["chest"], neck_deg=key["neck"])
        arm.pose.bones["hips"].keyframe_insert("location", frame=f)
        arm.pose.bones["spine"].keyframe_insert("rotation_euler", frame=f)
        arm.pose.bones["chest"].keyframe_insert("rotation_euler", frame=f)
        arm.pose.bones["neck"].keyframe_insert("rotation_euler", frame=f)

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
    return total


def body_step(a, b):
    """Largest joint displacement between two frames: is the body moving at all?"""
    return max(math.dist(a[j], b[j]) for j in JOINT_KEYS)


def sample(arm, total, split):
    """Read the evaluated armature back, one entry per frame."""
    scene = bpy.context.scene
    windup, active, _recover = split
    impact = windup + max(active, 1)
    track = []
    worst = 0.0
    for f in range(1, total + 1):
        scene.frame_set(f)
        targets = {limb: R.game_px(bpy.data.objects[empty])
                   for limb, (_u, _fo, empty) in R.LIMBS.items()}
        ks = R.solve_all(arm)
        joints = R.joint_table(arm)
        worst = max(worst,
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
        lean = max(-0.45, min(0.45, 0.9 * math.tan(math.radians(lean_deg))))
        track.append({
            "f": f, "phase": phase, "torso_deg": round(lean_deg, 1),
            "lean": round(lean, 3), "k": ks, **joints,
        })
    return track, worst, impact


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "baked2.json"

    print("rest bends: " + ", ".join("%s=%.1f" % (k, v) for k, v in R.REST_BEND.items()))
    report = {
        "units": "game px; origin at the feet; +x forward; -y up",
        "rhythm": "hold=CONSTANT, snap=LINEAR, ease=BEZIER",
        # 真站架 = 帧 0 的读回值，不是 STANCE 这份手写意图。解算器会把关节放到
        # 骨长允许的唯一点上，手写值只在「作者以为肘在哪」这一层成立 —— 后手肘
        # 就能差 11 px，而游戏画的是解算结果。这份字段的唯一消费者是
        # fighter.gd 的待机姿势，差 11 px 就是每招起手/收招跳一下。
        "stance": {},
        "cards": {}, "motions": {}, "warnings": [],
    }
    kmax = 0.0
    for cid, spec in CARDS.items():
        arm = R.build()
        total = animate(arm, spec["frames"], spec["keys"])
        track, worst, impact = sample(arm, total, spec["frames"])
        held = sum(1 for i in range(1, len(track))
                   if body_step(track[i], track[i - 1]) < 0.5)
        for fr in track:
            kmax = max(kmax, max(fr["k"].values()))
        report["cards"][cid] = {
            "frames": total, "split": list(spec["frames"]), "impact": impact,
            "held_frames": held, "readback_error_px": round(worst, 3), "track": track,
        }
        print("[%-9s] %2d frames, impact @%2d, held %2d/%2d, err %.3f, k<=%.2f" % (
            cid, total, impact, held, total - 1, worst,
            max(max(fr["k"].values()) for fr in track)))
        if worst > 0.5:
            report["warnings"].append("%s: readback error %.2f px" % (cid, worst))

    for name, spec in REACTS.items():
        arm = R.build()
        total = animate(arm, spec["frames"], spec["keys"])
        track, worst, _impact = sample(arm, total, (total, 0, 0))
        for fr in track:
            fr.pop("phase", None)
        report["motions"][name] = {
            "frames": total, "readback_error_px": round(worst, 3), "track": track,
        }
        print("[%-9s] %2d frames (react), err %.3f" % (name, total, worst))

    # 站架不变式，逐条当成硬检查（不是打印完就算）：
    #   ① 每张牌的帧 0 必须彼此相同 —— 否则起手动作的起始姿势随牌变化；
    #   ② 每张牌的末帧必须回到帧 0 —— 否则收招接待机会跳；
    #   ③ 受击反应首末帧同理。
    solved = report["cards"]["recover"]["track"][0]
    joints_only = {k: solved[k] for k in JOINTS}
    report["stance"] = joints_only
    worst_start = 0.0
    worst_end = 0.0
    for cid, entry in report["cards"].items():
        worst_start = max(worst_start, joint_gap(entry["track"][0], joints_only))
        worst_end = max(worst_end, joint_gap(entry["track"][-1], joints_only))
    for name, entry in report["motions"].items():
        worst_start = max(worst_start, joint_gap(entry["track"][0], joints_only))
        worst_end = max(worst_end, joint_gap(entry["track"][-1], joints_only))
    print("stance: 帧0 族内最大差 %.3f px，末帧回归最大差 %.3f px" % (worst_start, worst_end))
    if worst_start > 0.5:
        report["warnings"].append("stance: 帧 0 不一致 %.2f px" % worst_start)
    if worst_end > 1.5:
        report["warnings"].append("stance: 末帧未归位 %.2f px" % worst_end)

    # 手写意图 vs 解算结果。差得多不是错，是「作者以为的关节位置和解算器不同」，
    # 要让人看见，否则 fighter.gd 那三个字面量会一直停在旧值上。
    for k in JOINTS:
        gap = math.dist(STANCE[k], joints_only[k])
        if gap > 0.5:
            print("  stance[%s]: 手写 %.1f,%.1f → 实际 %.1f,%.1f（差 %.1f px）" % (
                k, STANCE[k][0], STANCE[k][1], joints_only[k][0], joints_only[k][1], gap))

    print("max stretch across all cards: %.2fx" % kmax)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("wrote %s (%d cards, %d motions)" % (out_path, len(report["cards"]),
                                               len(report["motions"])))


main()
