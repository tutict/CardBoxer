# User refinement — natural fighting-game motion

User steering 2026-11-20: "动作要像格斗游戏那样做得更流畅自然一些".
This continues the approved 3D both-role/all19 taikou+realtime task. V1 is now
installed (29 guarded files, backup saved); its native-motion test really passed,
but the installer incorrectly expected an underscore PASS marker instead of
"NATIVE MOTION CHECK: PASS". Fix that verifier, not production behavior.

V1 source/authoring snapshots: versions/v1/. Original: baseline/.
Work on project/ first; final incremental update must guard against current
installed hashes in reports/install-receipt.json, preserve unrelated edits and
save a versioned backup. Never re-run original --apply over an existing receipt.

## Motion direction

- Tight, readable bent-elbow guard; arms must not read as showing/opening hands.
- Grounded weight shift drives hip, chest/shoulder, elbow and wrist in that order.
- Jab is economical and snappy, rear cross adds torso turn, uppercut rises in an
  arc from legs/hip, sweep stays low with an extended sweeping leg and planted rear
  foot, wave gathers then pushes, throw visibly loads and turns.
- Forearm roll helps existing rigid hand meshes read as strikes; no new fingers,
  geometry, bones, materials or physics. Preserve existing model/costume shape.
- Continuous velocity through non-contact poses; avoid linear keyframe corners
  and repeated stops at intermediate keys. Return hand before torso settles;
  small trailing rebound, relaxed return to guard, not abrupt whole-body resets.
- Match approach and return with actual leg/shuffle motion. Preserve normal-spawn
  calibrated hand/body contact and avoid feet sliding back during recovery.

## Constraints and acceptance

- Keep Defs card phase counts, damage/position/AI/meter/rules unchanged.
- Keep taikou contact .48s, attack1.12s, hold.24s, total logical1.9s; ordinary.06s
  transitions, exact immediate contact/impact and0.45sKO remain authoritative.
- Required all19 clips/role; native quaternion/phase interfaces unchanged.
- Choose authored smooth target trajectories / additional breakdown poses and
  smooth quaternion sampling as appropriate. Intermediate bone velocity should
  not kink or pause at arbitrary keys; phase/contact endpoints stay exact.
- Ground actual skinned soles, not shin endpoints. Preserve support within2cm
  outside intentional lifted steps; no new giant skin spikes or cropped body.
- Prove improvements with normal-speed and slow-motion continuous GIFs showing
  whole guard->windup->hit->recovery cycles, both roles, readable footwork.
- Keep event ordering, late wave/newaction, KO, reset, pause and3D/off logical tests.

## Ownership

- Motion author: author_native_motion.py, author_native_grounding.py and related
  helpers, project/data/combat_motion_3d.json, authored-motion tests. Make dense
  smooth trajectories if they remove corners while preserving actual sole support.
- Runtime flow: project/scripts/native_motion.gd and battle_presentation.gd,
  interpolation/footwork tests. Coordinate data schema and sampling with author.
- Root: verifier/update installer, review, render/capture and final main update.
  No main edits until revised candidate is validated and approved for writing.
