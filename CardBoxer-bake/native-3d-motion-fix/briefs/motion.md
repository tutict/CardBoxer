# Task: native 3D pose authoring and sampler

Read ../contracts.md first; exact public interfaces/pose contract are binding.
Your owned files: project/scripts/native_motion.gd,
project/data/combat_motion_3d.json, project/tests/native_motion_check.gd,
author_native_motion.* and any authoring-only probes/tests in this task folder.
Do not edit arena/fighter/rig_driver/fighter_3d_layer or other agents' tests.

User wants arcade fighting on both existing models (player and foe), all 12 cards
plus hit_light/hit_heavy/block and stance/idle/walk/ko, both gameplay modes.
Keep models, topology, material, bone names and hand shapes. Source split/frames
come from project/data/motion_input*.json and scripts/card_data.gd, not old bakers.

Write meaningful failing test first, run with real log path, then implement.
Use native local rest-relative multi-axis quaternions; raw 2D amplitude retarget is
the bug and must not be copied. Use both models' actual Skeleton3D rests.
Current headless RigDriver can load rest metadata and this task's project has the
cached imports. Independent rig-rest export is being prepared by QA agent.

Arm geometry is transverse at rest (+/-X); model faces Godot +Z. Fighting guard
should bend both elbows and bring hands in front of chest/head (+Z). Jab extends
front arm forward, cross rear arm + torso/hip twist, uppercut travels upward,
sweep crouches and swings one leg horizontally forward, wave pushes both palms,
throw reaches/grabs and twists toward opponent. Movement/guard/evade/focus/recover
must read differently. Arcade windup, fast strike, impact peak at final active
frame, and recovery overshoot returning exactly to guard. Avoid all clips as
same out-to-side raised-arm gesture. Each role needs its own calibrated poses.

Authoring can use analytic two-bone IK/FK and output sparse keyframes in JSON.
Skeleton hierarchy/rest rotations matter; calculate delta=q_rest^-1*q_local,
do not assume each bone's local Z is the same world axis. No need for AnimationPlayer
or re-exported animated GLBs: new JSON is the source consumed by native sampler.
Four arms need independent upperarm/forearm orientation and roll, torso multi-axis.
Feet must reach ground and avoid obvious skating/floating; no independent foot bones.
Root offsets are skeleton-local meters and applied once by root's new driver.

First prioritize stance/jab/cross/sweep. Make sampler + a first clip set available
early so root can render actual 3D and give feedback. Then fill remaining clips.
Do not claim visual quality from math alone; root/QA will supply renders.

Data validation: all roles/clips present, 13 named finite normalized quaternions,
strictly increasing key frames in range, card splits/frames consistent, meaningful
distinct attack directions, closed card endpoints and looping walk/idle endpoints.
Return explicit diagnostic on invalid data; no silent identity for absent native clip.
sample accepts fractional frames and slerps. No new gameplay code or 2D table edits.

Record tests, design details, and concerns in reports/motion-report.md. Return a
short status with files, test result and readiness for visual QA. No git commits.
