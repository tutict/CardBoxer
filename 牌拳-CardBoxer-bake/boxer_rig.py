"""Shared CardBoxer rig: build, solve, read joints.

Coordinate bridge (verified against the game's own default pose):
    game px = (x*100, -z*100)   with 1 m = 100 px, +X forward, +Z up, y lateral
The rest pose is fighter.gd's _build_pose() defaults / 100, so a baked frame drops
into the game's joint dictionary without rescaling.

All four limbs are solved analytically, and the reasons are measured, not assumed
(see probe2/3/4.txt and boxer_debug.txt):
  * Blender's own `use_stretch` stretches a chain to its limit unconditionally:
    a 58 px reach came out with 78.8 + 81.3 px bones.
  * Scaling a chain under an active IK constraint collapses it (probe 3).
  * The game itself needs stretch: its sweep poses a 74 px thigh on a 48.7 px
    bone (1.6x), and its jab a 63.6 px forearm on a 25.5 px bone (2.5x). A rigid
    solve cannot reproduce the silhouette the designer tuned.
So the solver takes the reach as given and reports the stretch factor it needed.
Each segment is scaled by the same k, which keeps the hinge a hinge.
"""

import math

import bpy
from mathutils import Vector

REST = {
    "hip": (0.00, 0.80),
    "shoulder": (0.02, 1.48),
    "head": (0.04, 1.72),
    "f_elbow": (0.30, 1.32),
    "f_hand": (0.44, 1.56),
    "b_elbow": (-0.16, 1.28),
    "b_hand": (-0.02, 1.46),
    "f_knee": (0.34, 0.40),
    "f_foot": (0.36, 0.00),
    "b_knee": (-0.24, 0.42),
    "b_foot": (-0.44, 0.00),
}

# name, head, tail, parent. Both shoulders sit at the game's own shoulder point,
# because _build_pose draws both arms from the same joint.
#
# The rest pose is a *fighting* stance, not a T-stand: knees bent 40 px lower than
# the old straight-legged pose, weight on the back leg, both hands up at chin
# height with the elbows folded. That matters more than any single card's curve --
# every frame of every card is an offset from here, so a straight-legged rest made
# all twelve cards read as an upright mannequin sliding around.
BONES = [
    ("hips", (0.00, 0.80), (0.00, 0.98), None),
    ("spine", (0.00, 0.90), (0.00, 1.22), "hips"),
    ("chest", (0.00, 1.22), (0.02, 1.48), "spine"),
    ("neck", (0.02, 1.48), (0.04, 1.62), "chest"),
    ("head", (0.04, 1.62), (0.04, 1.72), "neck"),
    ("upperarm_f", (0.02, 1.48), (0.30, 1.32), "chest"),
    ("forearm_f", (0.30, 1.32), (0.44, 1.56), "upperarm_f"),
    ("upperarm_b", (0.02, 1.48), (-0.16, 1.28), "chest"),
    ("forearm_b", (-0.16, 1.28), (-0.02, 1.46), "upperarm_b"),
    ("thigh_f", (0.04, 0.80), (0.34, 0.40), "hips"),
    ("shin_f", (0.34, 0.40), (0.36, 0.00), "thigh_f"),
    ("thigh_b", (-0.04, 0.80), (-0.24, 0.42), "hips"),
    ("shin_b", (-0.24, 0.42), (-0.44, 0.00), "thigh_b"),
]

# limb -> (upper bone, lower bone, target empty, joint names)
LIMBS = {
    "f_arm": ("upperarm_f", "forearm_f", "t_hand_f"),
    "b_arm": ("upperarm_b", "forearm_b", "t_hand_b"),
    "f_leg": ("thigh_f", "shin_f", "t_foot_f"),
    "b_leg": ("thigh_b", "shin_b", "t_foot_b"),
}

SOLVED_BONES = tuple(b for limb in LIMBS.values() for b in limb[:2])

