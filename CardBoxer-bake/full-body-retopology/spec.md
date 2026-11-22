# Approved Blender retopology specification

Approved by user with "Please implement the plan" on 2026-11-20.

Both current characters receive full-body retopology, new UVs and reskinning,
preserving their identity, costume silhouette, colors and proportions. Deliver
editable Blender 5.2 projects with immutable source reference, refined high-detail
reference and new game mesh. Improve player face/eyelids/lips/ears/hands and cloth,
foe mask/armor edges/crystals/hands and cloth; keep joint deformation usable.

- Source: current installed Natural V2 main game, recorded in baseline-manifest.json.
- Canonical skeleton: all 14 original joints, 13 driven body bones and independent
  neutral_bone. Preserve names/order/parents/rest/mesh and skeleton transforms/IBMs.
  No visible neutral influence. At most four normalized influences per vertex.
- New low mesh: player target 60,000 triangles, foe 70,000, maximum 80,000 each.
  A quad-dominant editable body with intentional eye/mouth/finger/joint loops.
  Source index components at UV/normal seams are not physical holes.
- Runtime: one skinned mesh, surface 0 contains boots, one PBR material atlas;
  base-color, tangent normal and ORM images, each 4096x4096. Refined high-detail
  geometry is for authoring/baking and not included in runtime mesh.
- Hands: Basis open, grip_half_f, grip_f, grip_half_b, grip_b morphs. Zero deltas
  outside respective hands. hand_grip=[front,back], each 0..1. Progressive mapping:
  0..0.5 open->half, 0.5..1 half->closed. Body quaternions and existing phase data
  remain unchanged. Grips share visual sampling/transitions/pause/hitstop/KO/reset.
- Hand policy: guard/movement .75; jab/cross/uppercut active 1; sweep .75;
  wave open during gather/push; throw open->.65 grasp; all recover to .75;
  block/guard active 1; hits relax .25; KO relaxes 0.
- New contact sockets: open/half/closed for front/rear hand, canonical forearm-local
  coordinates, interpolated with identical grip coefficients for prediction/FX.
  Calibrate visible palm/knuckle contact, maintain original logical positions,
  phase counts, damage and taikou .48 contact/1.12 attack/.24 hold/.45 KO timing.
- Improve only foe's dedicated dark composite, keeping deep color identity;
  start RGB gain .65/.55/.52, tune same-view foreground mean to 50-75% of player's.
- Geometry/render acceptance: no spikes/unexpected openings/bad normals or crop;
  inspect open/.25/.5/.75/closed hands, all19 clips/both facings. Sole and visible
  contact deviation <=.02m. Normal 430/850 match, both modes, event/freeze/reset checks.
- Same machine real render avg >=59FPS, frame p95 <=20ms, pose <=2ms per role.
- Delivery: .blend + GLB + texture files, wireframe/near/whole-body comparisons,
  normal and slow preview, verified isolated game and guarded main update/backup.

Godot executable must ALWAYS receive an absolute real writable --log-file;
never omit it, never NUL. Do not alter user-owned Blender process/windows or
main game before root installs the completed verified candidate.
