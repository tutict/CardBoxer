# Natural fighting-game motion — authoring v2

Authored candidate is complete for both roles and all 19 clips, in the isolated
project. Real render acceptance, gameplay regression, and guarded installation
remain root-owned. Candidate data SHA256:
`083c84e3e24bdb4bea6d3e4b92855322caea97d675cae19a06df36acefd5a703`.

## Changed motion

The guard now bends the elbows beside the ribs and holds the unchanged hands
near the chin. Player elbow angles are 55.55/45.53 degrees, foe 41.44/41.47;
the old front/rear player angles were 104.5/94.7 degrees. Both roles keep their
elbows below the shoulder, wrists 3.7–6.2 cm below the head origin and hands
at least 0.137 m above the shoulder. The foe's
0.55 m upper arm/0.30 m forearm needs different target placement from the
player's 0.40/0.36 m chain; the poses therefore use measured per-role targets.

Jab chambers only 5.47/6.02 cm, instead of 23.7/24.9 cm, then drives along a
short line while the rear hand remains protected. Cross loads rearward, turns
the hip before the rear fist extends, and adds chest torque. At early active,
hip turn is 81.1% complete while fist extension is 21.4% complete. New breakdowns
separate hip, chest and arm timing. Forearm roll pronates the unchanged striking
hand meshes. During recovery the wrist returns to guard while 0.85–3.18 cm of
root settle remains, followed by the torso returning to its stance.

Sweep now follows a low lateral arc around a fixed rear ankle. The front boot
is 4.0 cm above the floor at contact and the knee angle is 162.33/164.20 degrees;
the old contact used a 13 cm lift and 129.8/111.2 degree knee angles. The player
crouch is calibrated to preserve the actual +Z contact reach, rather than
silently clamping an unreachable target. Contact foot +Z is exactly 0.790/0.670 m.

Uppercut has a low chamber, hip/leg drive, an intermediate rising hand arc, then
the upper strike and trailing recovery. Wave gathers close to the body while
weight loads backward, then shifts and pushes both hands forward. Throw reaches,
loads down, turns through hip and chest, and brings the hands back before its
body settles. High guard and block use compact protective arms. Idle, walk,
movement, recover, focus, reactions and KO use the new guard endpoints and
continuous target-space curves. Rush/backstep now include a planted handoff
between lifting the first and second foot.

## Continuous authoring and unchanged interface

All 751 poses per role are solved in target space at half-frame intervals.
Scalar targets use time-aware, monotone C1 Hermite tangents: tangents vanish at
true reversals or held values, rather than easing the whole pose to zero velocity
at every breakdown. Analytic two-bone IK and original weighted boot skinning
solve all limb rotations and actual sole heights at every dense pose. Runtime
time-aware cubic quaternion sampling and bounded root interpolation are owned
by the runtime agent and were coordinated with this half-frame density.

JSON remains version 1, with existing `frames`, `split`, `contact_frame`,
rest-relative quaternion and root-offset fields. Each clip adds the sampler
hint `interpolation: continuous`; author metadata records the 0.5-frame step.
All contact and phase endpoints are explicit keys. Card and loop endpoints
remain exact copies of stance. Card timing, contact authority, 28-frame KO,
rigs, geometry, materials, skins, physics and game rules are unchanged.

KO collapse retains its original sprawled-arm pole/roll after frame15: applying
the standing guard elbow pole at that endpoint put the arm mesh below the floor.
The original final visible mesh minimum is restored to -0.010572 m player and
+0.000006 m foe. No GLB edits were made by this work.

## Fresh evidence

`author_native_flow_check.py` first failed 38 meaningful old-motion checks:
compact guard, low extended sweep, continuous target coverage, economical
chamber, and hand-before-body recovery. `logs/natural-author-flow-red.log`
records that failure. A separate calibrated sweep-reach regression then caught
the initial player's unreachable contact target in
`logs/natural-author-reach-red.log`; the crouch calibration fixed it.

Final fresh checks:

- `logs/natural-author-cheek-flow.log`: biomechanics PASS, zero failures. Measures
  actual rig FK, compact guard, swept lateral path, fixed rear ankle, preserved
  contact reach, hip lead, economical chamber and staggered recovery.
- `logs/natural-author-cheek-ground.log`: actual CPU-skinned sole PASS, zero failures,
  1,502 dense authored poses, maximum support error <0.000020 m. Final KO whole
  visible mesh also meets the existing floor tolerance.
- `logs/natural-author-cheek-quarter.log`: Godot 4.5 native contract/geometry PASS,
  zero failures, 2,966 quarter-frame samples including every midpoint between
  dense keys. Actual imported ArrayMesh support maximum 0.002571 m, below the
  tightened 0.020 m requirement.
- `reports/natural-author-metrics.json`: final per-role biomechanics numbers.
- `reports/motion-actual-sole.json`: final dense actual-sole measurements.

Godot's existing root-certificate-store environment error appears after its
PASS line; the process exits 0 without GDScript parse/runtime errors. Full
normal-speed/slow-motion rendering and live contact acceptance are still the
root's next verification step, not claimed by authoring tests.

Owned edits: `author_native_motion.py`, new `author_native_flow_check.py`,
`project/data/combat_motion_3d.json`, and authored-geometry parts of
`project/tests/native_motion_check.gd`. The invalid-data contact test now removes
the actual contact key by frame instead of assuming it is sparse array index2.
No commits, subagents, main-project edits, or runtime/presentation edits.

## Final visual guard calibration

Root reviewed `shots/natural-v2-core/player-stance-facing1-f000.0.png` and found
the front fingertips above the forehead and the guarded palms still presented
to the camera. The final small calibration lowers actual wrists 9.0–9.8 cm,
retreats them 2.6–3.8 cm, tucks the elbow pole from lateral0.24 to0.20, and turns
default forearm roll from24 to58 degrees. Protected hands maintain that roll
through jab/cross/uppercut. Jab chamber and early hand recovery follow the new
guard heights. All endpoints were regenerated; strike reaches, sweep trajectory,
feet, phase timing and KO remain unchanged.

`logs/natural-author-cheek-red.log` records the four intended wrist-height
failures before this change. Guard tests now measure wrist location relative
to the actual head origin instead of locking the previous raised-hand height.
The final candidate is frozen after the fresh flow, quarter geometry and sole
checks listed above, for root's normal/slow cycle rendering.