#: IK 目标的静止位置，只列与骨骼自身尾端不同的地方（米）。
#:
#: 目标默认放在前臂骨自己的尾端，但后手的尾端距肩只有 4.5 px —— 那是「拳头长在
#: 三角肌里」，不是护手。而且任何躯干前倾都会把肩推到拳头跟前，让后臂折到极限
#: 乃至被缩短（实测 k 掉到 0.23）。后手放到护肋的蓄力位（距肩 27.9 px）之后，
#: 弦始终朝后，肘的解算侧别也就不用改。
REST_TARGET = {"b_arm": (-0.24, 1.38)}

# Hips pose-bone location axes, measured (probe 2):
#   x -> forward (+px), y -> up, z -> unused (lateral, out of the 2D plane)
# Spine pose-bone euler, measured (probe 1/3):
#   z -> forward/back lean (positive z leans BACKWARD), x -> lateral tilt
HIPS_FWD = 0
HIPS_UP = 1


def _bone_geom():
    return {name: (head, tail) for name, head, tail, _p in BONES}


def _rest_side(upper, fore):
    """Which side of the root-tip chord the rest joint sits on.

    Read off the rig rather than passed as a pole vector, so the elbow/knee keeps
    the bend direction it already has and never flips through the chord.
    Measured failure without this: the back elbow solved to x=+1.9, in front of
    the shoulder, where the rest pose has it at x=-14.
    """
    geom = _bone_geom()
    S = geom[upper][0]
    J = geom[upper][1]
    T = geom[fore][1]
    cross = (T[0] - S[0]) * (J[1] - S[1]) - (T[1] - S[1]) * (J[0] - S[0])
    return 1.0 if cross > 0 else -1.0


def _rest_bend(upper, fore):
    """The joint's own bend in the rest pose, in degrees off straight.

    Feeding this back into the solver reproduces the rest pose exactly (k = 1),
    which is what makes frame 1 and the last frame of every card snap-free.
    """
    geom = _bone_geom()
    S, J = geom[upper]
    T = geom[fore][1]
    a = math.dist(S, J)
    b = math.dist(J, T)
    d = math.dist(S, T)
    cos_e = max(-1.0, min(1.0, (a * a + b * b - d * d) / (2.0 * a * b)))
    return 180.0 - math.degrees(math.acos(cos_e))


REST_SIDE = {limb: _rest_side(u, f) for limb, (u, f, _t) in LIMBS.items()}
REST_BEND = {limb: _rest_bend(u, f) for limb, (u, f, _t) in LIMBS.items()}


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


def build():
    clear_scene()
    arm_data = bpy.data.armatures.new("BoxerRig")
    arm = bpy.data.objects.new("BoxerRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for name, head, tail, parent in BONES:
        bone = arm_data.edit_bones.new(name)
        bone.head = (head[0], 0.0, head[1])
        bone.tail = (tail[0], 0.0, tail[1])
        if parent:
            bone.parent = made[parent]
        made[name] = bone
    bpy.ops.object.mode_set(mode="OBJECT")

    for limb, (upper, fore, target) in LIMBS.items():
        empty = bpy.data.objects.new(target, None)
        empty.empty_display_size = 0.05
        # -1 = "derive it from the target"; see solve_limb().
        empty["bend"] = -1.0
        tip = REST_TARGET.get(limb, _bone_geom()[fore][1])
        empty.location = (tip[0], 0.0, -tip[1])
        bpy.context.collection.objects.link(empty)

    for bone in SOLVED_BONES:
        pb = arm.pose.bones[bone]
        pb.rotation_mode = "XYZ"
        # Each segment is placed independently, so the parent's stretch must not
        # silently lengthen the child (measured: the forearm came out 1/4 length).
        pb.bone.inherit_scale = "NONE"
    for bone in ("hips", "spine", "chest"):
        arm.pose.bones[bone].rotation_mode = "XYZ"
    bpy.context.view_layer.update()
    return arm


def pt(vec):
    """Blender world (x, y, z) -> game px (x, -y_up)."""
    return (round(vec.x * 100.0, 1), round(-vec.z * 100.0, 1))


def joint_table(arm):
    bpy.context.view_layer.update()
    pose = arm.pose.bones
    return {
        "hip": pt(pose["hips"].head),
        "shoulder": pt(pose["upperarm_f"].head),
        "head": pt(pose["head"].tail),
        "f_elbow": pt(pose["forearm_f"].head),
        "f_hand": pt(pose["forearm_f"].tail),
        "b_elbow": pt(pose["forearm_b"].head),
        "b_hand": pt(pose["forearm_b"].tail),
        "f_knee": pt(pose["shin_f"].head),
        "f_foot": pt(pose["shin_f"].tail),
        "b_knee": pt(pose["shin_b"].head),
        "b_foot": pt(pose["shin_b"].tail),
    }


def game_px(ob):
    loc = ob.location
    return (round(loc.x * 100.0, 1), round(-loc.z * 100.0, 1))


def set_targets(**kwargs):
    """Targets in game px, e.g. hand_f=(130,-132). Keys: hand_f/hand_b/foot_f/foot_b."""
    for key, value in kwargs.items():
        if value is None:
            continue
        limb = {"hand_f": "f_arm", "hand_b": "b_arm",
                "foot_f": "f_leg", "foot_b": "b_leg"}[key]
        ob = bpy.data.objects[LIMBS[limb][2]]
        ob.location = (value[0] / 100.0, 0.0, -value[1] / 100.0)
    bpy.context.view_layer.update()


def reset_targets():
    geom = _bone_geom()
    for limb, (_u, fore, target) in LIMBS.items():
        tip = geom[fore][1]
        bpy.data.objects[target].location = (tip[0], 0.0, -tip[1])
        bpy.data.objects[target]["bend"] = -1.0
    bpy.context.view_layer.update()


def torso(arm, fwd_px=0.0, up_px=0.0, lean_deg=0.0, chest_deg=0.0, neck_deg=0.0):
    """Move the body under the limbs. Positive lean_deg leans forward (+X).

    `neck_deg` is the head's own angle: the whole body can snap forward while the
    skull keeps going the other way for a frame. This is the cheapest secondary
    motion there is and its absence is a large part of why a pose-per-frame
    animation reads as rigid -- the head is the heaviest thing on the chain and
    always arrives late.
    """
    hips = arm.pose.bones["hips"]
    hips.location = (fwd_px / 100.0, up_px / 100.0, 0.0)
    arm.pose.bones["spine"].rotation_euler = (0.0, 0.0, -math.radians(lean_deg))
    arm.pose.bones["chest"].rotation_euler = (0.0, 0.0, -math.radians(chest_deg))
    arm.pose.bones["neck"].rotation_euler = (0.0, 0.0, -math.radians(neck_deg))
    bpy.context.view_layer.update()


def place(arm, bone_name, head_game, tail_game, length_px):
    """Point a bone from head to tail, then set its length as an explicit scale.

    The matrix carries rotation only: putting the length in the Y column makes
    Blender fold the parent's Y scale into the child's basis, which silently
    shrank the forearm to 1/4 length (measured 6.4 px where 25.2 was asked).
    """
    dx = (tail_game[0] - head_game[0]) / 100.0
    dz = -(tail_game[1] - head_game[1]) / 100.0
    u = Vector((dx, 0.0, dz)).normalized()
    mat = u.to_track_quat("Y", "Z").to_matrix().to_4x4()
    mat.translation = Vector((head_game[0] / 100.0, 0.0, -head_game[1] / 100.0))
    pb = arm.pose.bones[bone_name]
    rest_len_px = pb.bone.length * 100.0
    pb.matrix = mat
    bpy.context.view_layer.update()
    pb.scale = (1.0, length_px / rest_len_px, 1.0)
    bpy.context.view_layer.update()


def solve_limb(arm, limb, target, bend_deg=None):
    """Two-bone solve for one limb. Returns (joint_game_px, stretch_k, root_px).

    With `bend_deg=None` the elbow angle is **derived from the target distance**:
    the chain stays rigid (k = 1) for any reach it can make, and only stretches
    once the target is past full extension. That distinction matters more than it
    looks. v1 authored a fixed bend per key and let k absorb everything, which is
    fine while the shoulder stays put — but the guard arm rests folded at 176 deg,
    where the chord is ~10 px, so a 20 deg lean of the body moved the shoulder 25 px
    and the solver reported a 9.8x stretch. Same picture, rubber limb.

    The segments keep their rest ratio and stretch by one common factor k:
        d^2 = (a k)^2 + (b k)^2 + 2 (a k)(b k) cos(bend)
    so a rigid solve reports k = 1 exactly, and k > 1 says by how much the target
    is out of reach.
    """
    upper, fore, _empty = LIMBS[limb]
    A0 = arm.pose.bones[upper].bone.length * 100.0
    B0 = arm.pose.bones[fore].bone.length * 100.0
    # The root is the solved bone's own head, not the hip/shoulder joint: a thigh
    # starts 4 px forward of the hip, and reading the hip instead left the knees
    # 2-3 px off in every rest frame.
    root = pt(arm.pose.bones[upper].head)
    Sm = (root[0], -root[1])
    Tm = (target[0], -target[1])
    d = math.dist(Sm, Tm)
    if bend_deg is None:
        lo = abs(A0 - B0) + 0.5
        hi = A0 + B0 - 0.5
        if d >= hi:
            # straight arm, then rubber: k carries only the overreach
            bend_deg = 3.0
        elif d <= lo:
            bend_deg = 177.0
        else:
            cos_e = (A0 * A0 + B0 * B0 - d * d) / (2.0 * A0 * B0)
            bend_deg = 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos_e))))
    phi = math.radians(bend_deg)
    denom = math.sqrt(A0 * A0 + B0 * B0 + 2.0 * A0 * B0 * math.cos(phi))
    k = d / denom if denom else 1.0
    # k 只允许 >=1。目标比「完全折起」还近时 denom 是这条链的**最短弦**，d/denom < 1
    # 会把两段骨头一起缩短 —— 后手贴近肩时实测缩到原长的 23%，画面是胳膊塌成一小截。
    # 骨头长度不能变：宁可手落不到目标上（差几 px，读回误差会如实报出来），
    # 也不要画出一条在不同帧里长度不同的胳膊。
    if k < 1.0:
        k = 1.0
    a = A0 * k
    b = B0 * k
    base = math.atan2(Tm[1] - Sm[1], Tm[0] - Sm[0])
    # 解三角形用的距离要按下限夹住。目标比最短弦还近时 a、b、d 构不成三角形，
    # acos 被夹到 ±1，两个候选关节都落在弦上 → 叉积为 0 → 下面选不出侧别 →
    # 落到 `Jg = 肩点` 的兜底，手被扔到 b 之外（实测差 19.8 px）。夹住之后三角形
    # 恒成立，关节总在离弦有距离的圆上，侧别判断也就总有答案。
    lo = abs(A0 - B0) + 0.5
    d_tri = max(d, lo)
    half = math.acos(max(-1.0, min(1.0, (a * a + d_tri * d_tri - b * b) / (2.0 * a * d_tri))))
    want = REST_SIDE[limb]
    Jg = None
    for sign in (+1.0, -1.0):
        ang = base + sign * half
        J = (Sm[0] + a * math.cos(ang), Sm[1] + a * math.sin(ang))
        cross = (Tm[0] - Sm[0]) * (J[1] - Sm[1]) - (Tm[1] - Sm[1]) * (J[0] - Sm[0])
        if (1.0 if cross > 0 else -1.0) == want:
            Jg = (J[0], -J[1])
            break
    if Jg is None:
        # 真的选不出侧别（共线）。沿弦放，至少是一条正常长的直臂，
        # 不要放回肩点 —— 那会让整条胳膊的长度凭空消失。
        Jg = (Sm[0] + a * math.cos(base), -(Sm[1] + a * math.sin(base)))
    place(arm, upper, root, Jg, a)
    place(arm, fore, Jg, target, b)
    return Jg, k, root


def solve_all(arm):
    """Pose every limb from its target empty + keyed bend. Returns the stretch map."""
    ks = {}
    for limb, (_upper, _fore, empty) in LIMBS.items():
        ob = bpy.data.objects[empty]
        raw = float(ob["bend"]) if "bend" in ob.keys() else -1.0
        bend = None if raw < 0.0 else raw
        _, k, _root = solve_limb(arm, limb, game_px(ob), bend)
        ks[limb] = round(k, 2)
    return ks
